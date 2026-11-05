"""Repository-boundary regression tests for document, ADR, init and tooling writes.

Every case runs inside a throwaway ``tempfile.mkdtemp()`` repository with a
separate outside directory.  No real workspace is used as a test target.

Test resource ownership (enforced by ``claim_tree`` / ``delete_owned_tree``):

* every directory a case creates is registered through ``claim_tree``, which only
  accepts a throwaway root whose name carries one of this file's ``TEMP_PREFIXES``
  and sits under the system temp directory;
* cleanup deletes only those trees, never follows a directory link (a junction or
  symlink is removed as an entry so its target survives), and does not swallow
  errors -- a failed cleanup is a failed test;
* a case that must prove "nothing was created outside the repo" reserves a
  unique directory it created and then removed itself (``reserve_absent_dir``),
  so the path it asserts on is provably test-owned.  No case deletes a fixed
  absolute path such as ``C:/pm-boundary-drive``, and no case cleans a path
  resolved from the current working directory.

Baseline behaviour (before the fix): ``create_adr()`` ran ``mkdir`` on the
configured ``adr_dir`` and wrote through it before ``relpath()`` could complain,
and ``init()``/``sync_tooling()`` followed linked parents outside the repository.
``relpath()`` only judges *after* the write, so it never prevented the escape.
These tests assert the two things the fix must guarantee: the write is refused
before it happens, and the outside directory is byte-for-byte untouched.  案例 E
applies the same rule to the sidecar lock directory introduced by the concurrency
fix, because ``mkdir(parents=True)`` there was a write like any other.  案例 F
covers the Windows spelling drift: ``os.path.realpath()`` can answer the same
object twice with different prefixes, which would both refuse a legal
in-repository path and hand two processes two different lock names.
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_memory.bootstrap import init, sync_tooling
from project_memory.common import (PMError, _lock_path_for, canonical_realpath, ensure_inside_repo,
                                   record_lock)
from project_memory.knowledge import create_adr, create_document, load_config

IS_WIN = sys.platform == 'win32'
TEMP_PREFIXES = ('pm-bound-repo-', 'pm-bound-outside-', 'pm-bound-drive-')


def git(repo: Path, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


def fingerprint(root: Path) -> dict:
    """name -> sha256 for every file, plus the set of directories."""
    files, dirs = {}, []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or (IS_WIN and getattr(path.lstat(), 'st_reparse_tag', 0)):
            files[rel] = 'link'
        elif path.is_file():
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            dirs.append(rel)
    return {'files': files, 'dirs': dirs}


def dir_link(target: Path, link: Path) -> str:
    """Create a directory link; junctions on Windows, symlinks elsewhere."""
    if IS_WIN:
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True)
        if result.returncode != 0 or not link.is_dir():
            raise unittest.SkipTest('本机无法创建目录联接（junction）：'
                                    + result.stdout.decode('utf-8', 'replace'))
        return 'junction'
    os.symlink(str(target), str(link), target_is_directory=True)
    return 'symlink'


def make_temp_tree(prefix: str) -> Path:
    """Create a throwaway tree this file owns; the caller registers it with claim_tree."""
    assert prefix in TEMP_PREFIXES, f'未登记的临时前缀：{prefix}'
    return Path(tempfile.mkdtemp(prefix=prefix))


def _unlink_file(path: str) -> None:
    """Delete one entry, coping with the read-only bit git puts on loose objects.

    PermissionError is retried exactly once after clearing the bit; a second
    failure propagates instead of being labelled "ignore_errors".
    """
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)


def _remove_directory(path: str) -> None:
    try:
        os.rmdir(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.rmdir(path)


def delete_owned_tree(root: Path) -> None:
    """Remove a throwaway tree without ever descending into a directory link.

    A Windows junction and a POSIX symlink are unlinked as entries, so content
    living behind them is untouched.  Errors are not swallowed: a cleanup that
    really fails must fail the test instead of silently leaving litter -- the
    read-only git objects used to defeat ``shutil.rmtree(..., ignore_errors=True)``
    and leave hundreds of half-deleted temp repositories behind.
    """
    if not root.exists():
        return
    with os.scandir(root) as scan:
        entries = sorted(scan, key=lambda item: item.name)
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_reparse_tag', 0):
            try:
                os.unlink(entry.path)
            except OSError:
                _remove_directory(entry.path)  # junctions need rmdir; a second failure propagates
        elif entry.is_dir(follow_symlinks=False):
            delete_owned_tree(path)
        else:
            _unlink_file(entry.path)
    _remove_directory(str(root))


def claim_tree(case: unittest.TestCase, root: Path) -> Path:
    """Register a test-owned tree for deletion; refuse anything else."""
    if not root.name.startswith(TEMP_PREFIXES):
        raise AssertionError(f'拒绝清理不是本测试创建的目录：{root}')
    temp_root = Path(tempfile.gettempdir()).resolve()
    if temp_root not in root.resolve().parents:
        raise AssertionError(f'拒绝清理临时目录之外的路径：{root}')
    case.addCleanup(delete_owned_tree, root)
    return root


def reserve_absent_dir(prefix: str) -> Path:
    """Reserve a unique path that provably does not exist right now.

    ``mkdtemp`` makes the ownership unambiguous, ``rmdir`` gives the directory
    back; if the tool under test recreates anything at that exact spelling the
    test can attribute it and clean it up inside its own temp area.
    """
    path = make_temp_tree(prefix)
    os.rmdir(path)
    return path


def make_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix='pm-bound-repo-'))
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'test@example.invalid')
    git(root, 'config', 'user.name', 'Test')
    (root / 'README.md').write_text('hello', encoding='utf-8')
    git(root, 'add', 'README.md')
    git(root, 'commit', '-qm', 'first commit')
    return root


def write_config(root: Path, **overrides) -> None:
    cfg = {'schema_version': '1.1', 'doc_roots': ['docs'], 'mirror_roots': [], 'legacy_roots': [],
           'adr_dir': 'docs/decisions'}
    cfg.update(overrides)
    (root / '.project-memory').mkdir(parents=True, exist_ok=True)
    (root / '.project-memory' / 'config.json').write_text(json.dumps(cfg), encoding='utf-8')


class EscapedConfigTest(unittest.TestCase):
    """案例 A：配置里的目录本身就想跳出仓库。"""

    def setUp(self):
        self.root = claim_tree(self, make_repo())
        self.outside = claim_tree(self, make_temp_tree('pm-bound-outside-'))

    def assert_refused(self, adr_dir: str) -> None:
        before = fingerprint(self.outside)
        write_config(self.root, adr_dir=adr_dir)
        with self.assertRaises(PMError):
            create_adr(self.root, '边界', 'topic', 1, '方案', '理由', 'team')
        self.assertEqual(fingerprint(self.outside), before, '非法配置不得在仓库外留下任何文件')
        inside = list((self.root / 'docs').rglob('*')) if (self.root / 'docs').exists() else []
        self.assertEqual(inside, [], '非法配置也不能在仓库里留下半套目录')

    def test_parent_traversal_adr_dir(self):
        self.assert_refused(os.path.join('..', self.outside.name, 'decisions'))

    def test_absolute_adr_dir(self):
        self.assert_refused(str(self.outside / 'decisions'))

    def test_drive_style_adr_dir(self):
        """盘符路径：Windows 上会越界写到别的目录，POSIX 上会在仓库里留下 ``C:`` 目录，
        两边都必须在写入前拒绝。

        恶意串不再写成固定的 ``C:/pm-boundary-drive``——那要求测试先删掉一个不属于它的
        外部目录。Windows 改用 ``reserve_absent_dir()`` 预留一个「本测试建过又当场收回」
        的唯一目录，它的绝对拼写天然带盘符，越界写只会落在这个名字上，而清理权始终在本测试
        手里；POSIX 下 ``C:/...`` 是相对写法，越界产物只可能落在临时仓库内部，于是断言对象
        仍是本测试拥有的目录。两条分支都不清理仓库外目标，也不按当前工作目录解析路径。
        """
        before = fingerprint(self.outside)
        if IS_WIN:
            spare = claim_tree(self, reserve_absent_dir('pm-bound-drive-'))
            self.assertFalse(spare.exists(), '预留目录必须先不存在，之后的出现才算得是工具写的')
            adr_dir = str(spare / 'decisions').replace('\\', '/')
        else:
            spare = self.root / 'C:'
            adr_dir = 'C:/pm-boundary-drive/decisions'
        write_config(self.root, adr_dir=adr_dir)
        with self.assertRaises(PMError):
            create_adr(self.root, '盘符', 'topic', 1, '方案', '理由', 'team')
        self.assertFalse(spare.exists(), f'带盘符的配置不能在仓库外创建目录：{spare}')
        stray = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                       if p.name.startswith('C:'))
        self.assertEqual(stray, [], '带盘符的配置不能在仓库里留下 C: 目录')
        self.assertEqual(fingerprint(self.outside), before, '盘符配置也不能动仓库外既有内容')
        inside = list((self.root / 'docs').rglob('*')) if (self.root / 'docs').exists() else []
        self.assertEqual(inside, [], '非法配置不能在仓库里留下半套目录')

    def test_unc_style_adr_dir(self):
        self.assert_refused('//server/share/decisions')

    def assert_document_refused(self, path: str) -> None:
        """Same rule for the document path argument: refuse before creating anything."""
        before = fingerprint(self.outside)
        write_config(self.root)
        with self.assertRaises(PMError, msg=path):
            create_document(self.root, 'DOC-BOUND', '边界文档', 'canonical', 'draft', 'team', path)
        self.assertEqual(fingerprint(self.outside), before, f'非法文档路径越界写：{path}')
        self.assertEqual(list((self.root / 'docs').rglob('*')) if (self.root / 'docs').exists() else [],
                         [], f'非法文档路径不能在仓库里留下半套目录：{path}')
        stray = [p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                 if p.name.startswith('C:')]
        self.assertEqual(stray, [], f'非法文档路径不能在仓库里留下 C: 目录：{stray}')

    def test_document_paths_cannot_escape(self):
        """create_document() 的路径参数覆盖同样的越界形态。"""
        for form in ('../outside.md', 'docs/../../outside.md', 'docs\\..\\outside.md',
                     str(self.outside / 'x.md'), 'C:/pm-boundary-doc/x.md', '//server/share/x.md'):
            with self.subTest(form=form):
                self.assert_document_refused(form)

    def test_docs_root_argument_cannot_escape(self):
        """init() 的 --docs-root 一类参数走同一套失败关闭口径。"""
        for form in ('../outside', 'docs/../..', str(self.outside),
                     'C:/pm-boundary-root', '//server/share'):
            with self.subTest(form=form):
                before = fingerprint(self.outside)
                with self.assertRaises(PMError):
                    init(self.root, 'none', form, 'overlay')
                self.assertEqual(fingerprint(self.outside), before, f'非法 docs_root 越界写：{form}')
                # 注意：不能用 ``self.root / 'C:'``——Windows 上那会被解析成当前盘符，
                # 变成一个相对于工作目录的路径。这里只按名字在仓库里找残留。
                stray = [p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                         if p.name.startswith('C:')]
                self.assertEqual(stray, [], f'非法 docs_root 在仓库里留下 C: 目录：{stray}')
                self.assertEqual(
                    sorted(p.name for p in self.root.iterdir() if p.is_dir()
                           and p.name not in ('.git', '.project-memory')),
                    [], f'非法 docs_root 在仓库根下留下目录：{form}')

    def test_mixed_separator_traversal(self):
        self.assert_refused('docs\\..\\' + self.outside.name + '\\decisions')

    def test_roots_cannot_escape_either(self):
        for key in ('doc_roots', 'mirror_roots', 'legacy_roots', 'frozen_roots', 'evidence_roots'):
            write_config(self.root, **{key: [str(self.outside)]})
            with self.assertRaises(PMError, msg=key):
                load_config(self.root)

    def test_legal_config_still_loads(self):
        write_config(self.root, doc_roots=['docs/'], adr_dir='docs/decisions')
        cfg = load_config(self.root)
        self.assertEqual(cfg['doc_roots'], ['docs'], '结尾斜杠是历史合法写法，只归一化不拒绝')
        self.assertEqual(cfg['adr_dir'], 'docs/decisions')


class LinkedParentTest(unittest.TestCase):
    """案例 B：仓库内的目录是指向仓库外的链接。"""

    def setUp(self):
        self.root = claim_tree(self, make_repo())
        self.outside = claim_tree(self, make_temp_tree('pm-bound-outside-'))
        self.kind = dir_link(self.outside, self.root / 'docs')

    def test_decision_through_linked_docs(self):
        write_config(self.root)
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            create_adr(self.root, '联接', 'topic', 1, '方案', '理由', 'team')
        self.assertEqual(fingerprint(self.outside), before, f'{self.kind} 父目录不应被跟随')

    def test_new_document_through_linked_docs(self):
        write_config(self.root)
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            create_document(self.root, 'DOC-LEAK', '逃逸', 'canonical', 'draft', 'team',
                            'docs/topics/leak.md')
        self.assertEqual(fingerprint(self.outside), before)

    def test_link_inside_the_repo_is_still_allowed(self):
        """安全检查不能把仓库内部的链接也一并禁掉。"""
        (self.root / 'real' / 'decisions').mkdir(parents=True)
        dir_link(self.root / 'real', self.root / 'linked')
        write_config(self.root, doc_roots=['linked'], adr_dir='linked/decisions')
        rel = create_adr(self.root, '内部链接', 'topic', 1, '方案', '理由', 'team')
        self.assertTrue((self.root / rel).is_file(), f'仓库内链接仍应可写：{rel}')
        self.assertEqual(list((self.root / 'real' / 'decisions').glob('ADR-0001-*.md')).__len__(), 1)
        self.assertEqual(fingerprint(self.outside), {'files': {}, 'dirs': []})


class LockSidecarTest(unittest.TestCase):
    """案例 E：问题一的 sidecar 锁目录也是写入路径，链接出去同样算逃逸。

    ``record_lock()`` creates ``.project-memory/cache/locks/<hash>.lock`` with
    ``mkdir(parents=True)`` + ``os.open``.  Before this case existed, a junction
    or symlink at ``cache`` (or at ``cache/locks``) silently moved the lock
    outside the repository, which is exactly the failure mode of 案例 B in the
    concurrency code path.  A link that stays inside the repository must keep
    working: the check is about the boundary, not about links as such.
    """

    def setUp(self):
        self.root = claim_tree(self, make_repo())
        self.outside = claim_tree(self, make_temp_tree('pm-bound-outside-'))
        goals = self.root / '.project-memory' / 'coordination' / 'goals'
        goals.mkdir(parents=True)
        self.record = goals / 'G-LOCK.json'
        self.record.write_text('{}\n', encoding='utf-8')

    def test_cache_directory_link_outside_is_refused(self):
        dir_link(self.outside, self.root / '.project-memory' / 'cache')
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            with record_lock(self.record, timeout=1.0, label='边界'):
                pass
        self.assertEqual(fingerprint(self.outside), before, '锁文件不能写进仓库外的链接目标')
        self.assertFalse((self.outside / 'locks').exists(), '拒绝必须发生在 mkdir 之前')

    def test_locks_directory_link_outside_is_refused(self):
        (self.root / '.project-memory' / 'cache').mkdir()
        victim = self.outside / 'locks_target'
        victim.mkdir()
        dir_link(victim, self.root / '.project-memory' / 'cache' / 'locks')
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            with record_lock(self.record, timeout=1.0, label='边界'):
                pass
        self.assertEqual(fingerprint(self.outside), before, f'{victim} 里不能多出锁文件')
        self.assertEqual(list(victim.glob('*.lock')), [])

    def test_lock_directory_link_inside_the_repo_is_allowed(self):
        (self.root / '.project-memory' / 'cache').mkdir()
        target = self.root / 'scratch-locks'
        target.mkdir()
        dir_link(target, self.root / '.project-memory' / 'cache' / 'locks')
        with record_lock(self.record, timeout=1.0, label='边界'):
            pass
        self.assertEqual(len(list(target.glob('*.lock'))), 1, '仓库内链接的锁目录仍应可用')
        self.assertEqual(fingerprint(self.outside), {'files': {}, 'dirs': []})


def fixed_resolver(answer: str):
    """A stand-in ``realpath`` that always returns ``answer``."""

    def resolver(path, *args, **kwargs):
        return answer

    return resolver


def plain_realpath(path, *args, **kwargs):
    """``canonical_realpath`` demoted to the raw resolver — the in-test negative control."""
    return os.path.realpath(path)


def device_namespace_spelling(text: str) -> str:
    """The verbatim-path spelling of ``text``, as Windows hands it back."""
    if text.startswith('\\\\'):
        return '\\\\?\\UNC\\' + text.lstrip('\\')
    return '\\\\?\\' + text


class SpellingDrift:
    """A ``realpath`` that answers with the device-namespace spelling Windows produces.

    The real drift is a race against ``os.replace`` and cannot be produced on
    demand, so these cases inject it.  ``plain`` names resolutions that keep the
    ordinary spelling (matched exactly, after normalization): the drift hits
    individual calls, and a spurious boundary refusal only appears when the root
    and the candidate disagree about the prefix.  ``drifted`` lets every case prove
    the injection fired — a patch that silently became a no-op would otherwise
    report a pass for the wrong reason.
    """

    def __init__(self, plain=()):
        self._real = os.path.realpath
        self._plain = frozenset(os.path.normcase(self._real(item)) for item in plain)
        self.calls = 0
        self.drifted = 0

    def __call__(self, path, *args, **kwargs):
        text = self._real(path)
        self.calls += 1
        if os.path.normcase(text) in self._plain:
            return text
        answer = device_namespace_spelling(text)
        if answer != text:
            self.drifted += 1
        return answer


class CanonicalPrefixSpellingTest(unittest.TestCase):
    """案例 F (i)：两种拼写必须归一到同一种，非路径前缀仍按原样失败关闭。

    Pure string behaviour of ``canonical_realpath()`` with the resolver's answer
    injected, so it is meaningful on every platform.  The two forms that must not
    be rewritten are the volume-GUID and ``GLOBALROOT`` prefixes: they do not name
    an ordinary path, and silently normalizing them would turn a refusal into an
    accept.
    """

    CASES = [
        ('ordinary drive path', 'C:\\repo\\docs\\a.md', 'C:\\repo\\docs\\a.md'),
        ('prefixed drive path', '\\\\?\\C:\\repo\\docs\\a.md', 'C:\\repo\\docs\\a.md'),
        ('prefixed lower-case drive', '\\\\?\\c:\\repo\\a.md', 'c:\\repo\\a.md'),
        ('prefixed UNC share', '\\\\?\\UNC\\server\\share\\a.md', '\\\\server\\share\\a.md'),
        ('ordinary UNC share', '\\\\server\\share\\a.md', '\\\\server\\share\\a.md'),
        ('volume GUID stays verbatim',
         '\\\\?\\Volume{11111111-2222-3333-4444-555555555555}\\a.md',
         '\\\\?\\Volume{11111111-2222-3333-4444-555555555555}\\a.md'),
        ('device global root stays verbatim',
         '\\\\?\\GLOBALROOT\\Device\\HarddiskVolume3\\a.md',
         '\\\\?\\GLOBALROOT\\Device\\HarddiskVolume3\\a.md'),
    ]

    def test_prefix_handling(self):
        for label, resolver_answer, expected in self.CASES:
            with self.subTest(label):
                with mock.patch('os.path.realpath', new=fixed_resolver(resolver_answer)):
                    self.assertEqual(canonical_realpath('anything'), expected)

    def test_the_two_spellings_hash_to_the_same_key(self):
        """The lock name is ``sha256(normcase(canonical))``, so normcase must agree too.

        The UNC case is the one that can silently regress: returning ``//server/
        share`` parses as the same path as ``\\server\\share`` but ``normcase()``
        leaves separators alone, so the two would hash differently and fork the lock.
        """
        for prefixed_form, plain_form in [('\\\\?\\C:\\repo\\a.md', 'C:\\repo\\a.md'),
                                          ('\\\\?\\UNC\\server\\share\\a.md',
                                           '\\\\server\\share\\a.md')]:
            with self.subTest(prefixed_form):
                with mock.patch('os.path.realpath', new=fixed_resolver(prefixed_form)):
                    drifted = canonical_realpath('x')
                with mock.patch('os.path.realpath', new=fixed_resolver(plain_form)):
                    plain = canonical_realpath('x')
                self.assertEqual(os.path.normcase(drifted), os.path.normcase(plain))


@unittest.skipUnless(IS_WIN, '设备命名前缀是 Windows 路径解析器的行为')
class PathSpellingDriftTest(unittest.TestCase):
    """案例 F (ii)：拼写漂移不能让同一记录分叉成两把锁，也不能拒绝合法的仓库内路径。

    ``os.path.realpath()`` normally answers ``C:\\dir\\file``, but while a peer is
    replacing that file it can answer the verbatim form (a ``?`` prefix followed by
    the drive) instead.  Measured on this machine: 1 drift in 40 134 resolutions of
    a record under continuous replacement, and the two spellings hashed to two
    different lock keys.  Both the sidecar name and the boundary check are derived
    from realpath, so without normalization one process takes a lock nobody else
    takes — mutual exclusion lost without an error — and a legal in-repository path
    is refused because the root and the candidate disagree about the prefix.

    Each case asserts the injected drift actually fired and then re-runs the same
    call with ``canonical_realpath`` demoted to plain ``os.path.realpath``, which
    must fail.  A case that cannot tell those two apart proves nothing.
    """

    def setUp(self):
        self.root = claim_tree(self, make_repo())
        self.outside = claim_tree(self, make_temp_tree('pm-bound-outside-'))
        goals = self.root / '.project-memory' / 'coordination' / 'goals'
        goals.mkdir(parents=True)
        self.record = goals / 'G-DRIFT.json'
        self.record.write_text('{}\n', encoding='utf-8')
        self.locks = self.root / '.project-memory' / 'cache' / 'locks'

    def assert_drifted(self, drift: SpellingDrift) -> None:
        self.assertGreaterEqual(drift.calls, 1, '注入的 realpath 没有被调用：案例等于空跑')
        self.assertGreaterEqual(drift.drifted, 1, '注入未产生漂移拼写：案例等于空跑')

    def test_sidecar_lock_name_is_the_same_under_both_spellings(self):
        expected = _lock_path_for(self.record)
        drift = SpellingDrift()
        with mock.patch('os.path.realpath', new=drift):
            drifted = _lock_path_for(self.record)
        self.assert_drifted(drift)
        self.assertEqual(drifted[0].name, expected[0].name, '同一记录必须落在同一把锁上')
        self.assertEqual(drifted[1], expected[1])
        with mock.patch('os.path.realpath', new=SpellingDrift()), \
                mock.patch('project_memory.common.canonical_realpath', new=plain_realpath):
            neutralised = _lock_path_for(self.record)[0].name
        self.assertNotEqual(neutralised, expected[0].name,
                            '摘掉归一化后锁名应当分叉；不分叉说明本案例没有检测力')

    def test_record_lock_writes_one_sidecar_under_both_spellings(self):
        with record_lock(self.record, timeout=1.0, label='拼写'):
            pass
        drift = SpellingDrift()
        with mock.patch('os.path.realpath', new=drift):
            with record_lock(self.record, timeout=1.0, label='拼写'):
                pass
        self.assert_drifted(drift)
        self.assertEqual(sorted(item.name for item in self.locks.glob('*.lock')),
                         [_lock_path_for(self.record)[0].name], '两次获取只能留下一把锁文件')
        with mock.patch('os.path.realpath', new=SpellingDrift()), \
                mock.patch('project_memory.common.canonical_realpath', new=plain_realpath):
            with record_lock(self.record, timeout=1.0, label='拼写'):
                pass
        self.assertEqual(len(list(self.locks.glob('*.lock'))), 2,
                         '负对照应当留下一把额外的、没人再会去取的锁文件')

    def test_legal_in_repo_path_is_still_accepted(self):
        target = self.root / 'README.md'
        self.assertEqual(ensure_inside_repo(self.root, target, '写入路径'), target)
        drift = SpellingDrift(plain=[self.root])
        with mock.patch('os.path.realpath', new=drift):
            self.assertEqual(ensure_inside_repo(self.root, target, '写入路径'), target,
                             '合法的仓库内路径不能因为拼写漂移被拒绝')
        self.assert_drifted(drift)
        with mock.patch('os.path.realpath', new=SpellingDrift(plain=[self.root])), \
                mock.patch('project_memory.common.canonical_realpath', new=plain_realpath):
            with self.assertRaises(PMError):
                ensure_inside_repo(self.root, target, '写入路径')

    def test_repo_internal_link_is_still_accepted(self):
        target_dir = self.root / 'scratch-locks'
        target_dir.mkdir()
        self.locks.parent.mkdir(parents=True)
        dir_link(target_dir, self.locks)
        expected = _lock_path_for(self.record)[0].name
        drift = SpellingDrift()
        with mock.patch('os.path.realpath', new=drift):
            with record_lock(self.record, timeout=1.0, label='拼写'):
                pass
        self.assert_drifted(drift)
        self.assertEqual(sorted(item.name for item in target_dir.glob('*.lock')), [expected],
                         '仓库内链接的锁目录仍应可用，且仍只用一把锁')
        self.assertEqual(fingerprint(self.outside), {'files': {}, 'dirs': []})

    def test_escape_is_still_refused_when_the_spelling_drifts(self):
        victim = self.outside / 'docs_target'
        victim.mkdir()
        kind = dir_link(victim, self.root / 'docs')
        before = fingerprint(self.outside)
        drift = SpellingDrift()
        with mock.patch('os.path.realpath', new=drift):
            with self.assertRaises(PMError) as ctx:
                ensure_inside_repo(self.root, self.root / 'docs' / 'a.md', '写入路径')
        self.assert_drifted(drift)
        self.assertIn(kind, ('junction', 'symlink'))
        self.assertIn('仓库之外', str(ctx.exception), '拒绝理由必须是越界，不是拼写')
        self.assertEqual(fingerprint(self.outside), before, '归一化不能把越界写成放行')


class BootstrapBoundaryTest(unittest.TestCase):
    """案例 C / D：init 与 sync_tooling 写入仓库之外。"""

    def setUp(self):
        self.root = claim_tree(self, make_repo())
        self.outside = claim_tree(self, make_temp_tree('pm-bound-outside-'))

    def test_init_refuses_linked_docs_root(self):
        dir_link(self.outside, self.root / 'docs')
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            init(self.root, 'none', 'docs', 'full')
        self.assertEqual(fingerprint(self.outside), before, 'init 不能在仓库外新建目录或文件')

    def test_init_refuses_linked_tooling_dir(self):
        (self.root / '.project-memory').mkdir()
        dir_link(self.outside, self.root / '.project-memory' / 'tooling')
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            init(self.root, 'none', 'doc/new_doc', 'overlay')
        self.assertEqual(fingerprint(self.outside), before)

    def test_sync_tooling_refuses_linked_target_and_keeps_user_file(self):
        (self.root / '.project-memory').mkdir()
        target = self.root / '.project-memory' / 'tooling'
        dir_link(self.outside, target)
        planted = self.outside / 'project_memory' / 'common.py'
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text('用户的真实文件，不能被覆盖', encoding='utf-8')
        before = fingerprint(self.outside)
        with self.assertRaises(PMError):
            sync_tooling(self.root, write=True)
        after = fingerprint(self.outside)
        self.assertEqual(after, before, 'sync_tooling 既不能越界写，也不能覆盖已有文件')
        self.assertEqual(planted.read_text(encoding='utf-8'), '用户的真实文件，不能被覆盖')

    def test_init_and_sync_still_work_in_a_normal_repo(self):
        report = init(self.root, 'none', 'docs', 'full',
                      mirror_roots=['pro2/docs'], legacy_roots=['doc/_legacy'])
        self.assertTrue((self.root / 'docs' / 'CURRENT_STATE.md').is_file())
        self.assertTrue((self.root / 'docs' / 'decisions' / 'README.md').is_file())
        self.assertIn('.project-memory/tooling/project_memory/common.py', report['created'])
        sync = sync_tooling(self.root, write=True)
        self.assertEqual(sync['extra'], [])
        rel = create_document(self.root, 'DOC-OK', '正常文档', 'canonical', 'draft', 'team',
                              'docs/topics/ok.md')['path']
        self.assertEqual(rel, 'docs/topics/ok.md')
        rel = create_adr(self.root, '正常决策', 'topic', 7, '方案', '理由', 'team')
        self.assertTrue(rel.startswith('docs/decisions/ADR-0001-'))
        overlay = claim_tree(self, make_repo())
        init(overlay, 'none', 'doc/new_doc', 'overlay')
        self.assertFalse((overlay / 'docs').exists())
        self.assertTrue((overlay / '.project-memory' / 'config.json').is_file())


if __name__ == '__main__':
    unittest.main()

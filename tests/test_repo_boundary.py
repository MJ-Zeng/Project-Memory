"""Repository-boundary regression tests for document, ADR, init and tooling writes.

Every case runs inside a throwaway ``tempfile.mkdtemp()`` repository with a
separate outside directory.  No real workspace is used as a test target.

Baseline behaviour (before the fix): ``create_adr()`` ran ``mkdir`` on the
configured ``adr_dir`` and wrote through it before ``relpath()`` could complain,
and ``init()``/``sync_tooling()`` followed linked parents outside the repository.
``relpath()`` only judges *after* the write, so it never prevented the escape.
These tests assert the two things the fix must guarantee: the write is refused
before it happens, and the outside directory is byte-for-byte untouched.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory.bootstrap import init, sync_tooling
from project_memory.common import PMError
from project_memory.knowledge import create_adr, create_document, load_config

IS_WIN = sys.platform == 'win32'


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
        self.root = make_repo()
        self.outside = Path(tempfile.mkdtemp(prefix='pm-bound-outside-'))
        self.addCleanup(shutil.rmtree, self.outside, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

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
        """盘符路径：Windows 上越界写、POSIX 上留下 C: 目录，两边都必须在写入前拒绝。"""
        target = Path('C:/pm-boundary-drive')
        shutil.rmtree(target, ignore_errors=True)
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        write_config(self.root, adr_dir='C:/pm-boundary-drive/decisions')
        with self.assertRaises(PMError):
            create_adr(self.root, '盘符', 'topic', 1, '方案', '理由', 'team')
        self.assertFalse(target.exists(), '带盘符的配置不能在仓库外创建目录')
        stray = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                       if p.name.startswith('C:'))
        self.assertEqual(stray, [], '带盘符的配置不能在仓库里留下 C: 目录')

    def test_unc_style_adr_dir(self):
        self.assert_refused('//server/share/decisions')

    def test_mixed_separator_traversal(self):
        self.assert_refused('docs\\..\\' + self.outside.name + '\\decisions')

    def test_roots_cannot_escape_either(self):
        # v0.3 配置只有这三类根数组；上游的 frozen_roots/evidence_roots 尚不存在。
        for key in ('doc_roots', 'mirror_roots', 'legacy_roots'):
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
        self.root = make_repo()
        self.outside = Path(tempfile.mkdtemp(prefix='pm-bound-outside-'))
        self.addCleanup(shutil.rmtree, self.outside, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
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


class BootstrapBoundaryTest(unittest.TestCase):
    """案例 C / D：init 与 sync_tooling 写入仓库之外。"""

    def setUp(self):
        self.root = make_repo()
        self.outside = Path(tempfile.mkdtemp(prefix='pm-bound-outside-'))
        self.addCleanup(shutil.rmtree, self.outside, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

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
        overlay = make_repo()
        self.addCleanup(shutil.rmtree, overlay, ignore_errors=True)
        init(overlay, 'none', 'doc/new_doc', 'overlay')
        self.assertFalse((overlay / 'docs').exists())
        self.assertTrue((overlay / '.project-memory' / 'config.json').is_file())


if __name__ == '__main__':
    unittest.main()

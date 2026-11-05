"""Cross-process consistency for shared read-modify-write records.

These tests pin the property that was missing before the fix: the revision check
in ``coordination._mutate()`` and the hash chain in the audit ledger are only
correct when load -> mutate -> re-check -> replace cannot interleave with another
*process*.  Two threads inside one interpreter are never used as evidence of a
cross-process property.

Deterministic construction, no random sleeps: a ``Barrier`` is met inside the
critical section.  Without a mutex both processes reach it, so both read the same
revision and the second write silently discards the first.  With a mutex only the
lock owner gets there; its wait expires after ``MEET_TIMEOUT`` seconds, the
barrier breaks, and the other process is released into the record it should have
seen in the first place.

One more cross-process hazard lives on the same path and is Windows-only:
``os.replace`` is refused with ``PermissionError`` while another process still has
the record open for reading, so ``atomic_replace`` retries inside a bounded
deadline.  ``test_a_concurrent_reader_does_not_defeat_the_writer`` applies that
pressure on purpose.
"""
import json
import multiprocessing
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from project_memory.common import PMError, record_lock
from project_memory.coordination import (_append_audit_entry, _goal_path, _mutate,
                                         _read_audit_entries, add_goal_evidence, audit_migrate,
                                         audit_verify, create_goal, load_goal)

MEET_TIMEOUT = 1.0
GOAL = 'G-RACE'
CRITERION = 'C1'
AUDIT_LEDGER = '.project-memory/audit/verification_attempts.jsonl'
TEMP_PREFIX = 'pm-race-'


def _git(repo: Path, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


def _remove_with_one_retry(action, path: str) -> None:
    """Git writes loose objects read-only, so the first removal can raise
    ``PermissionError`` on Windows; clear the bit and retry once, then propagate."""
    try:
        action(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        action(path)


def _delete_tree(root: Path) -> None:
    if not root.exists():
        return
    with os.scandir(root) as scan:
        entries = sorted(scan, key=lambda item: item.name)
    for entry in entries:
        if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_reparse_tag', 0):
            # A link entry is removed as an entry; its target is never followed.
            # Windows junctions answer to rmdir, and rmdir on a reparse point
            # removes the point itself rather than the directory behind it.
            try:
                _remove_with_one_retry(os.unlink, entry.path)
            except OSError:
                _remove_with_one_retry(os.rmdir, entry.path)
        elif entry.is_dir(follow_symlinks=False):
            _delete_tree(Path(entry.path))
        else:
            _remove_with_one_retry(os.unlink, entry.path)
    _remove_with_one_retry(os.rmdir, str(root))


def remove_owned_temp_tree(root: Path) -> None:
    """Delete the tree this case created — and only that tree.

    The old cleanup was ``shutil.rmtree(self.root, ignore_errors=True)``, which
    hid a real failure: the read-only git objects above made every run leak a
    half-deleted repository instead of reporting anything.  Removal here is
    recursive, link entries (POSIX symlinks, Windows junctions) are dropped as
    entries so their targets are never followed or deleted, and a failure after
    the single retry propagates rather than being swallowed.
    """
    if not root.name.startswith(TEMP_PREFIX):
        raise AssertionError(f'拒绝清理不是本测试创建的目录：{root}')
    if Path(tempfile.gettempdir()).resolve() not in root.resolve().parents:
        raise AssertionError(f'拒绝清理临时目录之外的路径：{root}')
    _delete_tree(root)


def _meet(barrier) -> bool:
    """Rendezvous inside the critical section; False when nobody else was there."""
    try:
        barrier.wait(timeout=MEET_TIMEOUT)
    except threading.BrokenBarrierError:
        return False
    return True


def _runner(worker, args, queue):
    """Report failures as data: a crashed process must not look like a clean run."""
    try:
        queue.put(('ok', worker(args)))
    except BaseException as exc:  # noqa: BLE001 - re-raised in the parent
        queue.put(('error', f'{type(exc).__name__}: {exc}'))


def run_processes(worker, arg_sets, ctx=None, join_timeout=90):
    """Start one real process per argument set and return their results in order."""
    ctx = ctx or multiprocessing.get_context(None)
    queue = ctx.Queue()
    processes = [ctx.Process(target=_runner, args=(worker, args, queue)) for args in arg_sets]
    for process in processes:
        process.start()
    collected = [queue.get(timeout=join_timeout) for _ in arg_sets]
    for process in processes:
        process.join(join_timeout)
        assert not process.is_alive(), '子进程未在限定时间内结束'
    errors = [detail for kind, detail in collected if kind == 'error']
    assert not errors, f'子进程失败：{errors}'
    return [detail for _, detail in collected]


def mutate_worker(args):
    """One process, one legal update of the same goal record."""
    root, ref, barrier = args
    path = _goal_path(Path(root), GOAL)

    def mutate(record):
        record['met'] = _meet(barrier)
        record.setdefault('evidence_refs', []).append(ref)
        return record

    _mutate(path, mutate)
    return load_goal(Path(root), GOAL)


def evidence_worker(args):
    """Public API fan-out: only the real code path, no rendezvous."""
    root, sha = args
    outcome = add_goal_evidence(Path(root), GOAL, CRITERION, 'commit', sha)
    return outcome['goal']['revision']


def fanout_worker(args):
    """Release every process at the same moment, then use the public API."""
    root, sha, barrier = args
    barrier.wait(timeout=30)
    return evidence_worker((root, sha))


def audit_worker(args):
    """Two processes append to the hash-chained audit ledger."""
    root, token, barrier = args
    repo = Path(root)

    def read_with_rendezvous(path):
        entries = _read_audit_entries(path)
        _meet(barrier)
        return entries

    with mock.patch('project_memory.coordination._read_audit_entries', read_with_rendezvous):
        _append_audit_entry(repo, {'action': 'race', 'token': token})
    return token


def ledger_worker(args):
    """Migration rewrites the whole ledger, so it must serialise behind an append.

    The rendezvous sits inside the critical section (the same technique as
    ``mutate_worker``): with the mutex the second writer is kept out and nobody
    meets anybody, without it both read the same ledger and both meet.
    """
    root, mode, token, barrier = args
    repo = Path(root)
    real_read = _read_audit_entries
    seen = {}

    def read_with_rendezvous(path):
        entries = real_read(path)
        seen.setdefault('met', _meet(barrier))
        return entries

    with mock.patch('project_memory.coordination._read_audit_entries', read_with_rendezvous):
        if mode == 'migrate':
            result = audit_migrate(repo)
            outcome = {'mode': mode, 'changed': result['changed'], 'entries': result['entries']}
        else:
            _append_audit_entry(repo, {'action': 'race', 'token': token})
            outcome = {'mode': mode, 'token': token}
    outcome['met'] = seen.get('met')
    return outcome


def lock_probe_worker(args):
    """Try a record the parent already holds, then an unrelated record."""
    root, target, timeout = args
    outcome = {}
    try:
        with record_lock(Path(target), timeout=timeout, label='探针'):
            outcome['acquired'] = True
    except PMError as exc:
        outcome['acquired'] = False
        outcome['error'] = str(exc)
    other = _goal_path(Path(root), 'G-OTHER')
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text('{}', encoding='utf-8')
    try:
        with record_lock(other, timeout=timeout, label='探针'):
            outcome['other_acquired'] = True
    except PMError as exc:
        outcome['other_acquired'] = False
        outcome['other_error'] = str(exc)
    return outcome


def hammer_reader_worker(args):
    """Read the record in a tight loop until the parent says stop.

    On Windows a reader that still holds the file open makes the writer's
    ``os.replace`` fail with ``PermissionError`` (WinError 5).  This worker exists
    to apply that pressure at its maximum, so the retry in ``atomic_replace`` is
    exercised rather than assumed.  ``ready`` is set after the first successful
    read, which is how the writer learns the pressure is actually on — no sleeps.
    """
    path, stop, ready = args
    started = time.monotonic()
    reads = denied = 0
    announced = False
    while not stop.is_set():
        try:
            with open(path, encoding='utf-8') as handle:
                handle.read()
            reads += 1
            if not announced:
                announced = True
                ready.set()
        except (PermissionError, FileNotFoundError):
            denied += 1
    return {'reads': reads, 'read_denied': denied,
            'seconds': round(time.monotonic() - started, 2)}


class RecordLockRaceTest(unittest.TestCase):
    """问题一：多 Agent 并发更新可能丢失记录。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        _git(self.root, 'init', '-q')
        _git(self.root, 'config', 'user.email', 'test@example.invalid')
        _git(self.root, 'config', 'user.name', 'Test')
        (self.root / 'README.md').write_text('hello', encoding='utf-8')
        _git(self.root, 'add', 'README.md')
        _git(self.root, 'commit', '-qm', 'first commit')
        create_goal(self.root, GOAL, '并发一致性', '背景', '结果', 'team', ['必须通过测试'])
        self.shas = []
        for index in range(4):
            _git(self.root, 'commit', '--allow-empty', '-qm', f'evidence {index}')
            self.shas.append(subprocess.run(['git', '-C', str(self.root), 'rev-parse', 'HEAD'],
                                             capture_output=True, text=True).stdout.strip())

    def tearDown(self):
        remove_owned_temp_tree(self.root)

    def test_two_processes_updating_one_goal_lose_nothing(self):
        barrier = multiprocessing.Barrier(2, timeout=MEET_TIMEOUT * 10)
        args = [(str(self.root), f'cd000{index}' + '0' * 8, barrier) for index in (1, 2)]
        results = run_processes(mutate_worker, args)
        goal = results[-1]
        self.assertEqual(sorted(goal['evidence_refs']), ['cd000100000000', 'cd000200000000'])
        self.assertEqual(goal['revision'], 3, '两次成功更新必须体现为两次 revision 递增')
        self.assertFalse(goal['met'], '第二个写入者不应在临界区里遇到另一个进程')

    def test_public_api_fanout_keeps_every_update(self):
        ctx = multiprocessing.get_context(None)
        barrier = ctx.Barrier(4, timeout=30)
        args = [(str(self.root), sha, barrier) for sha in self.shas]
        revisions = run_processes(fanout_worker, args, ctx)
        goal = load_goal(self.root, GOAL)
        refs = [item['ref'] for item in goal['success_criteria'][0]['evidence']]
        self.assertEqual(sorted(refs), sorted(self.shas))
        self.assertEqual(goal['revision'], 5)
        self.assertEqual(sorted(revisions), [2, 3, 4, 5])

    def test_a_concurrent_reader_does_not_defeat_the_writer(self):
        """Windows 上「有人只是在读」也能让写入者的改名被拒（WinError 5）。

        读取进程把同一份记录循环打开到父进程确认它已经在跑（``ready`` 事件，不靠
        睡眠），父进程随后连着做 4 次真实更新。没有 ``atomic_replace`` 里的有界重试时，
        改名会直接抛 ``PermissionError``；有重试时四次更新全部落地、revision 连续、
        引用一条不少。读取计数也必须远大于零，否则这条测试什么都没压到。
        """
        path = _goal_path(self.root, GOAL)
        ctx = multiprocessing.get_context(None)
        stop = ctx.Event()
        ready = ctx.Event()
        queue = ctx.Queue()
        reader = ctx.Process(target=_runner,
                             args=(hammer_reader_worker, (str(path), stop, ready), queue))
        reader.start()
        try:
            self.assertTrue(ready.wait(timeout=60), '读取进程没有开始读记录')
            revisions = [add_goal_evidence(self.root, GOAL, CRITERION, 'commit', sha)['goal']['revision']
                         for sha in self.shas]
        finally:
            stop.set()
            kind, pressure = queue.get(timeout=60)
            reader.join(30)
        self.assertEqual(kind, 'ok', pressure)
        self.assertGreater(pressure['reads'], 100, f'读取进程没有形成压力：{pressure}')
        self.assertEqual(revisions, [2, 3, 4, 5], '读者的共享占用不能把更新挤掉')
        goal = load_goal(self.root, GOAL)
        refs = [item['ref'] for item in goal['success_criteria'][0]['evidence']]
        self.assertEqual(sorted(refs), sorted(self.shas))

    def test_concurrent_audit_append_keeps_the_chain_valid(self):
        _append_audit_entry(self.root, {'action': 'seed', 'token': 'seed'})
        barrier = multiprocessing.Barrier(2, timeout=MEET_TIMEOUT * 10)
        args = [(str(self.root), f'token-{index}', barrier) for index in (1, 2)]
        tokens = run_processes(audit_worker, args)
        entries = [json.loads(line) for line in
                   (self.root / AUDIT_LEDGER).read_text(encoding='utf-8').splitlines() if line]
        raced = [entry for entry in entries if entry.get('action') == 'race']
        self.assertEqual(sorted(entry['token'] for entry in raced), sorted(tokens))
        self.assertEqual([entry['seq'] for entry in entries], list(range(1, len(entries) + 1)))
        report = audit_verify(self.root)
        self.assertTrue(report['valid'], report['problems'])
        self.assertEqual(report['entries'], len(entries))

    def test_migration_and_append_on_one_ledger_serialize(self):
        """迁移整本重写账本，追加只写最后一行：两者并发时链必须仍然成立。

        屏障放在临界区里（和 ``mutate_worker`` 同一套构造）：有互斥时第二个写入者
        被挡在锁外，谁也不遇见谁，``met`` 为 False；互斥一旦摘掉，两个进程读到同一
        份账本、在屏障上相遇，``met`` 为 True，链也会被后写的那本覆盖掉。
        两种先后顺序都满足同一组不变量，所以这里不需要睡眠。
        """
        ledger = self.root / AUDIT_LEDGER
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            '{"schema_version": "1.2", "kind": "verification_attempt",'
            ' "timestamp": "2026-01-01T00:00:00Z", "outcome": "recorded", "token": "legacy-0"}\n'
            '{"schema_version": "1.2", "kind": "verification_attempt",'
            ' "timestamp": "2026-01-01T00:00:01Z", "outcome": "recorded", "token": "legacy-1"}\n',
            encoding='utf-8')
        barrier = multiprocessing.Barrier(2, timeout=MEET_TIMEOUT * 10)
        outcomes = run_processes(ledger_worker, [(str(self.root), 'migrate', '', barrier),
                                                 (str(self.root), 'append', 'cd-9', barrier)])
        self.assertEqual(sorted(item['mode'] for item in outcomes), ['append', 'migrate'])
        for item in outcomes:
            self.assertFalse(item['met'], f'{item["mode"]} 在临界区里遇见了另一个写入者')
        entries = [json.loads(line) for line in
                   ledger.read_text(encoding='utf-8').splitlines() if line]
        self.assertEqual([entry['seq'] for entry in entries], list(range(1, len(entries) + 1)),
                         '并发写入不能让 seq 重复或跳号')
        self.assertEqual({entry.get('token') for entry in entries},
                         {'legacy-0', 'legacy-1', 'cd-9'}, '追加的那条不能被迁移重写吞掉')
        report = audit_verify(self.root)
        self.assertTrue(report['valid'], report['problems'])
        self.assertEqual(report['entries'], len(entries))

    def test_lock_wait_is_bounded_and_reported(self):
        path = _goal_path(self.root, GOAL)
        outcome = {}
        with record_lock(path, label='测试'):
            outcome = run_processes(lock_probe_worker, [(str(self.root), str(path), 0.5)])[0]
        self.assertFalse(outcome['acquired'])
        self.assertIn('超时', outcome['error'])
        self.assertIn('不同进程', outcome['error'].replace('其他进程', '不同进程'))
        self.assertTrue(outcome['other_acquired'], '不同记录之间不应互相阻塞')

    def test_lock_releases_after_a_failed_write(self):
        path = _goal_path(self.root, GOAL)
        with self.assertRaises(RuntimeError):
            with record_lock(path, timeout=1.0, label='测试'):
                raise RuntimeError('写入失败')
        with record_lock(path, timeout=1.0, label='测试'):
            pass

    def test_same_record_lock_is_reentrant_in_one_thread(self):
        path = _goal_path(self.root, GOAL)
        with record_lock(path, timeout=1.0, label='外层'):
            with record_lock(path, timeout=1.0, label='内层'):
                pass

    def test_lock_sidecar_stays_in_ignored_cache(self):
        """init() already ignores .project-memory/cache/, so locks must not dirty the tree."""
        (self.root / '.project-memory' / '.gitignore').write_text('cache/\nissues/\nprs/\n',
                                                                  encoding='utf-8')
        _git(self.root, 'add', '-A')
        _git(self.root, 'commit', '-qm', 'project-memory layout')
        path = _goal_path(self.root, GOAL)
        with record_lock(path, timeout=1.0, label='测试'):
            pass
        lock_root = self.root / '.project-memory' / 'cache' / 'locks'
        self.assertTrue(list(lock_root.glob('*.lock')))
        status = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain'],
                                capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), '', f'锁文件污染了 git 工作树：{status}')


if __name__ == '__main__':
    unittest.main()

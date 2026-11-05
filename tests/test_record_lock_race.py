"""Cross-process consistency for shared read-modify-write records.

These tests pin the property that was missing before the fix: the revision check
in ``coordination._mutate()`` is only correct when load -> mutate -> re-check ->
replace cannot interleave with another *process*.  Two threads inside one
interpreter are never used as evidence of a cross-process property.

v0.3 没有审计账本（上游的 hash-chained ledger 属于后续版本），因此账本竞态
用例不在本分发内；_mutate 的竞态与锁本身的性质用例全部保留。

Deterministic construction, no random sleeps: a ``Barrier`` is met inside the
critical section.  Without a mutex both processes reach it, so both read the same
revision and the second write silently discards the first.  With a mutex only the
lock owner gets there; its wait expires after ``MEET_TIMEOUT`` seconds, the
barrier breaks, and the other process is released into the record it should have
seen in the first place.
"""
import multiprocessing
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from project_memory.common import PMError, record_lock
from project_memory.coordination import (_goal_path, _mutate, add_goal_evidence,
                                         create_goal, load_goal)

MEET_TIMEOUT = 1.0
GOAL = 'G-RACE'
CRITERION = 'C1'


def _git(repo: Path, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


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


class RecordLockRaceTest(unittest.TestCase):
    """问题一：多 Agent 并发更新可能丢失记录。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='pm-race-'))
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
        shutil.rmtree(self.root, ignore_errors=True)

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

"""B5A.1 evidence collector.

Runs the console-entry shadowing matrix against (a) the checkout native wrapper
and (b) a freshly pip-installed console command, plus the bare ``-m`` guard and
its documented residual.  Records raw stdout/stderr/exit, a structured
results.json, commands.jsonl and environment.txt.

This script records OBSERVED behaviour only.  It writes no PASS/VERIFIED verdict;
adjudication belongs to the reviewer/human.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import venv
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]
FIX = Path('C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a')
PY = sys.executable
IS_WIN = sys.platform == 'win32'
BIN = REPO / 'bin'

COMMANDS: list[dict] = []


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _env(**overrides) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
    env.pop('PYTHONPATH', None)
    env['PROJECT_MEMORY_PYTHON'] = PY
    env.update({k: str(v) for k, v in overrides.items()})
    return env


def _wrapper(args, scripts_dir: Path | None = None):
    """Native OS wrapper command.  scripts_dir=None -> checkout bin/."""
    base = scripts_dir if scripts_dir is not None else BIN
    if IS_WIN:
        return [os.environ.get('COMSPEC', 'cmd.exe'), '/c', base / 'project-memory.cmd', *args]
    return ['sh', base / 'project-memory', *args]


def _run(cmd, cwd, tag, case, malicious='', **overrides):
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=_env(**overrides),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=180)
    out = proc.stdout or ''
    err = proc.stderr or ''
    combined = out + err
    record = {
        'case': case,
        'entry': ' '.join(str(c) for c in cmd),
        'cwd': str(cwd),
        'malicious': malicious,
        'exit': proc.returncode,
        'FAKE_LAUNCHER': 'FAKE_LAUNCHER' in combined,
        'SHADOW': ('SHADOW_INIT' in combined) or ('SHADOW_MAIN' in combined),
        'real_help': '用法' in out,
        'stdout_head': out.splitlines()[0] if out.splitlines() else '',
    }
    (RUN / tag).mkdir(parents=True, exist_ok=True)
    (RUN / tag / f'{case}.out').write_text(out, encoding='utf-8')
    (RUN / tag / f'{case}.err').write_text(err, encoding='utf-8')
    (RUN / tag / f'{case}.exit').write_text(f'{proc.returncode}\n', encoding='utf-8')
    COMMANDS.append({'ts': _now(), 'case': f'{tag}/{case}', 'cmd': record['entry'],
                     'cwd': record['cwd'], 'malicious': malicious,
                     'exit': proc.returncode, 'FAKE_LAUNCHER': record['FAKE_LAUNCHER'],
                     'SHADOW': record['SHADOW'], 'real_help': record['real_help']})
    return record


def _hostile_cwd(base: Path, launcher: bool, package: bool) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    if launcher:
        shutil.copy(FIX / 'launcher-shadow' / '_project_memory_launcher.py',
                    base / '_project_memory_launcher.py')
    if package:
        shutil.copytree(FIX / 'shadow' / 'project_memory', base / 'project_memory',
                        dirs_exist_ok=True)
    return base


def checkout_matrix(tmp: Path) -> tuple[list[dict], dict]:
    res = []
    marker = tmp / 'ck.marker'
    res.append(_run(_wrapper(['--help']), tmp, 'candidate', 'normal', 'none'))
    res.append(_run(_wrapper(['--help']), tmp, 'candidate', 'pythonpath-fake-launcher',
                    f'PYTHONPATH={FIX / "launcher-shadow"}',
                    PYTHONPATH=FIX / 'launcher-shadow', B5A_MARKER=marker))
    cwd_l = _hostile_cwd(tmp / 'cwd-launcher', launcher=True, package=False)
    res.append(_run(_wrapper(['--help']), cwd_l, 'candidate', 'cwd-fake-launcher',
                    'cwd=_project_memory_launcher.py', B5A_MARKER=marker))
    res.append(_run(_wrapper(['--help']), tmp, 'candidate', 'pythonpath-fake-package',
                    f'PYTHONPATH={FIX / "shadow"}',
                    PYTHONPATH=FIX / 'shadow', B5A_MARKER=marker))
    cwd_p = _hostile_cwd(tmp / 'cwd-package', launcher=False, package=True)
    res.append(_run(_wrapper(['--help']), cwd_p, 'candidate', 'cwd-fake-package',
                    'cwd=project_memory/', B5A_MARKER=marker))
    cwd_b = _hostile_cwd(tmp / 'cwd-both', launcher=True, package=True)
    res.append(_run(_wrapper(['--help']), cwd_b, 'candidate', 'cwd-both-plus-pythonpath',
                    f'cwd=both; PYTHONPATH={FIX / "launcher-shadow"}',
                    PYTHONPATH=FIX / 'launcher-shadow', B5A_MARKER=marker))
    record = {'marker_written': marker.exists()}
    return res, record


def bare_m_matrix(tmp: Path) -> list[dict]:
    res = []
    marker = tmp / 'bare.marker'
    # guard: run from REPO with hostile PYTHONPATH -> fail closed (exit 3)
    res.append(_run([PY, '-m', 'project_memory', '--help'], REPO, 'bare',
                    'guard-pythonpath-fake-package', f'PYTHONPATH={FIX / "shadow"}',
                    PYTHONPATH=FIX / 'shadow', B5A_MARKER=marker))
    # residual: bare -m from /tmp with hostile PYTHONPATH -> shadow wins at resolve
    res.append(_run([PY, '-m', 'project_memory', '--help'], tmp, 'bare',
                    'residual-bare-pythonpath-fake-package',
                    f'PYTHONPATH={FIX / "shadow"} (unsupported entry)',
                    PYTHONPATH=FIX / 'shadow', B5A_MARKER=marker))
    return res


def installed_matrix(tmp: Path) -> tuple[list[dict], dict]:
    """Create a fresh venv, pip-install the repo, attack the installed command."""
    vroot = tmp / 'venv'
    venv.create(str(vroot), with_pip=True, symlinks=False)
    scripts = vroot / ('Scripts' if IS_WIN else 'bin')
    pyexe = scripts / ('python.exe' if IS_WIN else 'python')
    install = subprocess.run([str(pyexe), '-m', 'pip', 'install', '--disable-pip-version-check',
                              str(REPO)], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=300)
    COMMANDS.append({'ts': _now(), 'case': 'installed/pip-install',
                     'cmd': f'{pyexe} -m pip install {REPO}',
                     'exit': install.returncode,
                     'note': (install.stdout or install.stderr).strip().splitlines()[-1]
                     if (install.stdout or install.stderr).strip() else ''})
    info = {'venv': str(vroot), 'pip_exit': install.returncode,
            'scripts_dir_contents': sorted(p.name for p in scripts.iterdir()
                                           if 'project' in p.name or 'launcher' in p.name)}
    if install.returncode != 0:
        info['pip_error'] = (install.stderr or install.stdout)[-2000:]
        return [], info
    res = []
    marker = tmp / 'inst.marker'
    # installed command must NOT depend on PROJECT_MEMORY_PYTHON; use venv sibling.
    def installed_cmd(args):
        base = scripts
        if IS_WIN:
            return [os.environ.get('COMSPEC', 'cmd.exe'), '/c', base / 'project-memory.cmd', *args]
        return ['sh', base / 'project-memory', *args]

    def run_installed(case, cwd, malicious='', **over):
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
        env.pop('PYTHONPATH', None)
        env.update({k: str(v) for k, v in over.items()})
        cmd = installed_cmd(['--help'])
        proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=env,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=180)
        out, err = proc.stdout or '', proc.stderr or ''
        combined = out + err
        rec = {'case': case, 'entry': ' '.join(str(c) for c in cmd), 'cwd': str(cwd),
               'malicious': malicious, 'exit': proc.returncode,
               'FAKE_LAUNCHER': 'FAKE_LAUNCHER' in combined,
               'SHADOW': ('SHADOW_INIT' in combined) or ('SHADOW_MAIN' in combined),
               'real_help': '用法' in out,
               'stdout_head': out.splitlines()[0] if out.splitlines() else ''}
        (RUN / 'installed').mkdir(parents=True, exist_ok=True)
        (RUN / 'installed' / f'{case}.out').write_text(out, encoding='utf-8')
        (RUN / 'installed' / f'{case}.err').write_text(err, encoding='utf-8')
        (RUN / 'installed' / f'{case}.exit').write_text(f'{proc.returncode}\n', encoding='utf-8')
        COMMANDS.append({'ts': _now(), 'case': f'installed/{case}', 'cmd': rec['entry'],
                         'cwd': rec['cwd'], 'malicious': malicious, 'exit': proc.returncode,
                         'FAKE_LAUNCHER': rec['FAKE_LAUNCHER'], 'SHADOW': rec['SHADOW'],
                         'real_help': rec['real_help']})
        return rec

    res.append(run_installed('normal', tmp, 'none'))
    res.append(run_installed('pythonpath-fake-launcher', tmp,
                             f'PYTHONPATH={FIX / "launcher-shadow"}',
                             PYTHONPATH=FIX / 'launcher-shadow', B5A_MARKER=marker))
    res.append(run_installed('pythonpath-fake-package', tmp,
                             f'PYTHONPATH={FIX / "shadow"}',
                             PYTHONPATH=FIX / 'shadow', B5A_MARKER=marker))
    cwd_b = _hostile_cwd(tmp / 'inst-cwd-both', launcher=True, package=True)
    res.append(run_installed('cwd-both', cwd_b, 'cwd=both', B5A_MARKER=marker))
    info['marker_written'] = marker.exists()
    return res, info


def main() -> int:
    results: dict = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ck, ck_rec = checkout_matrix(tmp)
        results['checkout_wrapper'] = ck
        results['checkout_marker_written'] = ck_rec['marker_written']
        results['bare_m'] = bare_m_matrix(tmp)
        inst, inst_info = installed_matrix(tmp)
        results['installed_wrapper'] = inst
        results['installed_info'] = inst_info

    (RUN / 'results.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (RUN / 'commands.jsonl').open('w', encoding='utf-8', newline='\n') as fh:
        for rec in COMMANDS:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    env_lines = [
        f'collected_at: {_now()}',
        f'platform: {platform.platform()}',
        f'python: {sys.version}',
        f'executable: {PY}',
        f'repo: {REPO}',
        f'fixtures: {FIX}',
        f'is_windows: {IS_WIN}',
        '',
        '# fixture fake-launcher sha256 (raw bytes)',
        hashlib.sha256((FIX / 'launcher-shadow' / '_project_memory_launcher.py').read_bytes()).hexdigest(),
        '# fixture fake package __init__ sha256 (raw bytes)',
        hashlib.sha256((FIX / 'shadow' / 'project_memory' / '__init__.py').read_bytes()).hexdigest(),
    ]
    (RUN / 'environment.txt').write_text('\n'.join(env_lines) + '\n', encoding='utf-8')
    print('wrote results.json, commands.jsonl, environment.txt')
    print(json.dumps({k: v for k, v in results.items() if k.endswith('marker_written')},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

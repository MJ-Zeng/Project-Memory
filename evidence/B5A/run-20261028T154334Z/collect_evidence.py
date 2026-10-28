"""Summarise B5A raw outputs into the evidence JSON files."""
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
MARKERS = ('SHADOW_INIT', 'SHADOW_MAIN')


def _case(group, name):
    base = RUN / group / name
    out = (base.with_suffix('.out')).read_text(encoding='utf-8', errors='replace')
    err = (base.with_suffix('.err')).read_text(encoding='utf-8', errors='replace')
    exit_code = int((base.with_suffix('.exit')).read_text(encoding='utf-8').strip())
    return {
        'command_group': group,
        'case': name,
        'exit_code': exit_code,
        'marker_seen': any(marker in out or marker in err for marker in MARKERS),
        'help_seen': '用法' in out,
        'stdout_head': out.splitlines()[:3],
        'stderr_head': err.splitlines()[:3],
    }


def _write(name, payload):
    (RUN / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')


_write('shadow-pythonpath.json', {
    'threat': 'PYTHONPATH 中的同名 project_memory 包',
    'baseline': _case('baseline', 'shadow-pythonpath'),
    'candidate_launcher': _case('candidate', 'shadow-pythonpath-launcher'),
    'candidate_guard_bare_module': _case('candidate', 'shadow-pythonpath-guard'),
    'candidate_bare_module_residual': _case('candidate', 'shadow-pythonpath-bare'),
    'candidate_isolated_runpy': _case('candidate', 'isolated-runpy'),
})
_write('shadow-cwd.json', {
    'threat': 'cwd 中的同名 project_memory 包',
    'baseline': _case('baseline', 'shadow-cwd'),
    'candidate_launcher': _case('candidate', 'shadow-cwd-launcher'),
    'candidate_console': _case('candidate', 'shadow-console-cwd'),
})
_write('shadow-console.json', {
    'threat': 'console script + 恶意 PYTHONPATH',
    'baseline': _case('baseline', 'shadow-console'),
    'candidate_console': _case('candidate', 'shadow-console'),
})
_write('normal.json', {
    'threat': '正常调用',
    'baseline_bare_module': _case('baseline', 'normal'),
    'candidate_bare_module': _case('candidate', 'normal-bare'),
    'candidate_console': _case('candidate', 'normal-console'),
})
print('wrote shadow-pythonpath.json shadow-cwd.json shadow-console.json normal.json')

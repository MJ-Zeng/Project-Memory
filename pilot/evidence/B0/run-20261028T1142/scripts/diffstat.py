"""Write diffstat.txt for the B0.1 remediation."""
from __future__ import annotations

import subprocess
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[5]
RUN_DIR = Path(__file__).resolve().parents[1]
REVIEWED = '14cc8fcba367dc36db0706041a21f22e10e3264e'
BASELINE = '73be8e3ac4efc04c1811c122eb665344fe8ce4c3'


def git(*args: str) -> str:
    result = subprocess.run(['git', '-C', str(CODE_ROOT), *args],
                            capture_output=True, text=True, encoding='utf-8')
    return (result.stdout + result.stderr).rstrip()


def main() -> int:
    head = git('rev-parse', 'HEAD')
    sections = [
        f'HEAD: {head}',
        f'reviewed candidate: {REVIEWED}',
        f'original B0 baseline: {BASELINE}',
        '',
        f'## git diff --stat {REVIEWED}..HEAD',
        git('diff', '--stat', f'{REVIEWED}..HEAD'),
        '',
        f'## git diff --name-status {REVIEWED}..HEAD',
        git('diff', '--name-status', f'{REVIEWED}..HEAD'),
        '',
        f'## git diff --stat {BASELINE}..HEAD (cumulative B0)',
        git('diff', '--stat', f'{BASELINE}..HEAD'),
    ]
    text = '\n'.join(sections) + '\n'
    (RUN_DIR / 'diffstat.txt').write_text(text, encoding='utf-8', newline='\n')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Assemble the B3 evidence pack from matrix.json (PM-03 reviewer).

Writes LF-only text so the manifest matches the bytes stored in git.
"""
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
REPO = WS
FIX = Path('C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures')
MATRIX = json.loads((HERE / 'matrix.json').read_text(encoding='utf-8'))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wtext(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8', newline='\n')


def clip(text, n=4000):
    text = text or ''
    return text if len(text) <= n else text[:n] + '...<truncated>'


def walk_commands(node, case=''):
    if isinstance(node, dict):
        if 'command' in node and 'exit' in node:
            yield case, node
            return
        for key, value in node.items():
            yield from walk_commands(value, f'{case}.{key}' if case else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_commands(value, f'{case}[{index}]')


def main():
    rows = []
    for case, cmd in walk_commands(MATRIX):
        rows.append({
            'case': case,
            'command': cmd['command'],
            'cwd': cmd.get('cwd'),
            'pythonpath': cmd.get('pythonpath'),
            'exit': cmd['exit'],
            'stdout_head': clip(cmd.get('stdout'), 800),
            'stderr_head': clip(cmd.get('stderr'), 800),
        })
    wtext(HERE / 'commands.jsonl',
          ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))

    wtext(HERE / 'new-record.json', json.dumps({
        'description': 'AC-1/AC-2: new stable-digest record, evidence then evaluate',
        'case': MATRIX['new_record']}, ensure_ascii=False, indent=2))

    wtext(HERE / 'legacy-b2.json', json.dumps({
        'description': 'AC-3: legacy full-digest B2 record, candidate vs baseline',
        'candidate': MATRIX['legacy_b2'],
        'baseline': MATRIX['legacy_b2_baseline']}, ensure_ascii=False, indent=2))

    wtext(HERE / 'negative.json', json.dumps(
        MATRIX['negative'], ensure_ascii=False, indent=2))

    wtext(HERE / 'b2-regression.json', json.dumps({
        'forged_and_positive': MATRIX['b2_forged'],
        'binding_tamper': MATRIX['binding_tamper']}, ensure_ascii=False, indent=2))

    diff = subprocess.run(['git', '-C', str(REPO), 'diff', '--stat',
                           '832f2710..19bba33'], capture_output=True, text=True,
                          encoding='utf-8').stdout
    names = subprocess.run(['git', '-C', str(REPO), 'diff', '--name-status',
                            '832f2710..19bba33'], capture_output=True, text=True,
                           encoding='utf-8').stdout
    wtext(HERE / 'diffstat.txt', diff + '\n--name-status--\n' + names)

    entries = []
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.name != 'sha256sums.txt':
            entries.append((sha(path), path.name))
    fixture_files = [
        FIX / 'b2/new-stable/repo/.project-memory/verifications/325/VER-B3-new-stable.json',
        FIX / 'b2/definition-change/repo/.project-memory/verifications/325/VER-B3-definition-change.json',
        FIX / 'b2/genuine-trusted/repo/.project-memory/verifications/325/VER-B2-genuine-trusted.json',
        FIX / 'b2/genuine-trusted/repo/.project-memory/goals/G-B2.json',
        FIX / 'b2/new-stable/repo/.project-memory/goals/G-B3.json',
        FIX / 'b2/definition-change/repo/.project-memory/goals/G-B3.json',
    ]
    fixture_lines = [f'{sha(p)}  fixtures/{p.relative_to(FIX).as_posix()}'
                     for p in fixture_files]
    body = '\n'.join(f'{digest}  evidence/B3/{HERE.name}/{name}'
                     for digest, name in entries)
    body += '\n\n# fixture source files (read-only inputs)\n' + '\n'.join(fixture_lines) + '\n'
    wtext(HERE / 'sha256sums.txt', body)
    print(f'assembled {len(rows)} command rows')


if __name__ == '__main__':
    main()

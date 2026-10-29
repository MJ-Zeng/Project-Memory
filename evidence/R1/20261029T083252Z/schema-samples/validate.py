"""Validate R1 schema samples against skill/project-memory/assets/audit-ledger.schema.json."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
schema_path = ROOT / 'skill/project-memory/assets/audit-ledger.schema.json'
schema = json.loads(schema_path.read_text(encoding='utf-8'))
validator = Draft202012Validator(schema)
here = Path(__file__).resolve().parent
failures = []

entries = [json.loads(line) for line in
           (here / 'audit-entries.jsonl').read_text(encoding='utf-8').splitlines()
           if line.strip()]
r1_entry = json.loads((here / 'audit-entry-r1-refusal.json').read_text(encoding='utf-8'))
errors = sorted(validator.iter_errors(r1_entry), key=lambda e: e.path)
print('R1 refusal audit entry: ' + ('valid' if not errors else f'{len(errors)} error(s)'))
failures.extend(f'R1 refusal entry: {error.message}' for error in errors)
for index, entry in enumerate(entries, 1):
    errors = sorted(validator.iter_errors(entry), key=lambda e: e.path)
    print(f'audit entry seq={entry.get("seq", index)}: '
          + ('valid' if not errors else f'{len(errors)} error(s)'))
    failures.extend(f'entry {index}: {error.message}' for error in errors)

for name in ('checkpoint-head.json', 'checkpoint-request.json'):
    record = json.loads((here / name).read_text(encoding='utf-8'))
    errors = sorted(validator.iter_errors(record), key=lambda e: e.path)
    print(f'{name}: ' + ('valid' if not errors else f'{len(errors)} error(s)'))
    failures.extend(f'{name}: {error.message}' for error in errors)

print(f'checked {len(entries)} B4 audit entries + 1 R1 refusal entry + 2 checkpoint records; '
      f'{len(failures)} problem(s)')
raise SystemExit(1 if failures else 0)

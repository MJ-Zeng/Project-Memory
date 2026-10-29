#!/usr/bin/env python3
"""Marker command for B5B isolation proofs.

Writes ``marker`` to the path given as argv[1].  If the filesystem at that path
is the host filesystem the marker appears; if the path is masked by the sandbox
the write fails.  Kept dependency-free so it runs under both the host
interpreter and the WSL sandbox interpreter.
"""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print('usage: marker-command.py <marker-path>', file=sys.stderr)
    raise SystemExit(2)

target = Path(sys.argv[1])
try:
    target.write_text('marker', encoding='utf-8')
except OSError as exc:
    print(f'marker-write-failed: {exc}', file=sys.stderr)
    raise SystemExit(1)
print(f'marker-written: {target}')

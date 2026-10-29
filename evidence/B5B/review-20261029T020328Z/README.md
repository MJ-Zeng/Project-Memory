# B5B independent review evidence

- Reviewer: PM-03 independent session
- Run: `review-20261029T020328Z`
- Candidate: `89a14af60a0d4fa30ded850af610ee80ad7e9915`
- Base: `bb536ec1ff67a855e9207cc59de53851a0722f60`

## Files

- `*.out` / `*.err`: raw stdout/stderr captured from the real CLI.
- `*.json`: reviewer-derived summaries (labels say `source`); for
  `trusted-unavailable.json` the verbatim CLI payload is under `cli_payload`.
- `receipts/<scenario>/`: receipt, run log and attestation copied from the
  throwaway repo's `.project-memory` created during the run.
- `pytest.log`: full `pytest tests -v` on the candidate worktree.
- `pytest-root-collection-{base,candidate}.log`: full-root collection error,
  identical on base and candidate (pre-existing duplicate probe basenames).
- `commands.jsonl`: reviewer commands with exit codes.
- `environment.txt`, `diffstat.txt`, `sha256sums.txt`.

## Reproduction notes

- Candidate code was imported with `PYTHONPATH=<b5b-candidate>`; commands ran
  against a throwaway git repo outside the candidate worktree.
- Interpreter: `C:/SoftWare/Anconda/python.exe` (the PATH `python` is a
  WindowsApps stub).
- Host marker paths are Windows absolute paths; trusted host attempts use the
  corresponding `/mnt/c/...` path, which is masked inside the namespace.
- The first explicit-local attempt used an MSYS `/c/...` path by mistake; that
  run exited 2, its receipts were discarded, and the scenario was rerun with
  Windows paths. No stray host files were created.
- No keys, tokens or other project data are included.

# B3 review evidence — review-20261028T143901Z

Independent reproduction by PM-03 for candidate `19bba33` (PR #18), base `832f2710`.

Start with `../REVIEW-B3.md` (on branch `review/b3-19bba33`). Raw data:

- `matrix.json` — every command, exit code, stdout/stderr; record hashes before/after.
- `new-record.json`, `legacy-b2.json`, `negative.json`, `b2-regression.json` — case views.
- `pytest.log`, `pytest-b3-b2.log` — regression.
- `environment.txt` — host, versions, anchor metadata, fixtures.
- `sha256sums.txt`, `diffstat.txt`, `commands.jsonl`.

Reproduce: WSL as uid 1000, fixtures copied to `/tmp` per case,
`PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json`,
`PYTHONPATH=<repo>/.pilot/b3-candidate`, then `python3 run_matrix.py`.

No private key bytes, tokens, or other project data are stored here.

`sha256sums.txt` hashes the **git blob bytes (LF)**, not a Windows CRLF
checkout. Verify with `git show HEAD:<path> | sha256sum` (or from a
`core.autocrlf=false` checkout); fixture lines are hashed from the read-only
fixture tree.

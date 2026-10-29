#!/usr/bin/env python3
"""Independent PM-03 recheck of the B5B 42-item manifest.

For each manifest entry compares three byte-equivalent representations:
  1) raw worktree file bytes
  2) LF-normalized bytes (CRLF -> LF only; lone CR untouched)
  3) git blob bytes (git cat-file blob HEAD:<path>)
A file passes if any representation matches the manifest hash.
Also reports NUL counts/sizes for the two run.log files and environment.txt
size, and extra variants for the single miss.
"""
import hashlib
import subprocess
import sys

ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
RUN = "evidence/B5B/run-20261029T015035Z"
MAN = ROOT + "/" + RUN + "/sha256sums.txt"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def blob(path):
    return subprocess.check_output(["git", "cat-file", "blob", "HEAD:" + path], cwd=ROOT)


rows = []
with open(MAN, "rb") as fh:
    for rawname in fh.read().split(b"\n"):
        rawname = rawname.rstrip(b"\r")
        if not rawname:
            continue
        h, name = rawname.split(b" ", 1)
        name = name.lstrip(b"*").lstrip(b"./").decode()
        data = open(ROOT + "/" + RUN + "/" + name, "rb").read()
        raw_h = sha(data)
        lf_h = sha(data.replace(b"\r\n", b"\n"))
        blob_bytes = blob(RUN + "/" + name)
        blob_h = sha(blob_bytes)
        hit = {"raw": raw_h == h.decode(), "lf": lf_h == h.decode(), "blob": blob_h == h.decode()}
        rows.append((name, h.decode(), raw_h, lf_h, blob_h, hit, data, blob_bytes))

total = len(rows)
c_raw = sum(r[5]["raw"] for r in rows)
c_lf = sum(r[5]["lf"] for r in rows)
c_blob = sum(r[5]["blob"] for r in rows)
c_any = sum(any(r[5].values()) for r in rows)
print(f"total={total}")
print(f"raw_hits={c_raw}")
print(f"lf_hits={c_lf}")
print(f"blob_hits={c_blob}")
print(f"any_hit={c_any}/{total}")
print("MISSES:")
for name, man, raw_h, lf_h, blob_h, hit, data, blob_bytes in rows:
    if not any(hit.values()):
        print(f"  {name}")
        print(f"    manifest={man}")
        print(f"    raw={raw_h}")
        print(f"    lf_norm={lf_h}")
        print(f"    git_blob_sha256={blob_h}")
        print(f"    worktree_bom={sha(b'\\xef\\xbb\\xbf' + data)}")
        print(f"    worktree_plus_lf={sha(data + b'\\n')}")
        print(f"    cr_only_norm={sha(data.replace(b'\\r', b'\\n'))}")
        oid = subprocess.check_output(["git", "rev-parse", "HEAD:" + RUN + "/" + name], cwd=ROOT, text=True).strip()
        print(f"    blob_oid={oid}")
        print(f"    size={len(data)}")
        print(f"    crlf_pairs={data.count(b'\r\n')} lone_cr={data.count(b'\r') - data.count(b'\r\n')}")

print("NUL/size of flagged logs:")
for rel in ("receipts/trusted/run.log", "receipts/trusted-host-attempt/run.log"):
    b = open(ROOT + "/" + RUN + "/" + rel, "rb").read()
    print(f"  {rel}: size={len(b)} nul={b.count(b'\x00')}")

print("Other sizes:")
for rel in ("environment.txt",):
    b = open(ROOT + "/" + RUN + "/" + rel, "rb").read()
    print(f"  {rel}: size={len(b)} nul={b.count(b'\x00')}")

#!/usr/bin/env bash
# 按 evidence/B5B/README.md 的逐文件方法复测 B5B 清单：
# 对清单每一行依次比较工作树原始字节、LF 归一化字节、git blob 字节，任一等价表示命中即通过。
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
RUN=evidence/B5B/run-20261029T015035Z
cd "$RUN" || exit 1

total=0; raw=0; lfn=0; blob=0; any=0; miss=""
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  [ -z "$line" ] && continue
  h="${line%% *}"
  p="${line#* }"
  p="${p#\*}"
  rel="${p#./}"
  total=$((total+1))
  raw_h=$(sha256sum -- "$rel" | cut -d' ' -f1)
  lf_h=$(tr -d '\r' < "$rel" | sha256sum | cut -d' ' -f1)
  blob_h=$(git cat-file blob "HEAD:$RUN/$rel" | sha256sum | cut -d' ' -f1)
  r=0; l=0; b=0
  if [ "$raw_h" = "$h" ]; then raw=$((raw+1)); r=1; fi
  if [ "$lf_h" = "$h" ]; then lfn=$((lfn+1)); l=1; fi
  if [ "$blob_h" = "$h" ]; then blob=$((blob+1)); b=1; fi
  if [ $((r+l+b)) -gt 0 ]; then
    any=$((any+1))
  else
    miss="${miss}MISS $rel
  manifest=$h
  raw=$raw_h
  lf_norm=$lf_h
  git_blob=$blob_h
"
  fi
done < sha256sums.txt

printf 'total=%s\nraw_hits=%s\nlf_hits=%s\nblob_hits=%s\nany_hit=%s/%s\n' "$total" "$raw" "$lfn" "$blob" "$any" "$total"
if [ -n "$miss" ]; then printf '%s' "$miss"; else echo "MISS: none"; fi

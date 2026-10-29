== README claims present ==
11:B5B 复核记录的现场观测是 **约 19 行 LF / 22 行 CRLF / 1 行两者都不是**，base 与候选检出结果一致。原因是证据由 Windows 上的不同步骤生成，且 `evidence/B5B/**` 没有 `text eol=lf` 属性：
23:因此不要用单一 `tr -d '\r'` 覆盖全部文件：它只能匹配“生成时就是 LF”的子集（本次 17/42）。正确做法是**逐文件按字节核对，接受生成时的任一等价表示**：
34:本次复测结果：**41/42** 项至少命中一种表示（工作树 29、LF 归一化 17、git blob 19；部分文件同时命中）。唯一三项都不命中的是 `run-20261029T015035Z/environment.txt`（清单哈希 `d4f6d19f…`）：工作树原始字节、LF 归一化、git blob 均不匹配，行尾变体、BOM、尾随换行也不命中，按上文规则属于**需人工解释项**，其清单与文件字节均保持原样。除该项外其余文件都能在某一等价表示下复现，说明证据本身没有被改写，差异只来自行尾表示；**不要为了凑 `sha256sum -c` 而重写证据或清单**。
40:- `run-20261029T015035Z/receipts/trusted/run.log`（345 字节，42 个 NUL）
41:- `run-20261029T015035Z/receipts/trusted-host-attempt/run.log`（443 字节，42 个 NUL）
== README section 2 tail ==
- `run-20261029T015035Z/receipts/trusted/run.log`（345 字节，42 个 NUL）
- `run-20261029T015035Z/receipts/trusted-host-attempt/run.log`（443 字节，42 个 NUL）

这两份日志记录的是沙箱内 `marker-command.py` 的 stdout/stderr 和 WSL 的 `localhost` 转发警告。校验时必须按**原始字节**计算 SHA-256，不要先按 UTF-8 解码或做文本替换；阅读时用 `grep -a` 或二进制查看器。它们出现在清单中，属于有意保留的原始日志。

## 3. 校验边界

- 本说明不改变任何哈希、收据或场景结论；如与 `run-20261029T015035Z/README.md` 冲突，以当时生成的 `commands.jsonl`、`*.exit`、`receipts/` 为准。
- 不重签、不重算、不删除 NUL 日志，也不把工作树规范化后的字节写回清单。
- 行尾问题只影响**自校验便利性**，不改变 B5B 的场景行为：默认拒绝、显式 local、trusted 隔离、trusted 不可用不 fallback 的结论仍由各自的退出码和收据支撑。

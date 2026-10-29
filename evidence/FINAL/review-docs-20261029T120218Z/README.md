# Evidence — PM-03 增量复核（dbc858d）

- utc=2026-10-29T12:07Z
- base `f79a85f49cbdf3d0e2804c3485c1ca630a226ec1` → candidate `dbc858d2a3cf8144b24bf9e1523a509cd93cfce6`
- 全部为本机实际命令输出（Git Bash / Windows 10.0.26300 / Python 3.12.4 Anaconda），未编辑结果文本。

| 文件 | 内容 |
|---|---|
| `00-scope-audit.txt` | 父提交、远程分支、`git diff --name-status/--numstat`、删除/重命名与禁用路径检查 |
| `01-m1-m2-m3-repro.txt` | 临时 Git 仓库内独立复现 M-1/M-2/M-3（含 D-1 manual ref 反例） |
| `02-evidence-selfcheck.txt` | 候选证据包 `sha256sum -c` 三种基准对比 + 逐文件基准分类 |
| `03-script-rerun.txt` | `verify_release_docs.sh` 在 `dbc858d` 隔离 worktree 的完整重跑与对证据包的影响 |
| `04-pytest-default.log` | 候选 worktree 默认全量 pytest（253 passed / 2 skipped） |
| `05-environment.txt` | 环境与解释器说明 |

## 为什么不附本目录的 sha256sums.txt

本目录正是用来记录“上一份清单为什么不可用”的：

- 清单若按 Windows 工作树（CRLF）字节生成，提交后 git 归一化为 LF，任何人重新检出都会失败；
- 若按提交 blob（LF）字节生成，只能等提交后才知道 blob 内容，需要第二次提交或提交后另附哈希；
- 本项目已有正解：`.gitattributes` 对 `evidence/B4/**`、`evidence/R1/**` 设 `text eol=lf`，随后按目录内字节生成清单。本目录未采用该规则，因为改 `.gitattributes` 不在本轮复核授权范围内。

复核结论见 `review/FINAL/REVIEW-FINAL-DELTA.md` §6。

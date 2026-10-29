# PR #30 增量复核评论（供 PM-01 转发）

> 本会话无 GitHub API 凭据（符合试点约定），无法直接评论；以下为待转发文本。

---

**B4 增量复核（F-1 修复）结论：PASS（仅表示 F-1 修复合格，不是 v1.0 GO）**

复核者：PM-03，独立会话 + 独立 worktree。增量候选 `e731a29`（PR #30 新 head），上轮已复核 `9fa14f8`，基线 `f7c9133`。复核分支 `review/b4-e731a29`。
报告：`review/B4/REVIEW-B4-DELTA.md`；证据：`evidence/B4/review-20261029T073425Z/`（8 文件，`sha256sum -c` 全 OK）。

**增量范围**：`git diff 9fa14f85..e731a292` 仅 `.gitattributes` 一行（`evidence/**` → `evidence/B4/**`），无代码 / 测试 / 证据字节改动。

**F-1 是否闭合（独立复现）**

| 检查 | 结果 |
|---|---|
| B5B 全 43 文件 `git hash-object --path` == `HEAD:path` | delta **43/43**；reviewed `9fa14f8` 仅 41/43（两条 NUL 日志被重写） |
| `receipts/trusted/run.log` | `d4b0a4e9…`，与清单一致 ✅ |
| `receipts/trusted-host-attempt/run.log` | `2b999512…`，与清单一致 ✅ |
| 检出后 `git status --porcelain` | 空；两条日志不再永久显示 modified |
| B4 证据 `sha256sum -c` | **22/22 OK** |

**B5B 清单失配是既有问题（不归因 B4）**
在 base / `9fa14f8` / `e731a29` 三个 worktree 分别复算 B5B 清单 42 条：记录为 LF / CRLF / 都不匹配 = **19 / 22 / 1**，三处完全一致（`environment.txt` 为 neither）。说明清单来自混合行尾工作树，任何单一检出模式都无法全匹配——这是 B5B 既有缺陷，本次修复未引入新失配。delta 把 B5B 工作树恢复到与 base 相同的匹配度。

**回归**：增量无代码改动，沿用上轮 AC 结论；`tests/test_security_b4.py` 冒烟 14 passed。

**非阻断跟进（发布前建议）**
1. B5B `sha256sums.txt` 混合行尾：重新登记（统一行尾）或在 B5B README 写明校验方法。

未 Approve、未合并、未 force push。PASS 不构成 v1.0 GO，合并由人类决定。

## PM-03 独立增量复核 — `fix/release-docs` @ `dbc858d`

**DOCS_VERDICT: FAIL（狭窄）** — 三项文档修复全部实测通过；唯一失败项是证据包自校验。不涉及代码或安全结论，修完后可复审为 PASS。

| 项目 | 结果 |
|---|---|
| 父提交 / 远程分支 | `dbc858d` 唯一父提交 `f79a85f`；`origin/fix/release-docs` = `dbc858d` |
| 范围（无夹带） | 仅 `README.md`、`docs/OPERATIONS.zh-CN.md`、`skill/project-memory/references/workflows.md`、新增 `evidence/release-docs/**`、新增 handoff；无 `.py`/测试/schema/版本/`.gitattributes`/CI；无删除或改写历史证据 |
| M-1 `test-run` 示例 | 无模式 exit 3（无收据）；`--allow-local-untrusted` exit 0，`trust=local_untrusted`、`isolation.mode=none`；两个模式同给 exit 3；警告与“二选一”说明在，未把 `--trusted` 说成默认 |
| M-2 `--approved-by` | `human-owner` exit 1；`owner@example.com` exit 0（`approval_authority=claimed_unverified`，与“仅追溯标识、不是认证”一致）；三份文档示例一致 |
| M-3 空必达集合 | 空必达 `evaluate` exit 0 + `satisfied=false` + `no_required_criteria=true`；普通未满足 exit 2；`achieved` 仍 exit 1 |
| 回归 | 253 passed / 2 skipped（默认全量，exit 0） |

### 阻断项（Medium）

**F-1 证据包 `sha256sums.txt` 无法自校验**（`evidence/release-docs/20261029T115211Z/`）

- 在候选工作树执行 `sha256sum -c sha256sums.txt`：清单自身 CRLF，24 行全部 `could not be read`。
- 去掉清单 `\r` 后：**3/24 失败**（`exit-codes.txt`、`verification.log`、`verify_release_docs.sh`）。
- 对提交 blob（仓库真实字节）校验：**13/24 失败** —— 清单混用 CRLF 工作树字节（21 条）与 LF 字节（2 条）。
- `verification.log` 的记录值 `da5bd554…` **与提交内容任何字节变体都不匹配**（提交 blob `34f5259f…`），是陈旧哈希。
- 根因：新目录未加入 `.gitattributes` 的 `text eol=lf`（`evidence/B4/**`、`evidence/R1/**` 有；两者清单分别 22/22、36/36 通过）。
- 另：重跑 `verify_release_docs.sh` 会追加 `verification.log`（86→180 行）、重写 `exit-codes.txt`，但脚本不重生成清单，重跑后失败数升到 10。

交接 §6 的“`sha256sum -c` 自校验通过”声明与提交内容不符。行为证据（退出码、pytest）经独立复现**全部属实**，未发现伪造。

### 建议修复

1. `.gitattributes` 加 `evidence/release-docs/** text eol=lf`（与 B4/R1 一致），或改为对提交 blob 字节哈希；
2. 从提交后的 LF 字节重新生成 `sha256sums.txt`，修正 `verification.log` 陈旧行；
3. `verify_release_docs.sh` 跑完重写清单，或删掉“可自校验”表述。

### Low（D-1，非本轮引入）

`workflows.md:79-81` 的 manual 证据示例 `--ref 'review:https://...'` 仍被 `APPROVAL_REF` 拒绝（exit 1），自 b1 起存在；换 `--ref '#12'` 可执行。建议顺手改。

### 边界

未运行 `--trusted`；未合并、未 Approve、未打 tag、未建 Release、未创建 PR。本结论不构成 v1.0 GO，发布决定属人类审批者。完整报告：`review/FINAL/REVIEW-FINAL-DELTA.md`；证据：`evidence/FINAL/review-docs-20261029T120218Z/`。

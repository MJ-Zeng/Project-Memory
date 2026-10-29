# REVIEW — v1.0 发布文档订正增量复核（f79a85f → dbc858d）

- 审查者：PM-03（独立会话；未读 PM-01/PM-02 聊天或终端历史）
- 日期：2026-10-29（UTC 12:07）
- 基底：`f79a85f49cbdf3d0e2804c3485c1ca630a226ec1`（已合并，最终安全复核 `4e7c919` 的对象）
- 增量候选：`dbc858d2a3cf8144b24bf9e1523a509cd93cfce6`（分支 `fix/release-docs`，已推送，无 PR）
- 复核分支：`review/release-docs-dbc858d`
- 上一轮：`review/FINAL/REVIEW-FINAL.md` @ `4e7c919`（GO-READY，附 M-1/M-2/M-3）
- 本文件只记录增量复核事实与判定；不代表人民发布批准，也不构成 v1.0 GO。

## 1. 结论

| 项目 | 结果 | 证据 |
|---|---|---|
| 父提交与远程分支 | PASS | `dbc858d` 唯一父提交为 `f79a85f`；`origin/fix/release-docs` = `dbc858d` |
| 范围审计（无夹带） | PASS | 仅 3 个文档 + 新增 evidence + 新增 handoff；无 `.py`/测试/schema/`pyproject.toml`/`CHANGELOG`/版本/`.gitattributes`/CI |
| M-1 `test-run` 示例 | PASS（实测） | 无模式 exit 3；`--allow-local-untrusted` exit 0、`local_untrusted`/`isolation.mode=none`；两个模式同时给 exit 3 |
| M-2 `--approved-by` 邮箱 | PASS（实测） | 旧值 exit 1；`owner@example.com` exit 0；“仅追溯标识、不是认证”说明存在且与 `approval_authority=claimed_unverified` 一致 |
| M-3 空必达集合 | PASS（实测） | 空必达 `evaluate` exit 0 + `satisfied=false` + `no_required_criteria=true`；普通未满足仍 exit 2；`achieved` 仍 exit 1 |
| 回归 | PASS | 默认全量 `pytest -q -p no:cacheprovider` → 253 passed / 2 skipped，exit 0 |
| **证据自校验** | **FAIL** | 见 §6：`sha256sum -c sha256sums.txt` 在候选工作树 3/24 失败；对提交 blob 13/24 失败；`verification.log` 记录值对不上任何版本的字节 |

**DOCS_VERDICT: FAIL** — 唯一失败项是证据包自校验（Medium，证据完整性，非安全、非代码）。M-1/M-2/M-3 三项文档修复本身均经独立实测确认；范围干净；回归全绿。按本轮判定规则“证据自校验失败 = FAIL”，故判 FAIL，而不是因为文档或安全结论有问题。

## 2. 范围审计

```
$ git rev-list --parents -n 1 dbc858d
dbc858d... f79a85f...
$ git ls-remote origin refs/heads/fix/release-docs
dbc858d2a3cf8144b24bf9e1523a509cd93cfce6	refs/heads/fix/release-docs
```

`git diff --name-status f79a85f..dbc858d`：29 项，全部为

- `M README.md`、`M docs/OPERATIONS.zh-CN.md`、`M skill/project-memory/references/workflows.md`
- `A evidence/release-docs/20261029T115211Z/**`（24 个文件，全部新增）
- `A tasks/release-docs-handoff-20261029T115211Z.md`

核对结果：

- 无 `.py`、`tests/**`、schema、`pyproject.toml`、`CHANGELOG.md`、版本号、`.gitattributes`、`.github/**` 改动（`grep` 过滤 `git diff --name-only` 为空）。
- `--diff-filter=DR` 为空：无删除、无重命名；`evidence/` 下无非 `A` 条目，未改写任何历史证据。
- 12 处删除行全部是三份文档内的原地替换（`git diff` 逐行核对）：README 4（本地模式注释、旧命令、`goal evaluate` 退出码句、命令表行）、OPERATIONS 3（2 处 `human-owner` 示例、`status_problems` 列表行）、workflows 5（`--dry-run` 说明、`evaluate` 说明、3 处 `human-owner` 示例）。**唯一涉及安全措辞的删除行**（“普通子进程，没有操作系统隔离；收据标记为 local_untrusted”）是被扩写，不是被删除（新文见 `README.md:91-95`）。
- 提交作者 `PM-02 Developer <pm02@pilot.invalid>`，信息只描述文档订正；未触 `project-memory-mvp`。

## 3. M-1 — README `test-run` 示例（PASS）

文档侧（`README.md:88-102`、`README.md:163`；`docs/OPERATIONS.zh-CN.md:136`）：

- 本地示例已补 `--allow-local-untrusted`，并写明“宿主本地、无隔离、不可信、仅在了解风险时使用；需要隔离时改用 `--trusted`”。
- 明确“执行模式必须二选一”，命令表改为 `(--trusted | --allow-local-untrusted)`。
- 未把 `--trusted` 描述成默认；`OPERATIONS` 仍写“默认不执行”。安全警告是加强而非削弱。

独立实测（临时 Git 仓库，`PYTHONPATH` 指向候选，解释器用绝对路径 `C:/SoftWare/Anconda/python.exe`，因本机 `python` 是 Store 桩）：

| 场景 | 命令要点 | 实测 |
|---|---|---|
| 旧示例（无模式） | `test-run --command ... --agent qoder` | exit 3；stderr 要求二选一；**receipts_after_reject=0** |
| 新示例（本地） | 追加 `--allow-local-untrusted` | exit 0；收据 `trust=local_untrusted`、`isolation.mode=none`；stderr 有“没有操作系统隔离…需要隔离时请使用 --trusted”警告 |
| 两个模式同时给 | `--allow-local-untrusted --trusted` | exit 3；“必须且只能选择一种执行模式” |

与文档描述一致（含“不建快照、不写收据”）。未运行 `--trusted`（见 §10）。

## 4. M-2 — `--approved-by` 邮箱（PASS，附 1 条 Low）

文档侧：`docs/OPERATIONS.zh-CN.md:80,85,174`、`skill/project-memory/references/workflows.md:58,81,95,99` 的示例统一改为 `owner@example.com`；新增说明“必须是邮箱格式，否则 exit 1；该值只是追溯标识，不是认证：不校验邮箱归属，也不代替 GitHub 审查或分支保护”。

独立实测：

| 场景 | 实测 |
|---|---|
| `goal transition --to approved --approved-by human-owner` | exit 1（`approved_by 必须是邮箱地址格式…`） |
| 同命令 `--approved-by owner@example.com` | exit 0；`approved_by=owner@example.com`；approvals 记录 `approval_authority=claimed_unverified` |

`claimed_unverified` 与文档“只是追溯标识，不是认证”一致。三条 workflows.md 示例（manual 证据、`approved`、`achieved`）的 `--approved-by` 已一致。

**Low（D-1，非本轮引入）**：`workflows.md:79-81` 的 manual 证据示例整体仍不可执行 —— `--ref 'review:https://...'` 被 `APPROVAL_REF`（`coordination.py:65`）拒绝（`review` 分支要求后接数字），实测 exit 1；换成 `--ref '#12'` 后同一示例 exit 0。该 `ref` 写法自 b1 起就存在，不属 M-2 的 approved-by 范围，故不改变 M-2 判定，建议顺手修正。

## 5. M-3 — 空必达集合退出码（PASS）

文档侧：`README.md:125`、`docs/OPERATIONS.zh-CN.md:151`、`skill/project-memory/references/workflows.md:68` 均新增例外说明（exit 0 + `satisfied=false` + `evaluation_status=insufficient_evidence` + `status_problems` 含 `no_required_criteria`），并要求自动化读结构化字段而非只看退出码；`OPERATIONS:185` 的 `status_problems` 列表补 `no_required_criteria`；`--strict` 明确写为“本版没有”。

独立实测（G-AUTH 置为 evaluating 后把唯一判据 `required` 改为 false）：

| 场景 | 实测 |
|---|---|
| 普通未满足 `goal evaluate` | exit 2 |
| 空必达 `goal evaluate` | exit 0；`{"satisfied": false, "evaluation_status": "insufficient_evidence", "no_required_criteria": true, "status_problems": ["no_required_criteria"], "effective_status": "evaluating", "status_trusted": null}` |
| 普通未满足 `transition --to achieved` | exit 1（`needs_review`：C1） |
| 空必达 `transition --to achieved` | exit 1（`insufficient_evidence`：无） |

实现对应 `project_memory/cli.py:470-472`。文档描述与行为逐字段一致。

## 6. 证据自校验（FAIL — F-1）

交接 §6 声称：“`cd evidence/release-docs/20261029T115211Z && sha256sum -c sha256sums.txt`（工作树字节）”。该说法在提交后的候选工作树里**不成立**，且换到任何字节基准都不成立。

实测（详见 `evidence/FINAL/review-docs-20261029T120218Z/02-evidence-selfcheck.txt`）：

1. **候选工作树**：`sha256sum -c sha256sums.txt` 直接失败（`sha256sums.txt` 自身是 CRLF，24 行文件名都带 `\r`，“24 listed files could not be read”）。
2. 去掉清单里的 `\r` 后重跑：**3/24 失败** —— `exit-codes.txt`、`verification.log`、`verify_release_docs.sh`。
3. 对**提交 blob**（`git cat-file`，即仓库真实字节）校验：**13/24 失败**（12 个文件按 CRLF 工作树字节记录，提交后为 LF；加 `verification.log`）。
4. **`verification.log` 的记录值 `da5bd554…` 与任何版本都对不上**：提交 blob(LF) `34f5259f…`、CRLF 变体 `83e1bc43…`、去尾换行、trim 变体均不匹配 —— 该行是陈旧哈希，不是换行问题。

根因与仓库自身约定冲突：

- `.gitattributes` 为 `evidence/B4/**`、`evidence/R1/**` 设了 `text eol=lf`，注释写明“试点工件按字节哈希，必须在 Windows 检出时保持 LF，避免任务卡 SHA-256 漂移”。新目录 `evidence/release-docs/**` **未加入**该规则，`git check-attr` 返回 `text/eol: unspecified`。
- 对照：`evidence/B4/20261029T031257Z/sha256sums.txt` 在其目录内 22/22 通过；`evidence/R1/20261029T083252Z/sha256sums.txt` 在仓库根 36/36 通过。新证据包是唯一一个在自己目录内都过不了的。（另注：`evidence/B5B` 存在同类历史缺陷，属既有问题，不构成本轮豁免理由。）
- 清单本身混用两种基准：21 条按 CRLF 工作树字节、`exit-codes.txt` 与 `verify_release_docs.sh` 按 LF、`verification.log` 为陈旧值。因此“按工作树字节自校验”和“按提交字节自校验”至少有一个必然失败。

影响：证据包无法从仓库独立复算；交接文档的自校验声明不实（与 M-1/M-2/M-3 同类：文档描述 ≠ 实际行为），但行为层面的证据（退出码、日志）经我独立复现全部属实，未发现伪造。

修复建议（小改，均在文档/证据范围内）：

1. 在 `.gitattributes` 增加 `evidence/release-docs/** text eol=lf`（与 B4/R1 一致），或明确改为“对提交 blob 字节”哈希；
2. 从**提交后的 LF 字节**重新生成 `sha256sums.txt`，修正 `verification.log` 的陈旧行；
3. 让 `verify_release_docs.sh` 在跑完后重写清单，或删掉“可自校验”的表述；
4. 可选：顺手修 `workflows.md:79-81` 的 manual 证据 `ref` 示例（D-1）。

## 7. 脚本可重复性（F-2，与 F-1 同因）

`verify_release_docs.sh` 在隔离 worktree（`dbc858d` detached）完整重跑：**exit 0**，10 个场景退出码与提交值一致，pytest 253 passed / 2 skipped。CRLF 检出下用 `bash` 执行无解析问题。

但它会**改写证据包而不更新清单**：`verification.log` 86 → 180 行（`tee -a` 追加），`exit-codes.txt` 被截断重写，共 10 个文件变脏；脚本全文没有 `sha256sum`，不会重生成清单。重跑后清单失败文件数从 3 升到 10（隔离 worktree 中验证）。因此该脚本在“行为可重复”上通过，在“可自校验”上不成立 —— 与 §6 是同一缺陷的两个面。

## 8. 回归

`C:/SoftWare/Anconda/python.exe -m pytest -q -p no:cacheprovider`（候选 worktree）→ **253 passed, 2 skipped in 170.59s**，exit 0（`04-pytest-default.log`）。skipped 仍为两项平台相关符号链接测试。与交接自报一致，文档改动未误触代码。

## 9. 判定

按本轮规则：

- PASS 要求“仅文档/证据/交接；三项实测修复；回归全绿；无伪造” —— 前三条满足，但“证据自校验失败”是显式 FAIL 条件。
- **FAIL** 的唯一依据是 §6/§7 的证据完整性缺陷（Medium）。未发现：夹带代码/测试/版本；示例（M-1/M-2/M-3 目标）不可执行；改成默认不安全执行或删除安全警告；伪造行为结果。
- 因此这是一个**狭窄的 FAIL**：文档修复质量本身合格，证据包需要重新生成清单后才能进入人类发布决定。修完 §6 的 1–3 项后即可复审为 PASS（无需改代码）。
- 本结论不改变 `REVIEW-FINAL.md` 的安全判断（无 Critical/High），也不构成 v1.0 GO；发布决定仍属人类审批者。

## 10. NOT VERIFIED / 边界

1. `test-run --trusted`（WSL2 隔离）未执行 —— 按约束不运行不可信代码；仅静态核对文档措辞（`README.md:97-104`、`OPERATIONS:136`）与 R1 既有结论。
2. `audit checkpoint-request --approved-by owner@example.com` 未端到端执行（需 achieved + 签名锚）；仅确认其与 `goal transition` 共用 `_approved_by_problem`（`coordination.py:796-807`），且文档说明一致。
3. 未复核 `REVIEW-FINAL` §5 的既有未验证项（生产 anchor、第二主体 ACL、POSIX 安装、WSL2 attestation 真实性等）。
4. 未联网查询 tag/Release；未合并、未 Approve、未打 tag、未建 Release、未建 PR。
5. `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量未跑（本轮无代码改动，默认全量已足以证明未误触代码）。

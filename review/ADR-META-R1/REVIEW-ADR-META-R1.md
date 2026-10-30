# ADR-META-001 窄复核报告（PM-03）

- 复核对象：`docs/adr-metadata-20261030`，变更提交 `342676478864ee91cdc9ae887fb9f34bfa3ef273`，handoff 提交 `6d2706dcb59a31996f9825b42fc988293d65cb04`
- 远端实际顶点：`f18990da5607b2f3ac6bdf905749290e353cafdb`（比派单所述多 1 个 handoff 提交，见 §9）
- 基线：`f033a6c517cfde3eebb586b07f770d94b2d2c3b7`
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；Python 3.12.4；pytest 9.2.0；解释器位于复核 worktree 之外（`review/HYGIENE-R1/venv/Scripts/python.exe`）
- 隔离方式：在 `pm-pilot-03` 克隆中 `git fetch origin docs/adr-metadata-20261030`，建立 detached worktree：`rel-base`=`f033a6c`、`rel-target`=`6d2706d`、`rel-tip`=`f18990d`；PM-02 目录未改动。
- 输入边界：PM-02 的 handoff 仅作输入，未作为本报告任一结论的依据；下列结论均对应本轮自行执行的命令与输出。
- 结论：**PASS**（附 3 项口径/流程偏差，见 §9）

---

## 1. 变更提交范围（任务卡 AC-1）

```bash
git show --format= --numstat 3426764
```

```text
7  0  docs/decisions/ADR-0001-portable-repository-identity.md
7  0  docs/decisions/ADR-0002-inprocess-signature-verifier.md
7  0  docs/decisions/ADR-0003-execution-provenance.md
7  0  docs/decisions/ADR-0004-criteria-digest.md
7  0  docs/decisions/ADR-0005-cli-bootstrap.md
7  0  docs/decisions/ADR-0006-test-run-isolation.md
7  0  docs/decisions/ADR-0007-audit-integrity.md
7 files changed, 49 insertions(+)
```

恰为 7 个 ADR 文件、+49/−0、每文件 +7/−0。父提交为 `f033a6c`，链为 `f033a6c → 3426764 → 6d2706d → f18990d`（`git rev-list --parents` 逐项确认）。

## 2. 正文零改动（任务卡 AC-2）

对每个文件执行 `tail -n +8 <target> | cmp - <baseline>`：

```text
ADR-0001-portable-repository-identity.md BODY_IDENTICAL
ADR-0002-inprocess-signature-verifier.md BODY_IDENTICAL
ADR-0003-execution-provenance.md BODY_IDENTICAL
ADR-0004-criteria-digest.md BODY_IDENTICAL
ADR-0005-cli-bootstrap.md BODY_IDENTICAL
ADR-0006-test-run-isolation.md BODY_IDENTICAL
ADR-0007-audit-integrity.md BODY_IDENTICAL
```

7/7 逐字节一致。新增块为 6 行 frontmatter + 1 行空行，位置在文件最顶部，其后紧接原有 `# ADR-000N：...`。

frontmatter 取值逐项核对（`id` / `status` / `owner` / `related_issues`），并与原正文第 5 行（插入后第 12 行）的 `Issue #N` 对照：

| 文件 | id | status | owner | related_issues | 正文 Issue |
|---|---|---|---|---|---|
| ADR-0001 | `ADR-0001` | `proposed` | `MJ-Zeng` | `[3]` | #3 |
| ADR-0002 | `ADR-0002` | `proposed` | `MJ-Zeng` | `[1]` | #1 |
| ADR-0003 | `ADR-0003` | `proposed` | `MJ-Zeng` | `[12]` | #12 |
| ADR-0004 | `ADR-0004` | `proposed` | `MJ-Zeng` | `[16]` | #16 |
| ADR-0005 | `ADR-0005` | `proposed` | `MJ-Zeng` | `[20]` | #20 |
| ADR-0006 | `ADR-0006` | `proposed` | `MJ-Zeng` | `[23]` | #23 |
| ADR-0007 | `ADR-0007` | `proposed` | `MJ-Zeng` | `[28]` | #28 |

全部与任务卡表一致，无 ADR 被升为 `accepted`。

## 3. 审计多重集（任务卡 AC-3、AC-4）

分别在 `rel-base`、`rel-target` 执行 `./bin/project-memory audit --scope current`（均 exit 0），按 `(severity, code, location)` 多重集比较（`location` 归一正斜杠）：

| 指标 | 基线 f033a6c | 目标 6d2706d |
|---|---|---|
| 总数 | 84 | 42 |
| high | 14 | 0 |
| medium | 25 | 18 |
| low | 45 | 24 |
| 新增三元组 | — | **0** |
| 减少三元组 | — | **42** |

减少项按 code 汇总，恰好为任务卡允许的五项：

| severity | code | 基线 | 目标 | 减少 |
|---|---|---|---|---|
| high | `adr_invalid_id` | 7 | 0 | 7 |
| high | `adr_invalid_status` | 7 | 0 | 7 |
| medium | `adr_missing_provenance` | 7 | 0 | 7 |
| low | `broken_adr_reference` | 14 | 0 | 14 |
| low | `unknown_document_status` | 11 | 4 | 7 |

其余 code 计数不变：

- medium：`broken_document_reference` 3、`reference_authority_mismatch` 14、`reference_outside_repository` 1；
- low：`ambiguous_reference` 14、`broken_reference` 4、`dynamic_artifact_reference` 2。

因果已独立确认（非仅采信 handoff）：

- 三个 high/medium 项的 `location` 全部是 7 个 ADR 文件，逐文件各 1 条；新增 frontmatter 后消失，且审计代码/规则未改动（变更仅 docs/decisions 与 tasks）。
- `broken_adr_reference` 14 条中 9 条位于 ADR 文件自身、5 条位于 `docs/ARCHITECTURE.zh-CN.md`、`docs/OPERATIONS.zh-CN.md`、`docs/TEST_REPORT.md`；ADR id 元数据补齐后，这些引用可解析，故全部消失。
- `unknown_document_status` 减少的 7 条全部位于 ADR 文件（原缺 `status`），剩余 4 条位于 `docs/ARCHITECTURE.zh-CN.md`、`docs/OPERATIONS.zh-CN.md`、`docs/TEST_REPORT.md`、`docs/TUTORIAL.zh-CN.md`，与任务卡“ADR 之外 4 条不处理”一致。
- ADR 正文既有 finding 多重集不变：去掉上述五类 code 后，基线与目标均为 25 条，逐条相同（`ambiguous_reference` 12、`reference_authority_mismatch` 12、`reference_outside_repository` 1）。即 AC-4 的修正口径成立。

顶点 `f18990d` 亦单独跑审计：总数 42、high 0、medium 18、low 24，与 `6d2706d` 相同。

## 4. reconcile（任务卡 AC-5）

```bash
./bin/project-memory reconcile --fail-on high   # rel-target
```

```text
EXIT=0
state: needs_attention
counts: {'high': 0, 'medium': 18, 'low': 24}
summary: {"defects": 0, "docs": {"high": 0, "low": 24, "medium": 18}, "goals": 7, "open_defects": 0, "runs": 0, "verifications": 0}
items: 42
```

exit 0、high 0，`state` 仍为 `needs_attention`（medium/low 尚存，符合任务卡预期）。未调整 `STATUS` 集合、审计规则或脚本。

## 5. 双门槛回归（任务卡 AC-6）

在 `rel-target` 内、使用 worktree 外解释器：

| 门槛 | 结果 | 耗时 | 退出码 |
|---|---|---|---|
| 默认 `pytest -q` | 253 passed, 2 skipped | 147.87s | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | 253 passed, 2 skipped | 150.76s | 0 |

2 个 skip 为既有 Windows 符号链接跳过。

## 6. 禁止路径与范围（任务卡 §3、AC-7 相关）

```bash
git diff --name-only f033a6c..6d2706d | grep -E '^(project_memory/|tests/|bin/|skill/|evidence/|\.project-memory/)'
git diff --name-only f033a6c..f18990d | grep -E '^(project_memory/|tests/|bin/|skill/|evidence/|\.project-memory/)'
```

两次均为 `NONE`。目标范围：

```text
M  docs/decisions/ADR-0001..0007*.md   (7 files, +49)
A  tasks/PM02-adr-metadata-handoff-20261030T013347Z.md  (+81)
```

顶点追加：

```text
tasks/PM02-adr-metadata-handoff-20261030T013347Z.md  +1
```

未改 `docs/decisions/README.md`、其他文档、配置、测试或脚本。未创建 Goal/Run。

## 7. 与 dev/v1.0 当前头的关系

```bash
git fetch origin dev/v1.0        # origin/dev/v1.0 = 86892b44cbce1015e43d6dcd577da0f70f26bb75
git diff --name-only f033a6c..86892b4
```

`dev/v1.0` 相对 `f033a6c` 改动 4 个文件：`.project-memory/config.json`、`docs/CURRENT_STATE.md`、`pilot/PILOT_CLOSEOUT.md`、`tasks/PM02-docs-hygiene-handoff-20261030T010538Z.md`。与本分支改动文件集合交集为空（`comm -12` 无输出），派单“文件无重叠”成立。本分支未 rebase，复核仍按 `f033a6c`。

## 8. 分支推送状态

```bash
git ls-remote origin refs/heads/docs/adr-metadata-20261030
# f18990da5607b2f3ac6bdf905749290e353cafdb
```

分支确已推送 origin（与任务卡“本地，不 push”不同；派单已注明“已推送”）。

## 9. 偏差与说明

1. **顶点与派单不一致**：派单称 handoff 提交 `6d2706d` 为分支顶点，远端实际顶点为 `f18990d`（其子提交）。差异仅 1 行：handoff 增加“基线 `f033a6c`；`dev/v1.0` 合并头 `86892b4`（PR #35），本分支未 rebase，文件无重叠”。不含 ADR/配置/代码改动；顶点审计结果与目标一致。本报告以 `6d2706d` 为验收目标，并单独核验了顶点。
2. **推送与任务卡冲突**：任务卡分支要求“不 push”，实际已推送。派单已知悉并要求复核远端分支，故不据此判 FAIL；但属流程偏差，需 PM-01 记录。
3. **任务卡基线表述过期**：任务卡写 `f033a6c` 为“`dev/v1.0` 当前头”，实际 `dev/v1.0` 已因 PR #35 前进到 `86892b4`。派单已说明复核基线仍按 `f033a6c`，且文件无重叠，不影响本次结论。
4. **任务卡 AC-4 原表述矛盾**已在 2026-10-30 由 PM-01 修正；本轮按修正口径（三类 code 归零 + 正文既有 25 条不变）复核通过。
5. 派单正文写“8 项检查”但实际列 6 项；本报告覆盖 6 项必需检查，另补顶点核验与 dev/v1.0 重叠核验两项辅助检查。

## 10. 结论

**PASS。** 六项必需检查全部由本轮独立命令复现：提交 `3426764` 恰为 7 文件 +49/−0 且每文件 +7/−0；正文 7/7 逐字节不变；审计 84/14/25/45 → 42/0/18/24、新增 0、五类减少精确匹配且因果确认；reconcile exit 0、high 0、`needs_attention`；双门槛 253/2 且 exit 0；禁止路径 0 改动、ADR 正文既有 finding 多重集不变。偏差均为流程/口径层面（§9），未发现产品代码、测试、规则或证据被改动。

本报告不构成合并批准或人类批准。是否合并、何时合并由人类决定。

**NOT VERIFIED**

- 未在 CI 中运行；仅本机独立 worktree 验证。
- 测试所用 venv 为先前复核已创建的 worktree 外解释器（未为本轮重新安装依赖）；依赖版本同前，但未重新创建干净 venv。
- 未实际执行与 `86892b4` 的合并/变基；仅按文件集合确认无重叠，未做文本级合并冲突预演。
- 未观察 PM-02 工作区实时状态；仅验证 `origin` 上取到的提交。
- 未验证提交作者身份真实性：提交未签名，`PM-02 Developer <pm02@pilot.invalid>` 仅为声明。
- 未验证 `status: proposed` 的语义正确性或 owner 选择是否应另有主体（任务卡已指定，属决策而非复核项）。
- 未在其他操作系统验证；仅 Windows 11 AMD64。

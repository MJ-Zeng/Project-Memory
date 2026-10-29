# R1 增量复核报告 — PM-03

- 审查者：PM-03（独立会话）
- 日期：2026-10-29
- 对象：增量提交 `9d5f957e65faf536be4dc763cb97d50e815bdd91`（PR #32，base `dev/v1.0`）
- 增量基底：`bb06037c469b6586b95fbcd69b6965585f2c977e`（上轮已 PASS）
- 上轮报告：`review/R1/REVIEW-R1.md` @ `9d30611`（只读参考，未修改）
- 审查分支：`review/r1-9d5f957`
- 本轮证据：`evidence/R1/review-delta-20261029T110713Z/`
- 性质：**只审这一个增量提交**。本判定不是 v1.0 GO，不合并 PR、不 Approve、不打 tag、不建 Release。

---

## 1. 提交关系与范围审计

### 1.1 对象确认

- `git fetch origin` 后 `origin/fix/release-gates` = `9d5f957`。
- `git rev-list --parents` 显示 `9d5f957` 的唯一父提交是 `bb06037`；`git rev-list --count bb06037..9d5f957` = 1。
- 提交信息：`docs(r1): correct B5B coverage count to 41/42 and note Windows python3`。
- worktree：`.pilot/r1d-base`（`bb06037`）、`.pilot/r1d-delta`（`review/r1-9d5f957`）。

### 1.2 改动文件（`git diff --name-status bb06037..9d5f957`）

| 状态 | 文件 |
|---|---|
| M | `README.md` |
| M | `docs/OPERATIONS.zh-CN.md` |
| M | `evidence/B5B/README.md` |
| A | `evidence/R1/fix-20261029T104125Z/README.md` |
| A | `evidence/R1/fix-20261029T104125Z/b5b-recheck.log` |
| A | `evidence/R1/fix-20261029T104125Z/changed-docs.sha256` |
| A | `evidence/R1/fix-20261029T104125Z/commands.jsonl` |
| A | `evidence/R1/fix-20261029T104125Z/pytest-default.log` |
| A | `evidence/R1/fix-20261029T104125Z/reproduce-b5b.sh` |
| A | `evidence/R1/fix-20261029T104125Z/sha256sums.txt` |
| A | `tasks/R1-fix1-handoff-20261029T104125Z.md` |

共 11 个文件，全部落在允许范围内（文档 + 本轮证据 + 交接）。`reproduce-b5b.sh` 位于证据目录内，是复测脚本，不参与产品/测试执行。

### 1.3 禁止项核对

- `git diff --name-only bb06037..9d5f957 -- '*.py' 'tests/**' 'schema/**' 'pyproject.toml' 'CHANGELOG.md' '.gitattributes' '.github/**' 'project_memory/**' 'skill/**'`：**空**。
- 版本文件 blob 逐项相同：`project_memory/__init__.py` `d93ec638…`、`pyproject.toml` `e7e7761d…`、`CHANGELOG.md` `c1edf05b…`；版本仍 `1.0.0`。
- 任务卡 `tasks/R1.md` blob 相同（`25d8818c…`），SHA-256 `5949420f…`，与上轮报告一致。
- `evidence/R1/20261029T083252Z/` 零改动（`git diff` 为空），其清单在仓库根自校验 **36/36 OK**。

### 1.4 B5B 历史证据零改动

- `evidence/B5B/` 共 44 个文件，base 与候选的 `git ls-tree` 逐 blob 比对：仅 `evidence/B5B/README.md` 的 blob 变化（`0b8e75b6` → `28359ba1`）。
- `evidence/B5B/run-20261029T015035Z/**` 与其余历史文件 blob 完全一致。
- `environment.txt` blob 在 base 与候选均为 `e27a17fc…`，R1 与本次订正均未改其字节（最后修改仍为 B5B 提交 `78b8394`）。

**范围结论：仅文档 + 本轮证据 + 交接，无代码/测试/schema/版本/属性/CI 夹带；历史证据未动。**

---

## 2. F1 复现（B5B 清单 41/42）

在 `.pilot/r1d-delta` 的 `evidence/B5B/run-20261029T015035Z` 下，独立执行候选自带脚本并用另一套 Python 实现交叉验证（`b5b-reproduce.log`、`f1-crosscheck.txt`），两次结果一致：

| 项 | 实测 |
|---|---|
| 清单条目 | 42 |
| 工作树原始字节命中 | 29 |
| LF 归一化命中 | 17 |
| git blob 内容命中 | 19 |
| **至少一种表示命中** | **41/42** |
| 唯一不命中 | `environment.txt` |

`environment.txt` 实测：

- 清单：`d4f6d19fab1a3cd728c44f24724fc21e17139a2ca277fcf92e3aa2c4ce88f5c3`
- 工作树原始：`44c6eba74e51fd726c607588d50f1bff5a6f6883dc495ea354cacd74fbc90a52`
- LF 归一化：`a78b12ed17ebc4c613474c1102d44b794d04c554af837f3f88318e63710246c2`
- git blob SHA-256：`a78b12ed…`（对象 id `e27a17fc7bee71aacf2888afa538772c222db463`）

额外测试 11 种变体（raw / LF / CRLF / BOM / BOM+LF / 去尾随空白 / 去尾随空白+LF / 补尾随换行 / 补换行+LF / 去末尾换行 / 去末尾换行+LF），**均不命中**清单哈希（`f1-env-variants.txt`）。因此“需人工解释项”的表述成立，不是遗漏的第三种行尾表示。

NUL 日志独立复核：`receipts/trusted/run.log` 345 字节 / 42 个 NUL；`receipts/trusted-host-attempt/run.log` 443 字节 / 42 个 NUL。

新 README 表述逐项核对（`evidence/B5B/README.md:34`）：

- `41/42`、`29/17/19`、唯一不命中 `environment.txt`、清单哈希前缀 `d4f6d19f…` —— 与实测一致；
- 明确“行尾变体、BOM、尾随换行也不命中”，归类为“需人工解释项” —— 与实测一致；
- 保留 NUL 日志 345B/42、443B/42 —— 一致；
- **保留“不要为了凑 `sha256sum -c` 而重写证据或清单”的告诫** —— 仍在；
- 未改动任何 B5B 证据文件或清单字节（见 1.4）。

---

## 3. F2 复核（Windows `python3` 说明）

- 位置：`README.md:41`、`docs/OPERATIONS.zh-CN.md:64`，均在原 `python3 -m pytest` 代码块之后新增一句，未改原命令。
- 事实核对：本机 `python3` 与 `python` 都解析到 `…/WindowsApps/*` → `AppInstallerPythonRedirector.exe`（Microsoft Store 应用执行别名）；实际解释器 `C:\SoftWare\Anconda\python.exe` 为 Python 3.12.4。说明准确。
- 是否与原 openssl 发布要求冲突：**不冲突**。发布/CI 段落原文仍要求“**必须**设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`”“skip 不等于通过”，新增句只解释解释器选择，不改变门禁语义。
- 是否需要改代码：**不需要**。这是宿主环境差异，仓库代码无缺陷；文档提示是正确的最小修复。

---

## 4. 证据自校验（`evidence/R1/fix-20261029T104125Z/`）

| 检查 | 结果 |
|---|---|
| `sha256sum -c sha256sums.txt`（5 条） | **5/5 OK**，exit 0 |
| `changed-docs.sha256` vs 工作树字节 | 3 FAILED（见下） |
| `changed-docs.sha256` vs 提交 blob（LF） | **3/3 OK**：`77076cb4…`、`d3f0a790…`、`8d04fa68…` |
| R1 历史清单（36 条，仓库根） | **36/36 OK**，exit 0 |
| 本报告证据目录自校验 | 10/10 OK |

**关于工作树 3 FAILED**：三份文档未固定 `eol=lf`，Windows `core.autocrlf=true` 检出为 CRLF（CR 字节 215/297/49），而清单按 LF 字节计算。证据 README §5 已说明该约定并给出 `git cat-file blob HEAD:<path> | sha256sum` 的复核方法；按该方法 3/3 命中。因此这是**已披露的检出表示差异**，不是证据完整性失败。

抽查 `commands.jsonl`：

- seq 6（`reproduce-b5b.sh`，exit 0，41/42、29/17/19、miss=environment.txt）：**原样复现**。
- seq 9（NUL 日志 345/42、443/42）：**原样复现**。
- seq 10（`sha256sum -c sha256sums.txt`，exit 0）：**原样复现**。
- seq 14（全量 pytest，exit 0，253 passed / 2 skipped）：本文 §5 独立复跑得到相同计数。
- seq 1（`git rev-parse HEAD` = `bb06037`）：记录时点在提交前，现已无法复现为当前 HEAD，但与“先取证、后提交”的顺序自洽，且不与其他可复现条目矛盾。

---

## 5. 回归

- 命令：`PYTHONUTF8=1 /c/SoftWare/Anconda/python.exe -m pytest -q -p no:cacheprovider`
- 结果：**253 passed, 2 skipped**，exit 0（494.07 s）；日志 `pytest-default.log`。
- 2 个 skip 均为 rc3 符号链接用例（`tests/test_security_rc3.py` 的 `skipTest('当前平台不允许创建符号链接')`）。
- 运行期间 worktree HEAD 为 `a92df4c`（见 §6）；已核验 `9d5f957..HEAD` 仅新增 `evidence/R1/review-delta-*/**`，**产品与测试代码树与 `9d5f957` 完全相同**，因此回归结果对候选代码有效。

---

## 6. 并发写入披露（非候选内容）

复核期间，`review/r1-9d5f957` 分支上出现了两个**不是我创建的**提交：

- `a92df4c` `review(r1-delta): scope audit evidence for 9d5f957`（18:57:58 +0800）
- `5dcfaff` `review(r1-delta): F1 41/42 independent reproduction`（18:59:17 +0800）

两者作者均为 `PM-03 Reviewer`，内容只有 `evidence/R1/review-delta-20261029T105055Z/**`（`git diff --name-status 9d5f957..<commit>` 可验）；其数值（41/42、29/17/19、NUL 计数、自校验）与我的独立复现一致。判断为**另一个并发 PM-03 会话**在同一 worktree/分支上的写入。

处理方式：

- 不删除、不改写、不混入该会话的提交与未跟踪文件（`f2-python3-check.txt`、`pytest-delta.log`、`selfcheck-hashes.txt` 保持未跟踪）。
- 未把该会话的产物当作复现依据；本文所有数字来自本会话独立执行。
- 本轮证据改放独立目录 `evidence/R1/review-delta-20261029T110713Z/`，避免与其目录混写。
- 披露供 PM-01 判断分支归属；若需单一会话证据，请以上述目录为准。

---

## 7. 发现

1. **Info — `changed-docs.sha256` 在 Windows 检出下无法直接 `sha256sum -c`**：清单为 LF 字节，三份文档未固定 `eol=lf`，工作树为 CRLF。证据 README §5 已给出 blob/LF 复核方法且 3/3 通过；建议未来在清单旁一行注明“Windows 用 blob 复核”，非缺陷。
2. **Info — 任务说明的清单计数与实测不符**：复核要求写“`sha256sums.txt` 应 26/26”，实际该文件为 **5 条**（5/5 OK）；历史 R1 清单为 36 条（36/36 OK）。二者都不等于 26，判断为任务说明的模板数字，不是候选缺陷。
3. **Info — 并发写入**：见 §6。

无 Medium/High 发现；无伪造或篡改迹象。

---

## 8. 判定

**DELTA_VERDICT: PASS**

理由：

- 范围仅为文档 + 本轮证据 + 交接，无代码/测试/schema/版本/属性/CI 改动；
- B5B 历史证据 44 个文件仅 README blob 变化，`environment.txt` 等字节未动；
- F1 表述（41/42、29/17/19、唯一 miss `environment.txt`、NUL 345/42 与 443/42、保留告诫）与实测一致；
- F2 表述准确，不与 openssl 发布门禁冲突，无需改代码；
- 证据自校验（5/5、3/3 blob、36/36 历史）通过；
- 默认全量回归 253 passed / 2 skipped，exit 0。

本判定是程序性增量复核，**不是**安全认证，**不是** v1.0 GO；合并、Approval、tag、Release 由人类决定。

---

## 9. NOT VERIFIED

- `python3`/`python` 别名桩的 exit 49：本会话只核验了指向 `AppInstallerPythonRedirector.exe` 的路径，**未直接执行**桩（避免拉起 Store）；exit 49 由同机并发会话证据与别名机制佐证。
- PR #32 描述/评审状态：本会话无 GitHub 凭据，未读取（上轮亦 404）。
- macOS/Linux 上的检出与 openssl 开关行为（仅 Windows）。
- 生产 anchor 的真实端到端签名（沿用上轮边界）。
- `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量套件：本次为文档订正，未复跑（上轮已验；默认全量全绿足以证明无代码漂移）。
- 远端 tag/Release 状态。

---

## 10. 污染 / 偏差 / 耗时

- **污染**：未读开发/主管会话；未修改候选；未使用 `project-memory-mvp`；未读生产 anchor/私钥；无 GitHub 凭据、未直连 API。
- **偏差**：并发 PM-03 会话写入同一分支（§6）；`python3` 退出码未直接执行（§9）。
- **耗时**：约 20 分钟静态核对 + 约 15 分钟回归等待。

# B4 增量复核报告 — F-1 修复（`.gitattributes` 收窄至 `evidence/B4/**`）

- 复核者：PM-03 独立审查者（独立会话 / 独立 worktree；未读开发或主管会话、终端历史、未提交文件）
- 复核日期：2026-10-29
- 运行 ID：`review-20261029T073425Z`
- 结论：**PASS（仅表示 F-1 修复合格；不是 v1.0 GO）**
- 本报告只覆盖 B4 增量（相对上轮已复核的 `9fa14f8`）；B4 的 AC-1..AC-12 结论沿用上轮 `REVIEW-B4.md`。

---

## 1. 对象与身份

| 项 | 值 |
|---|---|
| 基线 | `f7c91333bbc999626e87eb29555b2c7c1ccb1a8f` |
| 上轮已复核（PASS） | `9fa14f853ed1fa8f473238ca1a0765b733711d65`（`review-20261029T065012Z`） |
| 增量候选 / PR #30 新 head | `e731a292cdba232f87c6bf86948d8d6a0d32ea75` |
| 远端 `origin/fix/b4-audit-integrity` | `e731a292cdba232f87c6bf86948d8d6a0d32ea75`（fetch 后一致） |
| 任务卡 `tasks/B4.md` SHA-256 | `3fcce10bb9b03293358a4beab40c0466bd3e40b59d7c0596d7fb8086d71649eb`（工作树与 `e731a29:tasks/B4.md` 均一致，未改） |
| 祖先关系 | `9fa14f8` 是 `e731a29` 的祖先（YES）；`f7c9133` 是 `e731a29` 的祖先（YES） |
| 复核分支 | `review/b4-e731a29`（基于 `e731a29`） |
| 证据包 | `evidence/B4/review-20261029T073425Z/`（8 个文件，`sha256sum -c` 全 OK） |

候选与派发 SHA 一致，非基线后代 / 任务卡漂移等中止条件均未触发。

---

## 2. 增量范围（仅属性变更）

`git diff 9fa14f85..e731a292`：**1 个文件、1 行**。

```diff
-evidence/** text eol=lf
+evidence/B4/** text eol=lf
```

- `git diff --name-status` 仅 `M .gitattributes`；`--numstat` 为 `1 1`。
- 期间唯一提交：`e731a29 fix(b4): scope LF evidence attribute to B4 only`（PM-02 开发会话中断后由 PM-01 完成推送）。
- 无代码 / 测试 / fixture / 证据字节改动 → `ATTR_ONLY = yes`。

属性生效核对（`git check-attr`，delta worktree）：

| 路径 | `text` | `eol` |
|---|---|---|
| `evidence/B5B/.../receipts/trusted/run.log` | unspecified | unspecified |
| `evidence/B4/20261029T031257Z/sha256sums.txt` | set | lf |

即：规则现在只作用于 B4 证据，不再触达 B5B。

---

## 3. F-1 闭合验证

### 3.1 add 不重写字节（`git hash-object --path` == `HEAD:path`）

对 `evidence/B5B` 全部 **43** 个文件逐一比较：

| worktree | 提交 | 相等数 |
|---|---|---|
| base | `f7c91333` | **43 / 43** |
| reviewed（F-1 缺陷现场） | `9fa14f8` | **41 / 43** |
| delta | `e731a29` | **43 / 43** |

- reviewed 的 2 个失配正是两个 NUL 日志：
  - `receipts/trusted/run.log`：`hash-object --path` = `903404328d618047…` ≠ `HEAD` = `4f21112e6c542200…`
  - `receipts/trusted-host-attempt/run.log`：`hash-object --path` = `8769a98aad589c0f…` ≠ `HEAD` = `006890065ea2e3aa…`
- delta 上两条均恢复相等（`4f21112e…`、`00689006…`），即 `git add` 不再改变这两个文件的对象身份。
- 说明：这两个日志含 NUL（各 42 个），以 **未归一化的 CRLF 二进制 blob** 存储（`-text`）；`text eol=lf` 会对其施加 CRLF→LF clean 过滤，故在 `9fa14f8` 上被重写。规则收窄到 `evidence/B4/**` 后此过滤不再命中 B5B，F-1 闭合。

### 3.2 两个 NUL 日志字节与清单一致

delta worktree 实际 sha256：

| 文件 | 实际 sha256 | 清单记录 | 一致 |
|---|---|---|---|
| `receipts/trusted/run.log` | `d4b0a4e9ed81023666ecae81ca8f4a9c583d40a2bc783dbbb3f12cd24f9fc42c` | 同值 | ✅ |
| `receipts/trusted-host-attempt/run.log` | `2b99951295f409941be7971bb2f8378c850904cc965ebc5bf1dd4c7fb0ac2cca` | 同值 | ✅ |

另两个 `run.log`（提示词要求一并记录）：

| 文件 | 实际 sha256 |
|---|---|
| `receipts/baseline-local/run.log` | `436a73ea0bb1117f8a6b0a7297dab7e8680e1a34f811ad2877d60ccc8d4f4bfb` |
| `receipts/local-explicit/run.log` | `3e1ec1f902d2bfeab113c0b518591061a01515a2d67c368a44ddfdc72a25aa18` |

四者均与 B5B `sha256sums.txt` 的记录相等（delta 上工作树保持原始行尾，未被归一）。

### 3.3 检出后工作树干净

- delta worktree `git status --porcelain` 为空；`git diff` 为空。
- 对两个日志 `git checkout --` 重新落盘后仍为空，哈希不变（`d4b0…`、`2b99…`）→ 不再永久显示 modified。
- `git update-index --refresh` rc=0，状态仍为空。
- 对照：reviewed worktree 上这两条日志显示 `M`，`git add` 会重写（见 3.1）。

---

## 4. B4 证据完整性（沿用并复核）

`cd evidence/B4/20261029T031257Z && sha256sum -c sha256sums.txt` → **22 / 22 OK**（`b4-manifest.log`）。清单为 LF，无 CRLF 解析问题。

---

## 5. 证明 B5B 清单失配是既有问题（非 B4 失败）

B5B `sha256sums.txt` 为 **CRLF 文件、42 条记录**。对每条记录，比较其哈希与两种形式：**blob 原样（LF）** 与 **LF→CRLF 转换后的哈希**，在三个 worktree 上分别复算：

| worktree | 提交 | 记录为 LF | 记录为 CRLF | 两者都不匹配 | 与工作树匹配数 |
|---|---|---|---|---|---|
| base | `f7c91333` | 19 | 22 | 1（`environment.txt`） | 29 / 42 |
| reviewed | `9fa14f8` | 19 | 22 | 1（`environment.txt`） | 19 / 42 |
| delta | `e731a29` | 19 | 22 | 1（`environment.txt`） | 29 / 42 |

**结论**：`19 / 22 / 1` 三处完全相同，与提示词预期一致。清单由混合行尾的工作树生成，任何单一检出模式都无法全匹配；这是 B5B 既有缺陷，**不属于 B4 失败**，也不应由本次 `.gitattributes` 承担。delta 把 B5B 工作树恢复到与 base 相同的匹配度（29/42），说明该改动只移除了 `9fa14f8` 额外引入的破坏，未引入新失配。

- 说明：在 `9fa14f8` 上，`text eol=lf` 把 `baseline-local` / `local-explicit` 的 `run.log` 归一为 LF，使其 CRLF 清单记录失配（匹配数降到 19/42）；这与两个 NUL 日志的“add 重写”是同一根因的不同表现。收窄规则后两者均恢复。
- 测量注意：Git Bash 的 `sha256sum -c` 会因清单 CRLF 解析失败；上述用 Python 按字节复算，未据此判 B5B FAIL。

**发布前跟进项（建议，不影响本判定）**：重新登记 B5B `sha256sums.txt`（统一 LF 或统一按工作树 CRLF），或在 B5B README 写明校验方法（例如按文件实际行尾形式校验）。

---

## 6. 回归沿用

增量只改属性、无代码 / 测试变化，上轮 AC-1..AC-12 结论沿用。冒烟：`tests/test_security_b4.py` → **14 passed**（未重跑全量矩阵）。

---

## 7. 判定

| 条件 | 结果 |
|---|---|
| 仅 `.gitattributes` 变更 | ✅ |
| B5B 43/43 add 不重写 | ✅ |
| 两个 NUL 日志字节与清单一致 | ✅ |
| B4 证据 22/22 | ✅ |
| B5B 混合清单失配在 base 同样存在 | ✅（三处均 19/22/1） |

**VERDICT: PASS**（F-1 修复合格）。

**NEW FINDINGS**：无阻断项。仅一条非阻断跟进：B5B 清单混合行尾需在发布前重新登记或写明校验方法（既有问题，见 §5）。

**NOT VERIFIED**：
- 未读取 PR #30 网页（本会话无 GitHub API，符合试点约定）；候选 SHA 取自派发与本仓库 `origin/fix/b4-audit-integrity` 引用核对。
- 未重跑全部场景矩阵（增量无代码改动，按提示词 §5 只做冒烟）。

**CONTAMINATION**：无。仅使用本 Clone / 本地 ref 与本地 worktree；未读开发或主管会话、终端历史、未提交文件；未读任何生产私钥（含 `/etc/pm-rc3-review/key-a.pem`）；未使用 `project-memory-mvp`；未修改候选、未合并 / Approve / force push。

PASS 只表示 F-1 修复合格，不是 v1.0 GO；合并由人类决定。

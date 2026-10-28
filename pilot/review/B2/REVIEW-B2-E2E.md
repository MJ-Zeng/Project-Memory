# PM-03 B2 anchor-a E2E 复审补充

- 审查者：PM-03 Independent Reviewer（独立会话）
- 日期：2026-10-28
- 任务：B2 — 补 anchor-a 端到端证据（不重做逻辑级审查）
- 候选：`004a35bd7c6b6584a9054d7b61eca88b44ec25e6`
- PR：[#14](https://github.com/MJ-Zeng/Project-Memory/pull/14)
- 基线：`587ac6a5024db3a6076a863876076d7fc7ecdd98`
- 任务卡 SHA-256：`3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e`
- 审查分支：`review/b2-004a35b`
- 上一轮报告：`pilot/review/B2/REVIEW-B2.md`（NOT VERIFIED，唯一缺口是 anchor-a E2E）
- 证据：`pilot/evidence/B2/review-e2e-20261028T213532Z/`

## 0. 结论

**E2E_ANCHOR_A: PASS（4/4）。整体 B2：PASS（逻辑级 28/28 + E2E 4/4）。**

四个 fixture 在真实 `anchor-a`、以 uid 1000 运行候选代码时全部符合预期：两个伪造收据被来源门禁拒绝（错误指向“执行来源不可信/人类例外缺失”，不是引用错误），两个带 anchor-a 签名的正例被接受。

## 1. 环境

| 项 | 值 |
|---|---|
| 运行身份 | WSL `uid=1000`（`zmj`），非 root |
| Python | 3.14.4（WSL） |
| 候选代码 | `PYTHONPATH=.pilot/candidate`，导入路径确认为该 worktree |
| 候选提交 | `004a35b`（`git worktree list`；三个源文件 blob 哈希记录在 `environment.txt`） |
| 信任锚 | `/etc/pm-rc3-review/anchor-a.json`，`0644 root:root`，runner 不可写；`load_anchor` 返回 `anchor-rc3-a / ok` |
| 签名者 | PM-01（`key-a.pem` 仅在 `/etc/pm-rc3-review/`，未读取、未使用） |
| Git | 2.53.0；每个副本 `core.autocrlf=true`、`core.fileMode=false` |

本轮**没有** patch `authority.load_anchor`：签名校验走真实的受保护 anchor 路径。

## 2. 四个 case 的运行

每个 case：`cp -a fixtures/b2/<case>/repo /tmp/b2-<case>`（fixture 只读），然后：

```bash
PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json \
PYTHONPATH=<pm-pilot-03>/.pilot/candidate \
python3 -m project_memory goal evidence \
  --repo . --id G-B2 --criterion C1 \
  --kind verification --ref VER-B2-<case>
```

| case | exit | head（运行前后一致） | stderr 摘要 | 判定 |
|---|---|---|---|---|
| `forged-untrusted` | 1 | `6f7a5ddb…` | `证据无效：VER-B2-forged-untrusted 的执行来源不可信：人类例外缺失：收据没有可验证的执行 attestation，也没有人类签名例外` | 拒绝（正确） |
| `forged-claimed-trusted` | 1 | `3111dbd4…` | 同上门禁消息（ref 为 `VER-B2-forged-claimed-trusted`） | 拒绝（正确） |
| `genuine-trusted` | 0 | `f8ddf427…` | 空 | 接受（`goal_evidence_result`） |
| `exception` | 0 | `b8c4d280…` | 空 | 接受（`goal_evidence_result`） |

关键点：

- 两个伪造 case 的 stderr **不含**“找不到验证记录”，确实命中执行来源门禁；`forged-claimed-trusted` 即使收据内容完整、布尔 `trusted=true`，仍被拒绝——证明门禁不是查布尔值。
- 两个正例 exit 0 且 stdout 为 `kind: goal_evidence_result`，说明不是“全部拒绝”。
- 两次运行（21:35、21:37）exit 与 head 完全一致。
- 运行前 `git rev-parse HEAD` == `result.json.head`；运行后 HEAD 不变（`goal evidence` 只改未提交的 Goal）。

## 3. 与 PM-01 `result.json` / `summary.json` 对比

| case | 期望 exit | 观察 exit | head 一致 | stderr 一致 | case_ok |
|---|---|---|---|---|---|
| `forged-untrusted` | 1 | 1 | 是 | 是（逐字一致） | 是 |
| `forged-claimed-trusted` | 1 | 1 | 是 | 是（逐字一致） | 是 |
| `genuine-trusted` | 0 | 0 | 是 | 是（均为空） | 是 |
| `exception` | 0 | 0 | 是 | 是（均为空） | 是 |

`summary.json.verdict=PASS` 被独立复现；`results.json` 中 `all_match=true`。

> B3 说明：正例的 `goal evaluate` 仍可能 `satisfied=false`（正向流程自失效未修）。本轮按任务要求只判 `goal evidence` 的来源门禁，未把 `evaluate` 当作 B2 判据。

## 4. 是否改变上一轮结论

**改变。** 上一轮 `REVIEW-B2.md` 为 NOT VERIFIED，唯一原因是缺 anchor-a E2E。本轮补齐后：

- 逻辑级结论不变（28/28 矩阵、13/13 绕过拒绝、B1 无回归）；
- anchor-a E2E 4/4 符合预期；
- 按本轮规则（逻辑级 + E2E 全部符合）整体 **B2: PASS**。

该 PASS 是独立审查结论，不代替人类的合并批准，也不宣布 Goal `achieved`。

## 5. 残余风险与 NOT VERIFIED

- **attestation 隔离字段是签名者断言**：`isolation.uid/pid_ns_levels/env_count/network` 由 PM-01 在生成 fixture 时写入，本轮只验证签名与绑定，未由真实 `trusted_exec` WSL 启动器观测。ADR-0003 §5.2 已披露。
- **fixture 的执行事实**是 PM-01 的 fixture 构建过程，不是一次新的受信启动器执行；E2E 证明的是“真实 anchor 验签 + 门禁判定”，不是“启动器隔离有效”。
- **真实人类签名例外**：`exception` case 的签名者仍是 PM-01 持有的 anchor-a 密钥；无法区分“人类本人”与“持有该密钥的自动化”。`issued_by` 只是签名载荷内字符串（上一轮 INFO）。
- **Windows 符号链接拒绝路径**未单独执行（平台限制），仅静态确认。
- **重放边界**（同一 attestation 重放同一收据）未在 anchor-a 上复验，属设计内接受。
- 未验证：PR #14 描述/评论、Issue #12 正文（环境无 `gh`、私有 API 无 token）。

## 6. 证据与可复现

`pilot/evidence/B2/review-e2e-20261028T213532Z/`：

```text
environment.txt          uid/python/git/anchor 权限与 anchor_id、候选 blob 哈希、fixture head
commands.jsonl           probe + 四个 case 的 cwd/env/argv/exit
results.json             case 期望 vs 观察、head_match、case_ok、all_match=true、verdict=PASS
<case>.stdout/.stderr/.exit/.head_before/.head_after
scripts/run_e2e.sh       复现脚本（强制 uid==1000，否则拒绝）
scripts/assemble_results.py
sha256sums.txt           25 项，清单最后写入、不含自身；就地校验 exit 0
```

全部文本为 LF；fixture 目录只被读取（四个 fixture HEAD 与 `summary.json` 一致，`.project-memory/` 未跟踪是 fixture 生成时的既有状态，非本轮改动）。

## 7. 污染与纪律

- `human_relay`：none
- `unauthorized_reads`：none（未读 PM-01/PM-02 会话或工作树；未读 `key-a.pem`/`key-b.pem`）
- 未修改候选代码/commit/分支、未修改 fixture、未自行签名
- 未 Approve、未合并、未 force push
- 未使用候选树里的 `.project-memory/tooling` 或探针

## 8. 最终判定

- `E2E_ANCHOR_A: PASS`
- `FORGED_UNTRUSTED: PASS`
- `FORGED_CLAIMED_TRUSTED: PASS`
- `GENUINE_TRUSTED: PASS`
- `EXCEPTION: PASS`
- **`VERDICT: PASS`**（逻辑级 28/28 + E2E 4/4）

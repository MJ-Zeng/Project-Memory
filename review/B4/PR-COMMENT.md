# PR #30 复核评论（供 PM-01 转发）

> 本会话无 GitHub API 凭据（符合 `PILOT_CLOSEOUT.md` §7.7），无法直接评论；以下为待转发文本。

---

**B4 独立复核结论：PASS（程序性独立复核，不是安全认证，不是 v1.0 GO）**

复核者：PM-03，独立会话 + 独立 worktree；候选 `9fa14f8`，基线 `f7c9133`；复核分支 `review/b4-9fa14f8`。
报告：`review/B4/REVIEW-B4.md`；证据：`evidence/B4/review-20261029T065012Z/`（27 个文件，`sha256sum -c` 全 OK）。

**独立复现（全部由复核者自己构造场景，未复用开发 probe）**

| 场景 | 结果 |
|---|---|
| 手改 `status=achieved`（无/有证据两种） | `effective_status=achieved_unverified`、`status_trusted=false`，raw 仅作声明 |
| 删中间行 | `invalid`，`seq_mismatch_at:2`，exit 2 |
| 改字段不重算 / 只重算该行 hash | `entry_hash_mismatch_at:2` / `prev_hash_mismatch_at:3` |
| 整链重建（自洽、不更新 checkpoint） | `invalid`，`checkpoint_chain_mismatch` |
| 截断为更短链（开发未留证，复核补做两种） | 均 `invalid`，`checkpoint_chain_mismatch` |
| 空账本 / 缺目录 | `audit_empty` / `audit_missing`，均 `invalid` |
| 换 Goal id 重放 checkpoint | `checkpoint_goal_mismatch` |
| 合法流程（测试 RSA key + `load_anchor` stub） | `valid`、`authoritative=true`、`effective=achieved`、`status_trusted=true` |
| Agent 签 checkpoint（缺签名 / 未受信密钥 / 无 anchor） | 三种均拒绝；`head.json` 不生成；仓库内无签名代码 |
| 达成后追加审计 | 仍 `valid`/`authoritative`，前缀锚有效 |

链哈希用独立实现复算 5/5 吻合（`seq`、`prev_hash`、`entry_hash`，首条 64 个 `0`）。

**回归**

- 全量：**247 passed / 2 skipped**（基线对照 233/2；2 个 skip 为既有 Windows 符号链接限制，非新增）
- B5B/B5A/B3/B2/RC3：**61 passed / 2 skipped**，无删测、无跳过、无放宽门禁
- `tasks/B4.md`、B0–B5B 任务卡、`frozen/*`、`execution.py`、`trusted_exec.py` 未改

**需跟进（不影响 B4 PASS）**

1. **MEDIUM — `.gitattributes: evidence/** text eol=lf` 追溯作用于既有 B5B 证据**：`evidence/B5B/run-20261029T015035Z/receipts/{trusted,trusted-host-attempt}/run.log` 是 CRLF/NUL 产物，`git add` 会把它们归一为 LF，字节改变、其 `sha256sums.txt` 记录失效（干净检出上 `git hash-object --path` ≠ `HEAD:path` 已证实）。建议改为 `evidence/B4/**` 或对二进制证据 `-text`。
2. **MEDIUM（已由 ADR §7.4 披露）** — 已签 checkpoint 之后追加的尾部行可被无成本删除而仍 `valid`。不影响 `achieved`（该转换在前缀内），但建议运维文档写明并约定关键动作后重新 checkpoint。
3. LOW — ADR §3.5 说非终态 `status_trusted=true` 且 problems 会标注；实现返回 `null`/`[]`（更保守），文档需对齐。
4. LOW — `.gitattributes` 与 `tasks/B4-*.md` 不在任务卡 §3 允许清单内（与 closeout §8.3 同一老问题），建议下一轮补允许清单。
5. INFO — `audit checkpoint-request` 依赖进程内可读 anchor（无 anchor 时 fail-closed 拒绝），OPERATIONS 可点明。

**NOT VERIFIED**：PR 正文/评论（本会话无 API 凭据）；生产 anchor-a 端到端（只用测试 key + stub）；真实 anchor 保护属性（未用第二主体）；双仓库 checkpoint 重放（用换 Goal id 近似）；并发写审计。

**未执行**：未 Approve、未合并、未 force push。合并与 Goal 生效由人类决定。

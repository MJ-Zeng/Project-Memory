# B2 冷启动恢复（PM-03）

- 恢复开始：2026-10-28T19:20+08:00（约）
- 首次正确复述：2026-10-28T19:30+08:00
- 接手分钟数：约 10
- 污染：none

## 六项事实

1. **任务**：B2 — 有效签名不得包裹伪造执行收据。把内容完整性与执行真实性拆成独立条件；只查 `execution_provenance.trusted` 布尔值判 FAIL。
2. **基线**：`587ac6a5024db3a6076a863876076d7fc7ecdd98`（PR #13 merge）。
3. **候选**：`004a35bd7c6b6584a9054d7b61eca88b44ec25e6`；PR head `6257fb61cf29974aad32216b24788766bc37d147`，仅比候选多两个 Handoff 文件（已核实）。候选是基线后代。
4. **判据**：AC-1..AC-11（任务卡，SHA-256 `3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e`，基线与候选均一致）。
5. **PM-02 声明**：全量 203 passed / 2 skipped（exit 0），B2 专项 13 passed；不声称 PASS/VERIFIED；四类 anchor-a fixture 未生成、未跑 anchor-a E2E、未跑真实 WSL 启动器；`issued_by` 只是字符串。Handoff 写 `qoder/qoder-desktop-agent`，与当前环境不一致（自报，不作身份认证）。
6. **下一步**：独立 worktree 重跑全量/B2/基线；自建负向/正向/例外/绕过矩阵；B1 回归；写 `REVIEW-B2.md` 与证据；E2E anchor-a 标 NOT VERIFIED。

## 必须询问的问题

- 无阻塞性问题。
- 工件缺失：GitHub Issue #12 正文与 PR #14 描述/评论（私有仓库 API 404，本机无 `gh`）；`pilot/kit/b2/` 无 anchor-a fixture。均已记录，不影响逻辑级复现，但 E2E anchor-a 无法验证。

## 工件一致性

- 任务卡哈希：一致。
- 候选/PR head：一致，候选为基线后代。
- Handoff 哈希：authority/coordination/execution 三项记录的是 CRLF 工作树哈希，`tests/test_security_b2.py` 记录的是 LF blob 哈希（混合基准，Low）。
- `pilot/STATUS.md`：仍写 B2 `dispatch_pending_merge`，过期（F-4 类型）。

## 污染与偏差

- `human_relay`：none
- `missing_artifacts`：Issue #12 正文、PR #14 描述/评论、anchor-a fixture
- `stale_artifacts`：`pilot/STATUS.md`
- `unauthorized_reads`：none；未读 PM-01/PM-02 会话、终端历史、未提交文件；未读 `/etc/pm-rc3-review/key-a.pem`、`key-b.pem`

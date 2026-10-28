Decision: ACCEPT_SCOPE_SPLIT_AND_MERGE
By: 人类（MJ-Zeng），2026-10-28 会话明确指令“接受 scope split，合并 B2，然后把试点收尾”
Date: 2026-10-28T21:45+08:00（GitHub merged_at 2026-10-28T13:44:37Z）
Basis: PR #14；`pilot/review/B2/REVIEW-B2-E2E.md`（`review/b2-004a35b` @ `6cbdc76`，PASS：逻辑级 28/28 + anchor-a E2E 4/4）；PM-01 门禁核对（203 passed / 2 skipped）
Merge commit: 5a5abddfc35161c290537c8e009352e7b52960bd（parents `587ac6a` + `6257fb6`）
Scope: 合并 `fix/b2-receipt-provenance` 到 `dev/v1.0`
**不包含**：
- 任务卡 AC-3 的 `goal evaluate satisfied=true` 子项——该子项是 B3 正向自失效，留给 B3；
- Release、部署、B3/B4/B5、Goal `G-B2` 置为 `achieved`。

Conditions:
- 合并树必须等于候选树 + Handoff；已按 PR head `6257fb6` 合并。
- `review/b2-004a35b` 与两份证据保留，不因合并删除。
- AC-3 的 `evaluate` 子项必须在 B2 Issue #12 / 本 decision / 试点报告中明确记为 **NOT VERIFIED，B3 范围**，不得写成“全部 AC 通过”。
- B3/B4/B5、`PYTHONPATH`/cwd 同名模块顶替 HIGH 仍为产品阻塞。
- 试点三轮 B0/B1/B2 到此收尾；v1.0 不 GO。

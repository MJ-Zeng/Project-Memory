# B4 上下文恢复

- 日期：2026-10-29
- 会话：PM-02 Developer（独立 Clone）
- 基线：`f7c91333bbc999626e87eb29555b2c7c1ccb1a8f`
- 任务卡：`tasks/B4.md`，SHA-256 实测 `3fcce10bb9b03293358a4beab40c0466bd3e40b59d7c0596d7fb8086d71649eb`（与派发值一致）
- 候选分支：`fix/b4-audit-integrity`

## 1. 六项事实

1. **任务与基线一致**：工作区 HEAD 为 `f7c9133`（PR #29 merge commit），`tasks/B4.md` 哈希与派发值一致；依赖 B0–B5B 均已合并在 `dev/v1.0` 历史中。
2. **两个缺口已实测复现**：
   - 手改 `.project-memory/goals/<id>.json` 的 `status=achieved` 后，`goal_show` 仍返回 `goal.status=achieved`（仅 `status_consistent=false`）；消费方只看 `status` 就会误信。`evaluate_goal` 返回 `satisfied=false`、`recorded_status_consistent=false`，但没有 `effective_status`/`status_trusted` 字段。
   - `.project-memory/audit/verification_attempts.jsonl` 的条目没有 `prev_hash`/`entry_hash`；`audit` 顶层命令是文档审计，不存在执行账本 `audit verify`；删除中间行、重写字段、整文件重建都无检测手段。
3. **改动面**：`coordination.py` 的 `_audit_attempt`（355）、`goal_show`（1098）、`evaluate_goal`（950）、`transition_goal`（1051）；`authority.py` 只提供验签（`load_anchor`/`verification_authority`），**没有签名函数**——签名必须由仓库外人类/PM-01 用 anchor 私钥生成，测试用测试 RSA key + patch `load_anchor`。
4. **运行环境**：`python` 指向 WindowsApps 别名（exit 49），真实解释器是 `C:/SoftWare/Anconda/python`（3.12.4，pytest 9.1.1）；CLI 输出含中文，需要 `PYTHONIOENCODING=utf-8` 才能被管道正确解码。
5. **既有测试约束**：`test_security_rc3.py` 固定了 `status_consistent`、`status_authority=local_untrusted`（proposed 场景）、`recorded_status_consistent` 语义，以及 `goal_achieved_unsatisfied` 审计条目的 `reason` 字段；`test_project_memory.py::test_t05_rejected_attempt_is_audited_but_not_recorded` 直接读取 JSONL 字段。新增链字段可以附加，但不能改这些既有字段/语义。
6. **B5B/B5A/B3 边界**：B4 不触碰 `test-run` 默认拒绝、原生包装器、B3 稳定判据摘要与 B2 来源门禁；这些由定向测试回归确认。

## 2. 接手分钟数

约 8 分钟（从读取 `PILOT_CLOSEOUT.md` 到完成复现脚本并确认两个缺口）。

## 3. 必须询问的问题

1. B4 的签名 checkpoint 由谁在何时签？本会话按“`transition_goal` 生成 `head.request.json`，PM-01/人类用 anchor-a 私钥签名后 `audit checkpoint-attach`”设计；若 PM-01 期望其它交付形态，需要提前对齐。
2. 生产 anchor-a 的签名载荷约定是否接受“canonical JSON（sort_keys、无空格、无尾随换行）”？本实现以此为准，并在 ADR 中写明。
3. `audit verify` 作为现有文档审计命令 `audit` 的子命令（`audit verify`/`audit head`/`audit migrate`/`audit checkpoint-*`）是否可接受？无子命令时保持原文档审计行为不变。

## 4. contamination

无。本会话只读取本 Clone 与 GitHub 工件；未读取主管/审查者会话、终端历史或工作树；未读取 `/etc/pm-rc3-review/key-a.pem`。

# RC3 B1–B5 脱敏摘要

- 候选：`0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4`
- 独立复核结论：**RC3 NO-GO**
- 完整复核报告在实验室 `reviews/independent-rc3-0d08a1a/`；本文件只保留试点需要的技术事实，不含密钥、日志原文或其他项目数据。

## B1（CRITICAL）签名验证器可被调用者替换

- 位置：`project_memory/authority.py` 的 `_openssl()` / `_verify_signature()`。
- 根因：用 `shutil.which()` 解析 `PATH` / `PROJECT_MEMORY_OPENSSL`，且只信任二进制的退出码。
- 攻击：Agent 控制环境 → 假 `openssl`（或 `/bin/true`）→ 伪造签名被接受 → Goal 到 `achieved`。
- 修复方向：不信任环境变量解析验证器；固定路径/哈希/所有者；缺失/不匹配 fail closed；校验输出而不只看退出码；或进程内固定实现。
- 验收：`pilot/rounds/B1/task.md`；探针：`pilot/kit/b1/openssl_substitution.py`。
- 注意：正向判据只到“签名被接受”；`goal evaluate → satisfied` 受 B3 影响，不作为 B1 通过条件。

## B2（HIGH）有效签名可包裹伪造执行收据

- 位置：`project_memory/coordination.py` 的 `_verification_ok()`。
- 根因：授权层要求 `checks.tests.receipt_integrity_valid`，但不要求 `execution_provenance.trusted` 或等价外部执行证明。
- 攻击：手写自洽收据（`valid=true`、`provenance.trusted=false`）+ 真签名 → Goal 到 `achieved`。
- 修复方向：授权层要求 `execution_provenance.trusted=true` 或等价证明；执行来源纳入签名载荷；负向测试。
- 验收：B2 轮次任务卡（B1 关闭后创建）。

## B3（HIGH）正向流程自失效

- 位置：`project_memory/coordination.py` 的 `add_goal_evidence()` 与 `goal_criteria_sha256()`。
- 根因：签名绑定验证时的 `goal_criteria_sha256`；挂证据后 digest 变化，记录失效，需二次签名。
- 修复方向：签名载荷与可增长的 `criterion.evidence` 解耦；或先固定证据再验证，禁止把 verification 自身追加为 evidence。
- 验收：B3 轮次任务卡（B2 关闭后创建）。

## B4（MEDIUM）审计不是防篡改账本

- 直接编辑 Goal JSON 的 `status` 会显示 `achieved`；审计可删除/重建；无链式哈希或签名。
- 修复方向：仅追加 + 前序哈希链；关键状态转换同步写入受保护日志；`goal show` 显示一致性。
- 计划：B1–B3 之后的独立轮次。

## B5（MEDIUM）默认 `test-run` 无操作系统隔离

- 默认 `test-run` 是普通子进程（`isolation.mode=none`），Agent 可直接调用；收据标 `local_untrusted`，但默认路径就是运行不可信代码。
- 修复方向：默认 `--trusted`，或默认拒绝 Agent 自动执行不可信命令；`--local` 需显式选择并标注风险。
- 计划：B1–B3 之后的独立轮次。

## 已知限制

- RC3 复核未建立真实权限差异的签名者；测试签名只证明密码学路径，不代表真人批准。
- 未执行完整 `PROJECT_MEMORY_WSL_EXE` 伪造攻击（NOT RUN）。
- 未访问真实 GitHub/CI/审批系统；外部证据均为 `declared_unfetched`。
- 本试点不重新论证 B1–B5；只按任务卡复现与验收。

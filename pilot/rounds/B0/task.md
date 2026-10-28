# B0 — 可移植的仓库身份，解除执行收据的绝对路径绑定

- 任务 ID：`B0`
- 状态：`draft`（派发前冻结）
- 优先级：P0（阻断试点）/ P1（产品）
- 基线：`dev/v1.0` 的 B0 dispatch 合并提交；精确 SHA 见派发 Issue
- 冻结参照：`71b65bd26356df41efbb566bd8fe5e8648394bd9`（B1 脚手架 merge commit）
- 候选分支：`fix/b0-repo-identity`
- 关联 Issue：见派发 Issue（本任务卡不绑定 URL）
- Goal：`G-B0`
- 发现来源：B1 正向 fixture 准备；见 Issue #1 的 P-1 评论

## 1. 问题

执行收据把**仓库的绝对路径**当作仓库身份：

```text
execution.repo_id(repo) = sha256(repo.resolve())
```

收据里保存这个 `repo_id`；`verify_receipt` 要求它等于当前仓库路径的哈希。

因此，同一个仓库、同一个 commit、同样的内容，只要复制/Clone 到另一个路径：

- `verify_receipt.valid = false`，问题为“收据不属于本仓库”；
- `_verification_current` 失败；
- `goal evidence` 报“针对的不是当前提交或执行已失效”。

## 2. 最小复现

1. 在路径 A 创建仓库，提交；
2. 运行 `test-run`，生成收据；
3. 运行 `verify`，生成验证记录；
4. 把整个仓库复制到路径 B（内容与 commit 不变）；
5. 在 B 中运行 `verify_receipt` 或 `goal evidence`。

当前结果：

```text
receipt_repo_id = 87284aaf...
current_repo_id = ce540af6...
valid = false
problem = 收据不属于本仓库
```

期望结果：同一个仓库/commit 在 B 中仍然有效。

## 3. 影响

- PM-02 在 `pm-pilot-02` 产生收据，PM-03 在 `pm-pilot-03` 无法验证；
- CI checkout、Docker、换机器、git worktree 同样失败；
- 证据包不可移植，“独立复核”退化为只能看开发自报；
- 这是多 Agent / 多 Clone 协作的核心前提，不是 fixture 脚本问题。

## 4. 目标

让执行收据与验证记录在**同一仓库的独立 Clone/不同路径**之间可移植，同时仍然拒绝来自**不同仓库**的收据；不削弱签名与内容绑定。

## 5. 范围

允许修改：

- `project_memory/execution.py`（`repo_id` 及其调用点）
- `project_memory/coordination.py`（如验证路径需要）
- `tests/test_security_rc3.py` 或新增 `tests/test_repo_identity.py`
- `docs/decisions/` 下的 ADR / security note
- `pilot/evidence/B0/`、`pilot/rounds/B0/handoff-*`
- 必要的收据/快照 schema 版本文档

不允许：

- 修改 B1/B2/B3/B4/B5 的行为；
- 删除/跳过既有测试；
- 修改任务卡/判据/探针/评测器；
- 用环境变量静默覆盖仓库身份而不记录安全影响；
- 让不同仓库的收据互相通过。

## 6. 设计选项（PM-02 选一个并写 ADR）

1. **规范化 remote URL + 根 commit（推荐）**
   - 同一 GitHub 仓库的不同 Clone 得到同一身份；
   - 无 remote 的本地仓库用根 commit/tree 作为回退；
   - 拒绝不同根 commit/remote 的收据。
2. **仓库 UUID**
   - 在 `.project-memory/config.json` 中生成并提交；
   - Clone 共享同一 UUID；
   - 需说明配置被篡改时的残余风险。
3. **移除 repo_id 检查**
   - 只依赖 commit/tree/snapshot/log 内容哈希；
   - 最简单，但要论证不会让不同仓库的收据误通过。

无论选哪个，都必须说明：为什么旧的绝对路径绑定存在、替换后防的是什么、没防什么。

## 7. 验收标准

| AC | 判据 | 方法 | 通过条件 |
|---|---|---|---|
| AC-1 | 跨路径正例 | 路径 A 生成收据，复制到路径 B，验证同一 commit | `verify_receipt.valid=true`；`_verification_current=true`；`goal evidence` exit 0 |
| AC-2 | 跨仓库负例 | 不同 remote/根 commit 的仓库 B 使用 A 的收据 | 拒绝，退出非 0；错误可定位到仓库身份 |
| AC-3 | 身份定义 | ADR 说明稳定身份的计算方式与回退 | 不含绝对路径；Clone/CI 路径变化不影响 |
| AC-4 | 向后兼容 | 旧路径绑定收据不静默跨路径通过 | schema 版本升级；旧收据标 `legacy_path_bound` 或明确拒绝 |
| AC-5 | 回归 | 既有 147 项 + 新增正/负测试 | 全绿；无删除/跳过未说明 |
| AC-6 | 无新伪造路径 | 签名、authority、receipt 内容哈希不被削弱 | 既有负向用例仍拒绝；无新绕过 |
| AC-7 | ADR | 信任模型、被拒方案、残余风险、迁移 | 与实现一致；残余风险明确 |
| AC-8 | 范围纪律 | diff 只在允许文件 | 无 B1/B2/B3 夹带 |
| AC-9 | 证据 | 命令、退出码、日志、哈希 | 可复现；跨路径/跨仓库证据齐全 |
| AC-10 | 独立复现 | PM-03 从两个不同路径复现 | 正例通过、负例拒绝 |

## 8. 迁移与兼容

- 收据/快照 schema 版本必须升级；旧收据标记为 `legacy_path_bound`。
- 旧收据在同一路径下可以继续工作，但不得被当作跨路径证据。
- 不得静默重写历史收据；如需迁移，必须显式命令并记录。
- 文档必须说明：升级后旧证据的可信范围。

## 9. 证据包

```
pilot/evidence/B0/<run-id>/
  README.md
  environment.txt
  commands.jsonl
  cross_path.json
  cross_repo.json
  pytest.log
  diffstat.txt
  sha256sums.txt
```

不含私钥、token、其他项目数据。

## 10. 判定语义

| 结论 | 条件 |
|---|---|
| **PASS** | AC-1..AC-10 全部满足；跨路径正例、跨仓库负例、全量回归通过；无新绕过 |
| **FAIL** | 任一 AC 失败；跨仓库收据被接受；或跨路径仍失败 |
| **BLOCKED** | 环境/权限/基线缺失，无法执行 |
| **NOT VERIFIED** | 有 AC 未运行；整体不得记 PASS |

## 11. 不在范围

- B1/B2/B3/B4/B5 的修复；
- v1.0 发布；
- 多 Agent 编排、Web UI、知识图谱、额外模型服务；
- 修改冻结候选 `frozen/rc3-0d08a1a`。

## 12. 阅读顺序

`pilot/README.md` → `pilot/ROLES.md` → `pilot/ROUND_PROTOCOL.md` → 本任务卡 → `handoff-dispatch.md` → `pilot/reference/RC3_B1_B3.md`。

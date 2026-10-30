---
id: "ADR-0001"
status: "proposed"
owner: "MJ-Zeng"
related_issues: [3]
---

# ADR-0001：可移植的仓库身份（执行收据不再绑定绝对路径）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28
- 任务：B0（Issue #3）
- 基线：`73be8e3ac4efc04c1811c122eb665344fe8ce4c3`
- 影响范围：`project_memory/execution.py`（`repo_id` 及调用点、收据/快照 schema 版本）、`project_memory/coordination.py`（仅验证路径的兼容分支）、测试、本文档
- 不涉及：B1–B5 的行为、签名/authority、评测器、冻结候选

## 1. 背景与问题

当前实现把**仓库在文件系统中的绝对路径**当成仓库身份：

```python
def repo_id(repo: Path) -> str:
    return _sha256_bytes(str(repo.resolve()).casefold().encode('utf-8'))
```

`test-run` 把该值写入执行收据的 `repo_id`；`verify_receipt` 要求它等于“当前仓库路径”的哈希（`execution.py` 的 `verify_receipt`）。于是同一个仓库、同一个 commit、同样的快照与日志，只要目录名不同（独立 Clone、CI checkout、Docker、`git worktree`、换机器），收据就被判为“收据属于其他仓库”，`_verification_current` 随之失败，`goal evidence` 报“针对的不是当前提交或执行已失效”。

这是多 Agent / 多 Clone 协作的前提问题：PM-02 在一个 Clone 产生的收据，PM-03 在另一个 Clone 无法验证，独立复核退化为“只能看开发自报”。

## 2. 决策

仓库身份改为 **规范化 remote URL + 根提交（root commit）**，二者都不含检出路径。

### 2.1 计算方式

```text
remote   = 规范化后的网络 remote URL；没有网络 remote 时为 null
roots    = git rev-list --max-parents=0 HEAD 的全部根提交（40 位小写 SHA，按字典序排序）
identity = sha256(JSON({"remote": remote, "roots": roots}))   # sort_keys, 紧凑分隔符
kind     = "remote+root"（有 remote）| "root-only"（无网络 remote）
```

- **remote 选择**：优先 `origin`；否则取名字字典序最小的 remote。取 `git remote get-url <name>`。
- remote 规范化（只做无损归一，不猜测等价关系）：
  - 去掉结尾 `/` 与结尾 `.git`；
  - `scheme://[user@]host[:port]/path` → `host[:port]/path`（host 小写，path 保持原样；user 与 scheme 丢弃）；
  - 显式默认端口 `:22` 被丢弃：`ssh://[user@]host:22/path` 与 scp 形式 `[user@]host:path` 归一到同一身份 `host/path`。非默认端口保留（`host:2222/path` 与 `host/path` 不同）；
  - scp 形式 `[user@]host:path` → `host/path`；
  - 本地路径、`file://`、相对路径视为**没有网络 remote**，不进入身份，避免把绝对路径重新引入；
  - 因此 `git@github.com:Owner/Repo.git` 与 `https://github.com/Owner/Repo` 归一到同一身份 `github.com/Owner/Repo`。
- **根提交**：取当前 `HEAD` 可达历史的全部根提交。普通 Clone、复制整仓、CI checkout 得到同一组根提交；分支切换、HEAD 移动不影响身份（根提交不变）。
- **无 commit 的仓库**：`test-run` 本来就需要 commit，身份计算失败时按 fail-closed 处理（见 §2.4），不回退到路径。

### 2.2 收据字段（schema `1.1`）

新收据保留 `repo_id`（值为上述 `identity`），并新增：

```json
"repo_identity": {
  "schema": "1.1",
  "kind": "remote+root",
  "remote": "github.com/MJ-Zeng/Project-Memory",
  "root_commits": ["<sha>", ...]
}
```

快照清单 `schema_version` 同步升到 `1.1`（字段不变，仅版本号）。

### 2.3 验证逻辑

`verify_receipt` 重算当前仓库身份并与收据的 `repo_id` 比较；不一致即 `valid=false`，问题为“收据属于其他仓库”。若收据带 `repo_identity`，同时校验其 `kind/remote/root_commits` 与重算值一致（发现字段被单独改写）。

### 2.4 旧收据（schema `1.0`）的迁移/标记

- **不重写历史收据**。旧收据保持 `schema_version=1.0` 原样。
- 验证时识别旧 schema，只按旧公式 `sha256(casefold(absolute_path))` 校验：
  - **同一路径**：继续有效，但结果带 `identity.kind="legacy_path_bound"`、`identity.portable=false`、`legacy_path_bound=true`，明确“不能作为跨路径证据”；
  - **不同路径**：`valid=false`，问题“收据属于其他仓库（legacy 路径绑定，不能跨路径使用）”。
- 不提供静默迁移命令。要获得可移植收据，重新运行 `test-run` 生成 `1.1` 收据，并重新生成引用它的验证记录。文档写明升级后旧证据的可信范围。

### 2.5 验证映射的仓库绑定（B0.1 整改）

`verify` 的 criterion evidence 映射带 `target_repository`。判断它是否属于当前仓库不再依赖绝对路径或目录名，而是复用 §2.1 的稳定身份：

- 接受**稳定身份本身**：`repo_identity.id`，或规范化 remote（`host/path`）；
- 接受**绝对路径**，但只当它是当前检出路径，或另一个**存在**的检出目录且 `repo_identity` 相同（同一仓库的复制品）。该路径必须是 git 顶层目录，且不能位于当前仓库内部；
- **不再接受裸目录名**：同名目录的不同仓库无法用名字通过检查；
- 路径不存在或解析失败时按不匹配处理（fail-closed），不猜测。

于是路径 A 写下的 mapping 在复制出的路径 B 中仍按身份通过；不同 remote 或不同根提交的仓库即使目录同名也会被拒绝。长期可移植的 mapping 推荐直接写稳定身份或规范化 remote，而不是绝对路径。

## 3. 被拒方案

| 方案 | 拒绝原因 |
|---|---|
| **仓库 UUID（写入 `.project-memory/config.json` 并提交）** | 需要修改被跟踪配置并处理旧仓库没有 UUID 的迁移；配置随仓库复制时不会自动生成新 UUID，把该文件手工复制到另一个仓库即可让收据互认，负例只能靠“不复制配置”的约定；合并/重置还会制造身份冲突。可在未来作为 remote 不可用时的补充，但不是本轮最小方案。 |
| **移除 `repo_id` 检查，只依赖 commit/tree/snapshot/log 内容哈希** | 任务要求“仍拒绝不同仓库的收据”。去掉仓库维度后，任何包含相同 commit 与快照的仓库都会接受收据；也让“收据属于哪个仓库”无法诊断。内容哈希本身不能区分“同一仓库的另一份拷贝”和“另一个仓库”。 |
| **继续用绝对路径，但允许配置覆盖** | 等于把身份判断交给环境变量/配置，静默绕过且无法审计；任务卡明确禁止。 |
| **用 `git rev-parse --show-toplevel` 的规范化路径** | 仍是路径；跨机器、跨挂载点不稳定，问题原样保留。 |

## 4. 迁移与向后兼容

- schema 版本：执行收据 `1.0 → 1.1`；快照清单 `1.0 → 1.1`。
- 旧收据：只读保留，按 §2.4 标记 `legacy_path_bound`；不删除、不改写、不批量迁移。
- 旧验证记录：仍按原逻辑校验，它引用的旧收据只在原路径有效；跨路径复核必须重新生成 `1.1` 收据与验证记录。
- 对既有测试：147 项中不存在跨路径假设，`repo_id` 不再是路径哈希不改变它们的语义；`test_relative_repo_path_does_not_raise` 仍然成立（身份与路径表示无关）。

## 5. 信任模型：防什么、不防什么

**防**

- 同一仓库的不同 Clone / 不同检出路径：收据与验证记录可移植（`valid=true`、`_verification_current=true`）。
- 不同 remote 或不同根提交的仓库：使用他人收据被拒绝，错误可定位到仓库身份。
- 收据把 `repo_identity` 字段单独改写但与 `repo_id` 不一致：被校验发现。
- 身份计算不再读取检出路径，路径变化不会改变身份（AC-3）。

**不防（残余风险，必须与签名/authority 一起理解）**

1. **`.git/config` 可被同权限 Agent 改写**：remote 只是本地配置，不是认证。改写 remote 使其与 A 相同后，根提交仍必须与 A 相同才会通过；若攻击者同时复制 A 的对象库，那在内容上已经是 A 的另一个 Clone。**仓库身份不是来源证明**。
2. **整仓复制**：按设计，复制出的仓库就是“同一仓库”，收据可移植；这正是 AC-1。若把收据复制进一个根提交相同但内容被改写的仓库，commit/tree/snapshot/log 哈希会先失败。
3. **根提交可伪造**：攻击者可以构造一个根提交相同的仓库（技术上等同复刻历史）；这无法用无密钥身份阻止。真正的门槛仍是 `verify` 的签名/authority 与内容绑定，本 ADR 不改变它们。
4. **本地路径 remote 退化为 `root-only`**：此时身份只剩根提交；两个不同来源但根提交相同的仓库无法区分（现实中只在复制时发生）。这是为了避免把绝对路径重新引入身份而接受的取舍。
5. **浅克隆（`--depth`）**：`--max-parents=0` 会停在被截断的边界，根提交与完整 Clone 不同，跨路径验证会失败。需要在 CI 中 `git fetch --unshallow`（或 `--filter` 的完整历史）后再生成/验证收据；文档与 Handoff 记录该限制。
6. **身份不是签名**：`repo_id` 无密钥，收据内容哈希也无密钥。它只回答“这是不是同一个仓库”，不回答“谁执行、是否可信”。`execution_provenance.trusted` 仍恒为 false，`VERIFIED` 仍必须经过 authority 签名。
7. **映射写绝对路径时依赖对方检出存在**（§2.5）：复制场景下 A 仍在，B 可按身份匹配；若 A 已被删除/移动，B 无法从旧路径解析身份，会失败关闭。需要长期可移植时在 mapping 中写稳定身份或规范化 remote。
8. **显式非默认端口是独立身份**：`ssh://host:2222/path` 与 `host/path` 不同（只归一默认端口 22）；这是有意保守，避免把不同端点合并。

## 6. 验证计划（对应任务卡 AC）

| AC | 方法 |
|---|---|
| AC-1 | 路径 A 建仓、commit、`test-run`、`verify`；整仓复制到 B；B 中 `verify_receipt.valid=true`、`_verification_current=true` |
| AC-2 | 不同 remote（同根提交）与不同根提交（同 remote）两种仓库使用 A 的收据，均拒绝且错误指向仓库身份 |
| AC-3 | 检查身份只由 remote+roots 决定；同一仓库改名/移动路径后 `repo_id` 不变 |
| AC-4 | 构造 `1.0` 旧收据：原路径通过并标 `legacy_path_bound`，复制到 B 后拒绝 |
| AC-5 | 147 项既有测试 + 新增正/负测试全绿 |
| AC-6 | 既有 authority/负向用例保持拒绝；签名与内容哈希逻辑不变 |
| AC-7 | 本 ADR |
| AC-8 | diff 仅触及任务卡允许文件 |
| AC-9 | `pilot/evidence/B0/<run-id>/` 命令、退出码、日志、哈希 |
| AC-10 | PM-03 从两个不同路径独立复现（不在本会话） |

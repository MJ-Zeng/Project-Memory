# 架构决策

ADR 状态：proposed、under-review、accepted、rejected、superseded。

Accepted 决策需要可审计的人工审查；approved_by 必须指向或写明批准证据。Agent 只能新建 `proposed`，不能自行 `accepted`；所有者可以用明确指令授权 Agent 代为落盘，此时 ADR 正文与变更 PR 必须写明授权来源、批准人和证据位置。

## 索引

状态按各篇 frontmatter 实测（2026-11-09 复核）；8 篇均为 `accepted`，由所有者授权 Agent 代为落盘，批准证据见对应变更 PR 的 approval 上下文。接受只表示设计理由被批准，不代表功能已在某个版本上线。

| ADR | 标题 | 状态 | 决定的是什么 |
|---|---|---|---|
| [ADR-0001](ADR-0001-portable-repository-identity.md) | 可移植的仓库身份（执行收据不再绑定绝对路径） | accepted | 收据和记录里存仓库相对路径与身份，不存本机绝对路径，换机器不等于记录失效 |
| [ADR-0002](ADR-0002-inprocess-signature-verifier.md) | 签名验签器进程内化（不再由 PATH / 环境变量选择验签器） | accepted | 验签在进程内完成，PATH 与环境变量不能再挑选验签实现 |
| [ADR-0003](ADR-0003-execution-provenance.md) | 执行来源与内容完整性分离（B2） | accepted | 收据能证明文件未被改动，不能证明由谁产生；两者分开建模 |
| [ADR-0004](ADR-0004-criteria-digest.md) | 判据定义摘要与证据分离（B3） | accepted | 成功标准以摘要绑定，改判据会让旧证据失效，而不是静默沿用 |
| [ADR-0005](ADR-0005-cli-bootstrap.md) | CLI 启动引导与同名包顶替防护（B5A） | accepted | 原生包装器按绝对路径启动，防止仓库内同名包顶替已安装的 CLI |
| [ADR-0006](ADR-0006-test-run-isolation.md) | 默认 `test-run` 不得静默执行未隔离代码（B5B） | accepted | 隔离模式不可用时显式失败并降级记录，不假装在沙箱里跑 |
| [ADR-0007](ADR-0007-audit-integrity.md) | 审计账本与 Goal 状态的可验证性（B4） | accepted | 审计账本按 head 提交请求与附加，Goal 状态转换留下可复核的记录 |
| [ADR-0008](ADR-0008-anchor-lifecycle.md) | 信任锚生命周期（有效期、吊销、指纹）与审批的仓库身份复检 | accepted | 锚的有效期、吊销列表与指纹只在仓库外配置里可信，读取时复检仓库身份 |

需要复核状态时重跑：`python3 -m project_memory reconcile --repo . --format markdown`（其中包含 accepted ADR 是否与目标关联的检查）与 `python3 -m project_memory search --repo . '<主题>'`（检索决策正文）。

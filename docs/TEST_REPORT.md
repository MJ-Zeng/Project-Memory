> 历史记录（2026-10-25，v0.3 阶段，74 项 unittest）：不代表 v1.0.0 的测试结论。
> 当前状态见 `docs/CURRENT_STATE.md`。

# 验证记录

日期：2026-10-25
环境：Windows 10.0.26300，Python 3.12.4（`C:\SoftWare\Anconda\python.exe`），Git Bash。

命令：

```bash
cd C:/Documents/02_Research/Code/project-memory-mvp
PYTHONUTF8=1 /c/SoftWare/Anconda/python.exe -m unittest discover -s tests -v
```

## 结果

**74 项测试全部通过，0 失败，0 错误**（本机约 29 秒）。其中 26 项 `CoordinationTest` 覆盖 Goal、Run、检查点、恢复、独立验证、缺陷和对账；原有初始化、审计、检索和完成门禁测试保持通过。

| 验证内容 | 测试 | 结果 |
|---|---|---|
| 初始化幂等、不覆盖已存在文件 | `test_init_non_destructive_and_tooling`, `test_init_overlay_skips_index_and_custom_root` | 通过 |
| 拒绝竞争的 `doc/` 与 `docs/` 根 | `test_init_refuses_competing_docs_root` | 通过 |
| 离线 CLI，之后补装 Skill | `test_installed_offline_cli_can_install_skill_later` | 通过 |
| ADR 状态机与审批门禁 | `test_adr_proposal_and_approved_gate`, `test_same_topic_accepted_adr_warning` | 通过 |
| ADR 引用有效性 | `test_broken_document_reference`（ADR 引用在审计路径中覆盖） | 通过 |
| Handoff 结构、幂等与冲突 | `test_handoff_idempotent_and_conflict`, `test_handoff_store_outside_repo_stays_read_only` | 通过 |
| 缺上下文时不编造文档 | `test_missing_context_warns_instead_of_inventing` | 通过 |
| 断链，包括中文文件名 | `test_broken_document_reference`, `test_broken_relative_link_in_chinese`, `test_link_written_from_nested_project_root` | 通过 |
| 重复内容与镜像分歧 | `test_duplicate_document_content`, `test_identical_mirror_copy_is_not_a_duplicate`, `test_custom_doc_root_and_mirror_divergence` | 通过 |
| 冻结镜像策略 | `test_frozen_mirror_reports_drift_at_medium`, `test_invalid_mirror_policy_is_rejected` | 通过 |
| 围栏代码块里的示例不算文档链接 | `test_fenced_code_block_example_is_not_a_broken_link` | 通过 |
| current scope 排除历史、镜像和证据 | `test_current_scope_excludes_history_mirror_and_evidence` | 通过 |
| current scope 仍检查全部 ADR | `test_current_scope_still_checks_adrs` | 通过 |
| 拒绝非法审计 scope | `test_invalid_audit_scope_is_rejected` | 通过 |
| 固定格式文档脚手架 | `test_new_doc_scaffolds_fixed_frontmatter`, `test_cli_new_doc` | 通过 |
| 拒绝不安全或未批准的文档状态 | `test_new_doc_rejects_unapproved_or_unsafe_input` | 通过 |
| 拒绝重复 ID 和已存在路径 | `test_new_doc_refuses_duplicate_id_and_existing_path` | 通过 |
| 尊重自定义 canonical 根 | `test_new_doc_uses_custom_canonical_root` | 通过 |
| 多进程/多线程并发 | `test_concurrent_handoff_same_run_is_idempotent`（6 线程，同一 run ID） | 通过（仅同进程线程） |
| 任务完成但文档未同步 | `test_finish_unknown_and_declared`, `test_finish_docs_impact_uses_custom_root` | 通过 |
| 检索排除历史与镜像 | `test_search_excludes_archive_and_labels_authority` | 通过 |
| 无 Git、无 GitHub | `test_local_task_without_git`, `test_injected_issue_does_not_change_policy` | 通过 |
| 空审计 fail-closed | `test_audit_fails_closed_when_no_docs` | 通过 |
| PR 快照可追溯性 | `test_pr_snapshot_traceability_findings` | 通过 |
| Schema 文件可解析 | `test_schema_files_are_valid_json` | 通过（只验证 JSON 解析） |
| 语义检索的防护 | `test_semantic_mode_requires_local_dir` | 通过 |
| 入口文档缺失、非 canonical、非 current | `test_entry_doc_missing_or_not_canonical`, `test_entry_doc_must_declare_current` | 通过 |
| 初始化时声明入口文档 | `test_init_writes_entry_doc_and_takeover_template`, `test_init_overlay_declares_missing_entry_doc` | 通过 |
| 新鲜度与非法 `last_verified_at` | `test_entry_doc_freshness_findings`, `test_current_document_staleness_and_invalid_date` | 通过 |
| 拒绝不安全的 `entry_doc` 与年龄配置 | `test_config_rejects_unsafe_entry_doc_and_age` | 通过 |
| Goal 至少一个必达标准；approved/achieved 需批准并持久化 `approved_by` | `test_goal_requires_criteria_and_approval` | 通过 |
| Goal 评估看证据，不看 Issue 是否关闭 | `test_goal_evaluation_uses_criteria_not_issue_closure` | 通过 |
| 跨 criterion 证据不会丢失（修复丢失更新） | `test_goal_evidence_accumulates_across_criteria` | 通过 |
| 测试证据拒绝 README 等非证据文件 | `test_goal_evidence_accumulates_across_criteria` | 通过 |
| 重复 run ID、同任务并发活跃 run | `test_duplicate_and_concurrent_runs` | 通过 |
| run ID 跨任务重复被拒 | `test_duplicate_run_id_across_tasks_is_rejected` | 通过 |
| 检查点幂等，结束后拒绝写入 | `test_checkpoint_is_idempotent_and_closed_after_finish` | 通过 |
| finish 写 1.2 handoff 和恢复包 | `test_finish_writes_12_handoff_and_resume_package` | 通过 |
| base 不是当前 HEAD 祖先 | `test_resume_detects_stale_base` | 通过 |
| 1.1 旧 handoff 可读并降级 | `test_legacy_11_handoff_is_readable_with_warning` | 通过 |
| 恢复默认排除 verifier，并使用最近检查点 | `test_resume_skips_verifier_and_uses_checkpoint` | 通过 |
| 自验、陈旧 SHA、expected SHA 不匹配被拒 | `test_verification_requires_independent_evidence_and_current_sha` | 通过 |
| verifier 角色与 agent/model/session 独立性 | `test_verifier_role_and_independence_are_enforced` | 通过 |
| 验证记录不能跨 Goal 复用 | `test_verification_evidence_cannot_cross_goal` | 通过 |
| 旧提交验证不再满足 Goal 或恢复为 verified | `test_stale_verification_stops_goal_and_resume` | 通过 |
| 失败的 `--resolves-defect` 不留下可用 pass | `test_failed_resolves_defect_leaves_no_pass_record` | 通过 |
| 修复提交必须在被验证历史中 | `test_resolves_defect_requires_fix_in_verified_history` | 通过 |
| 缺陷修复、复验和 verifier run 不被误报 | `test_defect_lifecycle_and_reverification` | 通过 |
| 缺陷手工标 verified 被对账发现 | `test_reconcile_flags_verified_defect_without_record` | 通过 |
| 对账发现篡改、孤立 run、未验证提交 | `test_reconcile_detects_tampering_orphans_and_unverified_submission` | 通过 |
| 1.2 metadata 参与 handoff 幂等判断 | `test_handoff_12_metadata_is_part_of_idempotency` | 通过 |
| run 状态转换被强制 | `test_run_transition_is_enforced` | 通过 |
| dry-run 如实报告已有记录 | `test_dry_run_reports_existing_records_truthfully` | 通过 |
| 任务 ID 含冒号在 Windows 上可 finish | `test_task_id_with_colon_finishes_on_windows` | 通过 |
| 模型密钥不写入执行记录 | `test_run_record_does_not_store_model_key` | 通过 |
| GitHub 错误不泄漏 Token | `test_github_errors_do_not_include_token` | 通过 |
| CLI 端到端 Goal/Run/Verify/Reconcile | `test_cli_goal_run_verify_reconcile_end_to_end` | 通过 |
| 工具同步默认 dry-run，写入不删 extra | `test_sync_tooling_is_dry_run_then_updates_without_deleting_extra` | 通过 |

## 独立 QA 发现与修复

一个人工指定的只读 QA 会话在 61 项测试全部通过后检查了 v0.3 实现，发现以下真实问题。修复后重新运行到 74 项通过。

| 级别 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| high | 自验只检查 run ID；同 agent/model/session 也能通过 | 要求 verifier `role`，并要求 agent/model/session 至少一项不同 | `test_verifier_role_and_independence_are_enforced` |
| high | 验证记录可跨 Goal 复用 | 证据检查要求 verification 的 `goal_id` 与当前 Goal 一致 | `test_verification_evidence_cannot_cross_goal` |
| high | pass 在提交漂移后仍然满足 Goal | Goal 证据和 `resume` 重新检查当前 HEAD 与 run 状态 | `test_stale_verification_stops_goal_and_resume` |
| high | 失败的 `--resolves-defect` 已写入可用 pass | 写记录前先校验全部缺陷，失败则完全不写 | `test_failed_resolves_defect_leaves_no_pass_record` |
| high | 缺陷可手工改成 `verified`，没有验证记录 | 禁止直接更新为 verified；对账检查 `verified_by` 的有效性 | `test_reconcile_flags_verified_defect_without_record` |
| medium | `resume` 默认选中 verifier run | 默认只选 executor；verifier 需要显式 `--run-id` | `test_resume_skips_verifier_and_uses_checkpoint` |
| medium | 有检查点但无 handoff 时仍返回 `needs_handoff` | 活跃执行使用最近检查点作为恢复来源 | 同上 |
| medium | verifier 活跃执行被误报为多个活跃 run | 对账排除 verifier | 同上 |
| medium | Goal 证据更新会丢失前一个 criterion 的证据 | 基于 `_mutate` 的当前记录追加 | `test_goal_evidence_accumulates_across_criteria` |
| medium | run ID 可跨任务重复，`_find_run_by_id` 含糊 | 拒绝跨任务重复；读取时发现重复立即报错 | `test_duplicate_run_id_across_tasks_is_rejected` |
| medium | `model.key` 被持久化，可能泄漏凭据 | 删除字段和 CLI 选项，只保留 provider/id | `test_run_record_does_not_store_model_key` |
| medium | 含冒号的任务 ID 在 Windows 上 finish 崩溃 | handoff 路径统一做安全化 | `test_task_id_with_colon_finishes_on_windows` |
| low | run 状态机没有在实际写入时强制执行 | `finish` 和 `verify` 都检查转换 | `test_run_transition_is_enforced` |
| low | dry-run 对已存在 Goal 仍报告 `created: true` | dry-run 比较内容并如实返回 | `test_dry_run_reports_existing_records_truthfully` |
| low | 同 run 的 1.1 handoff 会阻塞 finish | 明确报错并要求使用新 run ID，不原地升级 | 人工检查 + `test_legacy_11_handoff_is_readable_with_warning` |
| low | completion-report schema 不接受字符串 task 和空 `base_sha` | schema 改为 string/integer、可空 SHA | Schema 解析测试 |

未在离线环境解决的问题：`externally_verified` 和 `human_approved` 仍由调用方声明。CLI 不联网抓取 CI、不认证 review 审批人，只把来源标为 `declared_unfetched`。

## v0.3 本地 Goal 实验

实验仓库：`C:\Documents\02_Research\Code\project-memory-v03-lab`，真实 Git 提交 `ec5c031` → `7d78b7e` → `3250269`。实验使用 `auto` 模型的多个独立 Qoder 会话，没有切换模型。

- Goal `G-AUTH`（修复授权绕过）处于 `evaluating`，C1/C2/C3 均通过 `goal evaluate`。
- 第一轮验证 `VER-63c883e7c934` 为 fail，产生 high 缺陷 `DEF-1b77a3e93a52`；修复后 `VER-f17891e6cdd3` 为 pass，缺陷转 verified。
- 最终对账在更新后的工具上是 **0 high、0 medium、1 low**（入口文档没有 `last_verified_at`）。
- `run resume --task local-auth-1` 返回 `verified`，选中 executor `run-fix-1`，当前验证为 `VER-f17891e6cdd3`。
- 最终输出在实验室的 `experiment/34-*`、`35-*`、`36-*`。

该实验只证明本地记录链和命令能跑通，不证明验证结论本身正确。实验中的 Goal 批准是“实验自批”，不是真实人工审批；`G-AUTH.json` 的 `approved_by` 仍为空，因为该记录生成于批准持久化缺陷修复之前。没有回溯改写它；修复后的行为由单元测试覆盖。

## 教程命令实测

`docs/TUTORIAL.zh-CN.md` 里的命令在一个临时 Git 仓库里完整执行过，仓库没有提交：

- `init --install none` 生成了 `docs/CURRENT_STATE.md`，其中没有 `last_verified_at`。
- `audit --scope current --fail-on high` 返回 0，带一个 low 级 `entry_doc_unverified`；补上真实的 `last_verified_at` 后，同样的审计为 0 个发现。
- `start --task-file` 返回 `source: local_task_file`、`base_sha: null`。
- `handoff` 写入 `.project-memory/handoffs/demo-001/run-01.json`，状态为 `reported_unverified`。
- `finish` 返回 `do_not_close`，阻断项是 `pr_merge_evidence` 和 `review_attestation`。
- `graph` 和词法 `search` 正常执行。
- `--help`、错误信息、审计的 `message`/`note`、生成的 ADR 正文和 `CURRENT_STATE.md` 都是中文；命令名、字段名、状态值和 schema 关键字保持英文，避免破坏脚本兼容性。

这次验证只证明命令序列能跑通，不证明审计能判断文档内容是否真实。

## 真实仓库只读运行

为避免公开内部项目名，下面用仓库 A、B、C 代称；命令和数字保持原样。

审计有两个范围。`--scope all`（默认）扫 canonical、镜像和历史材料，用于周期复核。`--scope current` 扫 canonical 下的 `current`、`draft`、`in_flight`、`unclassified` 文档，加上全部 ADR；`finish` 和推荐的 CI 门禁都使用这个范围。提取链接前会先去掉围栏代码块，所以命令示例和模板示例不会被误报为断链。

- **仓库 A（多根工作区）**：canonical 根为 `doc/new_doc`，另有一个只读镜像和一个 legacy 目录。全量审计扫描 203 篇 Markdown（42 篇 canonical、117 篇 legacy、44 篇 mirror），在 `mirror_policy: frozen`、ADR-0001 已 accepted 的情况下，结果为 **0 high、90 medium、46 low**。medium 包括 81 个历史/镜像/证据区的断链、8 处已确认的镜像分歧，以及 1 组镜像多余文件。8 处分歧是原先已知的 7 处，加上对 `00_项目总览.md` 的一次有意修正；镜像没有被改动。current scope 为 **18 篇文档，0 个发现**，`entry_doc = doc/new_doc/00_项目总览.md`（`status: current`，`last_verified_at: 2026-10-23`）。冻结前，同样的分歧会产生 7 个 high；冻结策略在 2026-10-25 经人工批准。
- **仓库 B（长期记忆覆盖层，`doc_roots: memory`，`legacy_roots: doc`）**：全量扫描 21 篇文档，其中 4 篇 canonical、17 篇 legacy，结果为 **0 high、5 medium**。5 个 medium 都是 legacy `doc/` 里的断链，`memory/` 覆盖层本身没有发现。current scope 为 **4 篇文档，0 个发现**。`memory/00_当前状态.md` 仍是 `draft`，`entry_doc` 有意留空，等所有者回答接手问题并把它提升为 `current` 后再设置。
- **仓库 C（外部只读复核，HEAD `1fa0032`）**：20 篇文档，3 个 medium 断链，集中在同一份审核报告中，指向不存在的文件。这个仓库没有被修改：前后执行 `git status`，都只有原先未跟踪的两份整改文档；没有创建 `.project-memory`。

演示输出在 `demo/pro3-release-2026-10-24/` 和 `demo/bigmodel-search-*.json`。

`examples/demo.sh` 已在本机完整执行（`PYTHON=/c/SoftWare/Anconda/python.exe bash examples/demo.sh`，退出码 0），依次跑完 init、decision、start、handoff、finish、audit、graph、search。脚本给出的完成建议是 `ready_for_human_verification`，因为示例快照和声明都由脚本提供；脚本同时打印了这些内容未经独立验证。

## 未验证的部分

以下项目不能当作已经通过：

- **跨模型续接**：NOT RUN。Qoder CN 的会话创建接口没有模型参数，实验只在 `auto` 模型的多个独立会话之间交接；`dfmodel`、`qfmodel` 只在本地配置中确认存在，没有在 v0.3 实验中切换使用。真正换模型需要人在界面中选择。
- **真实 GitHub 接入**：NOT RUN。`https://api.github.com/repos/wpqweasd/pro3` 返回 HTTP 404，本机也没有安装 `gh`。没有获取或创建任何 Issue、PR、review 或 CI 结果。
- **外部 CI / review 证据**：NOT RUN。`externally_verified` 和 `human_approved` 只验证 URL 形式并标记 `declared_unfetched`，没有抓取或认证真实状态。
- **真实人工审批**：NOT RUN。实验中的 Goal 批准是自批；没有有权限的人批准 `achieved`，Goal 停在 `evaluating`。
- **跨进程并发的强保证**：只测了同进程多线程和重复 run 的记录冲突；没有测多个操作系统进程或多个 Agent 同时写。没有分布式锁。
- **JSON Schema 实例校验**：只验证了 schema 文件能被 JSON 解析，没有用 Draft 2020-12 校验器检查全部生成的记录。
- **验证结论的正确性**：CLI 检查记录身份、SHA、日志存在性和状态机，不判断测试是否真的覆盖了风险，也不判断日志内容是否真实。
- **真实嵌入模型**：本机没有本地 sentence-transformers 模型；语义检索只有结构性防护，没有在真实模型上跑过。
- **语义矛盾检测**：审计能发现结构性冲突，例如镜像分歧、重复哈希、失效链接；它不能判断两篇措辞不同的文档是否在事实上互相矛盾。
- **模型与 SHAP 复现**：本机 Python 缺少 `rdkit` 和 `shap`，`src/` 里的代码没有运行。
- **Windows 崩溃恢复**：原子 no-clobber 写入验证了幂等性，没有验证断电或进程被杀后的恢复。
- **1.1 原地迁移**：不提供。同 run 的 1.1 handoff 必须换新 run ID 才能生成 1.2。

## 对旧版报告的更正

早先的版本声称“14 个 unittest 用例通过”和“12 个 JSON Schema 文件通过 Draft 2020-12 校验”，但当时既没有这些用例，也没有做过 schema 实例校验。本文件替换了那些说法，只保留上面列出的命令和结果。

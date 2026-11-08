# 人如何接手项目

接手时不必把文档读完。先用有限时间确认现在什么是真的，动手前核对一条事实。

## 谁读什么

- 人读仓库里提交的 Markdown。接手流程不能依赖运行 Python。
- Agent 先读配置里的 `entry_doc`，再用 `audit --scope current` 确认当前有效文档集合，用 `goal list` 和 `run resume` 看目标和在办执行。
- `search` 用来回答具体问题，比如“这个数字在哪里定义”，不适合当作项目导览。不要靠反复搜索来浏览项目。

## 阅读顺序

1. 读 `.project-memory/config.json` 里 `entry_doc` 指向的文档。它应该声明 `status: "current"`，并检查 `last_verified_at`。没有这个日期时，审计报 low，读者先把它当成未核验。
2. 看 `last_verified_at`。如果超过 `max_verified_age_days`，在重新核对之前，把所有状态描述都当成未确认。
3. 只读入口文档列为当前的内容，按它给出的顺序读。
4. 第一次修改之前，用仓库、日志或命令核对一条具体事实。
5. 入口没覆盖的内容，用 `search` 查，按返回的 `path`、`status` 和 `authority` 判断。能改现有 canonical 文档，就不要再写一份摘要。

## 接手在办目标与执行

有 Goal 或 Agent Run 时，先看记录，再看代码：

1. `goal list` 找 active 或 evaluating 的目标，`goal show` 看成功标准、关联 Issue/ADR/PR、执行、验证和缺陷。
2. `goal evaluate` 确认哪些标准有证据、哪些没有。不要因为 Issue 关闭就认为目标达成。
3. `run resume --task TASK` 或 `--goal GOAL` 取接手包。`resume_ready` 只表示记录齐全；逐项核对 `checks`、未关闭缺陷和 handoff 中的提交。
4. `stale_base` 或 `needs_human` 时停下来，请人裁决，不要自行 rebase、重置或覆盖别人的执行。
5. 换模型或换会话时开新的 run ID，base 指向前一个 head。不要接着用旧 run ID 写检查点或 finish。
6. 声称“已修复”的缺陷要看 `fixed_in_sha` 是否存在，以及有没有 pass 的复验。`fixed` 不等于 `verified`。
7. 记录里的 `agent_claimed` 只是声明。继续之前用独立验证或自己运行命令核对。

## 接手自检

动手前回答下面五个问题。答不出来说明文档有缺口，不是读者的问题，把缺口报出来。

1. 哪个基线已经验证过，用什么指标，在哪个评测集上？
2. 哪些线在做、哪些停了、哪些已经关闭，分别由谁决定？
3. 哪些数据和命令可以复现一次评测？
4. 最大的未决决策是什么，谁负责？
5. 改一处代码，可能让哪些已有结论失效？

不要靠读历史计划来回答。计划、手册、SOP 和 handover 描述的是某个人在某个时间点的打算；只有入口文档和 `status: current` 的文档描述现在。

## 不要当现状读

- `legacy_roots`、档案目录、`90_原始档案`、`_history`。
- 证据快照、原始日志、截图和一次性输出。
- `proposed` 或 `under-review` 的 ADR。决策还没有批准。
- 状态是 `proposed` 的 Goal，或没有 `approved_by` 的标准变更。目标意图不是已批准的范围。
- `reported_unverified` 的 handoff、检查点里未经核对的完成项，以及 `agent_claimed` 的证据。
- 重构方案、迁移日志和旧 handover，除非你在追查项目为什么走到今天。
- 状态是 `draft`、`in_flight`、`historical`、`superseded`、`archived` 或 `unclassified` 的文档。

被放弃的方案常常写得比当前方案更详细。详细不等于权威。

## 入口缺失或过期时

Agent 的做法：

1. 先把情况作为第一个阻塞项报告：`entry_doc_missing`、`entry_doc_not_current` 或 `entry_doc_stale`。
2. 不要拿历史 handover、重构方案或证据快照替代。
3. 提议一篇 `new-doc` 草稿，或对现有入口做一次受审查的更新。
4. 不要自己设置 `status: current` 或改 `last_verified_at`。这两件事需要实际核对过结论的人来做。

人的做法：先修入口文档。在别处补更多细节，弥补不了入口缺失或误导。

## 让入口保持有用

- 控制在 2k tokens 左右。它几乎每次会话都会加载，长度是持续成本。
- 它放当前事实、阅读顺序、未决事项和链接，不重复专题文档的细节。
- 只有重新核对过结论之后才更新 `last_verified_at`，并在变更记录里写清核对了什么。
- 一个仓库只留一篇入口。两个入口会重新制造审计本来要消除的歧义。

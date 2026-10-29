# 交接 — v1.0.0 发布文档三项 Medium 修正（M-1/M-2/M-3）

- 分支：`fix/release-docs`（从 `f79a85f49cbdf3d0e2804c3485c1ca630a226ec1`，即 `dev/v1.0`）
- 触发：PM-03 v1.0.0 最终安全复核 `REVIEW-FINAL.md` §3 的 M-1/M-2/M-3
- 证据：`evidence/release-docs/20261029T115211Z/`
- 判定：本文件只记录执行事实，不给出 PASS/GO 结论；判定属于 PM-03 与人类审批者。

## 1. 改了什么

| 文件 | 变更 |
|---|---|
| `README.md` | `test-run` 本地示例补 `--allow-local-untrusted` 并注明“宿主本地、无隔离、不可信、仅在了解风险时使用；需要隔离用 `--trusted`”；命令表改为 `(--trusted \| --allow-local-untrusted)` 并标注“执行模式必须二选一”；`goal evaluate` 退出码段补空必达集合例外与结构化字段建议 |
| `docs/OPERATIONS.zh-CN.md` | `goal transition --to approved` 与 `audit checkpoint-request` 的 `--approved-by` 改为 `owner@example.com`，并说明“邮箱格式、追溯标识而非认证”；`goal evaluate` 段补空必达集合例外（exit 0 + 结构化字段）与 `--strict` 不在本版范围；`status_problems` 列表补 `no_required_criteria` |
| `skill/project-memory/references/workflows.md` | 同类修正：manual 证据与 `goal transition` 的 `--approved-by` 改为邮箱并注明追溯标识语义；`evaluate` 退出码段补空必达集合例外 |

未改：任何 `.py`、测试、schema、`pyproject.toml`、`CHANGELOG.md`、版本号、依赖、`evidence/**` 历史文件；未碰 `project-memory-mvp`。

## 2. 为什么

- M-1：B5B 要求 `test-run` 必须二选一执行模式，旧示例无模式会 exit 3，快速上手路径不可用（无安全影响，fail closed）。
- M-2：`--approved-by` 要求邮箱格式（`coordination.py:796-807`），旧示例 `human-owner` 必被 exit 1 拒绝，批准/checkpoint 流程照抄不可执行。
- M-3：R1 有意让空必达集合 `goal evaluate` exit 0（`cli.py:467-472`），但文档仍写“未满足时退出 2”，只看退出码的脚本会把 `insufficient_evidence` 误当通过。

## 3. 实测退出码（临时 Git 仓库，证据 `exit-codes.txt`）

| 场景 | 命令要点 | 退出码 |
|---|---|---|
| M-1 旧示例（无模式） | `test-run --command ... --agent qoder` | **3**（拒绝执行，无收据） |
| M-1 修正示例（本地） | 追加 `--allow-local-untrusted` | **0**（收据 `trust=local_untrusted`、`isolation.mode=none`、命令 exit 0） |
| M-2 旧值 | `goal transition --to approved --approved-by 'human-owner'` | **1** |
| M-2 修正值 | `--approved-by 'owner@example.com'` | **0** |
| M-3 空必达集合 | 判据全部 `required=false` 后 `goal evaluate` | **0** |
| M-3 结构化字段 | 同上输出 | `satisfied=false`、`evaluation_status=insufficient_evidence`、`no_required_criteria=true`、`status_problems=["no_required_criteria"]`、`effective_status=evaluating`、`status_trusted=null` |
| M-3 achieved 仍拒绝 | 空必达集合下 `transition --to achieved` | **1**（`insufficient_evidence`） |

未执行任何 `--trusted` 不可信代码；可信模式仅静态核对文档措辞。

## 4. 回归

`C:/SoftWare/Anconda/python.exe -m pytest -q -p no:cacheprovider` → **253 passed, 2 skipped**，exit 0（`pytest-default.log`，189.56s）。skipped 仍为平台限制的两项符号链接测试。证明文档改动未误触代码。

## 5. 改动范围

`git diff --name-status f79a85f..HEAD` 仅：

- `M README.md`
- `M docs/OPERATIONS.zh-CN.md`
- `M skill/project-memory/references/workflows.md`
- `A evidence/release-docs/20261029T115211Z/**`
- `A tasks/release-docs-handoff-20261029T115211Z.md`

## 6. SHA-256（LF 字节，等于提交 blob）

- `README.md` `b05fcf10571b0ff61173d07589522fd040e2663385f5016ab70daaa849a0bd41`
- `docs/OPERATIONS.zh-CN.md` `59218738bf9f8e03eda189c62e2088eb3f43d67ca8dbc6aede6e2940487e04c1`
- `skill/project-memory/references/workflows.md` `2ad150192970c3e5a74b1f4293be700e3a5d83de6ef7bba93d086c4b98893334`

证据目录自校验：`cd evidence/release-docs/20261029T115211Z && sha256sum -c sha256sums.txt`（工作树字节）。

## 7. 未验证 / 边界

- 未合并、未打 tag、未建 Release；PR 未创建。
- 未跑 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量（本轮仅文档，默认全量已足够证明未误改代码）。
- 未复核生产 anchor、ACL、POSIX 安装等 REVIEW-FINAL §5 既有未验证项。
- 文档示例在 Windows 上用 Anaconda 绝对路径替代 `python3`（README 已注明 Store 桩问题）；sh 包装器场景未重跑。

## 8. 订正（2026-10-29，F-1/F-2 证据自校验）

§6 的“工作树字节”自校验缺少行尾前提，原清单混用 CRLF 工作树字节与 LF 字节，且 `verification.log` 记录的是陈旧哈希，因此在提交后检出中不成立。现已修正：

- `.gitattributes` 增加 `evidence/release-docs/** text eol=lf`（与 `evidence/B4/**`、`evidence/R1/**` 同款）。
- `sha256sums.txt` 从 LF 字节重新生成：`sha256sum -b`、`LC_ALL=C` 排序、排除清单自身，覆盖目录内除自身外的全部文件。
- `verify_release_docs.sh` 改为截断写 `verification.log`（不再 `tee -a` 追加），结束时把证据文件行尾统一为 LF、重生成清单并执行 `sha256sum -c`。脚本重跑会改写证据包，**重跑后必须一并提交证据文件与清单**。

正确的自校验（在干净检出中执行，行尾为 LF，工作树字节等于提交 blob）：

```bash
cd evidence/release-docs/20261029T115211Z && sha256sum -c sha256sums.txt
```

前提是 `.gitattributes` 中的 `evidence/release-docs/** text eol=lf` 生效；若在旧检出上直接跑，`core.autocrlf=true` 可能留下 CRLF 字节，需重新检出该目录。

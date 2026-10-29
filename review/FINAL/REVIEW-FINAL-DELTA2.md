# REVIEW — v1.0 发布证据包自校验修复复审（dbc858d → 5158908）

- 审查者：PM-03（独立会话；未采信 PM-02 自述，全部结论来自本机实测）
- 日期：2026-10-29（UTC 12:26–12:29）
- 基底（已复核对象）：`dbc858d2a3cf8144b24bf9e1523a509cd93cfce6`（`review/FINAL/REVIEW-FINAL-DELTA.md` @ `874f3e2`，判定 FAIL narrow，唯一失败项 F-1）
- 增量候选：`51589083e4c0d012f7006b2528a579104c0532cf`（`fix/release-docs`，父 `dbc858d`，已推送，无 PR）
- 复核工作树：`.pilot/docs-fix2`（detached `5158908`，跑 F-1/F-2）、`.pilot/docs-fix2-f1`（全新 detached `5158908`，复算 F-1）、`.pilot/docs-fix2-out`（分支 `review/release-docs-5158908`，仅存放本报告与证据）
- 证据目录：`evidence/FINAL/review-docs-fix-20261029T122642Z/`
- 本文件只记录增量事实与判定；不构成 v1.0 GO，发布决定仍属人类审批者。

## 1. 结论

| 项目 | 结果 | 证据 |
|---|---|---|
| 范围（无夹带、无删除） | **PASS** | §2；14 个文件均在允许清单内；`--diff-filter=DR` 为空；禁用路径过滤为空 |
| **F-1 证据包自校验** | **PASS** | §3：干净检出 `sha256sum -c` **24/24 OK，exit 0**；24/24 工作树字节 == 提交 blob；清单可由 blob 逐字节重建；无 `da5bd554` 陈旧值；无 CRLF |
| **F-2 脚本重跑可重复** | **PASS** | §4：脚本 exit 0；末尾 `sha256sum -c` 24/24、exit 0；10 场景退出码 3/0/0/1/0/0/0/0/0/1；pytest **253 passed / 2 skipped**；清单同步重建；变脏文件已记录 |
| D-1 `--ref` 示例 | **PASS（实测）** | §5：新示例 exit 0；旧示例 `review:https://...` exit 1 |
| 证据语义未变 | **PASS** | §6：仅 ID/时间戳/commit_sha/log_sha256/head 变化；关键判定字段逐项一致 |
| 交接 §8 描述 | **PASS（附 N-1）** | §7：§8 操作描述与实际一致；但 §6 的 `workflows.md` 哈希未随 D-1 修正更新（Low，见 N-1） |
| 回归 | **PASS** | §8：默认全量 253/2；`PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量见 §8 |

**DOCS_VERDICT: PASS**

依据：本轮 gate 条件（F-1 自校验成立、F-2 重跑可重复、D-1 示例可执行）全部以实际命令与退出码确认；范围无夹带、无删除、无改写历史证据；证据语义与修复前一致；默认全量回归全绿。唯一新增问题是交接文档 §6 中 `workflows.md` 的哈希陈述已过期（N-1，Low，纯元数据，不影响证据包自校验、不影响示例行为、不涉及代码/安全），建议随下一次文档提交顺手更新，不阻断本判定。

## 2. 范围审计

```
$ git rev-list --parents -n 1 5158908
5158908... dbc858d...
$ git diff --name-status dbc858d..5158908      # 14 项
M .gitattributes
M evidence/release-docs/20261029T115211Z/{m1-new,m2-goal-create-auth,m2-goal-create,m2-new,
  m3-active,m3-evaluate,m3-evaluating}.json
M evidence/release-docs/20261029T115211Z/{pytest-default.log,sha256sums.txt,verification.log,verify_release_docs.sh}
M skill/project-memory/references/workflows.md
M tasks/release-docs-handoff-20261029T115211Z.md
$ git diff --diff-filter=DR --name-status dbc858d..5158908   # 空（无删除/重命名）
$ git diff --name-only ... | grep -E '(^project_memory/|^tests/|^evidence/B4/|^evidence/R1/|^evidence/B5B/|^pyproject.toml$|^CHANGELOG.md$)'
(无输出)
$ git diff --stat dbc858d..5158908
14 files changed, 135 insertions(+), 69 deletions(-)
```

内容级核对（非仅路径）：

- `.gitattributes`：仅新增一行 `evidence/release-docs/** text eol=lf`，与 B4/R1 同款；未改其他规则。
- `workflows.md`：仅 D-1 示例（`review:https://...` → `https://github.com/example/repo/pull/12#pullrequestreview-1`），3 行。
- `tasks/...handoff...md`：仅文件末尾追加 §8，共 +16 行，未改既有内容。
- `verify_release_docs.sh`：日志改为截断写，末尾新增行尾归一 + 清单重生成 + `sha256sum -c` 自检并以自检码退出。
- `evidence/**`：仅改动本证据包 9 个文件，无 `evidence/B4`、`evidence/R1`、`evidence/B5B` 触碰。

## 3. F-1 实测（核心判据）

环境：**全新** worktree `.pilot/docs-fix2-f1`（detached `5158908`，检出后 `git status --short` 为空）。本机 `core.autocrlf=true`，故所有字节结论均在该干净检出内得出。日志见 `01-f1-selfcheck.txt`。

```
$ cd evidence/release-docs/20261029T115211Z && sha256sum -c sha256sums.txt
…（24 行）
SHA256SUM_C_EXIT=0                 # 24/24 OK
$ git check-attr text eol -- sha256sums.txt
text: set    eol: lf               # 新规则生效
$ find . -maxdepth 1 -type f -exec grep -l $'\r' {} +    # 无输出（无 CRLF）
$ # 工作树字节 vs git cat-file blob HEAD:<path>
compared=24 mismatches=0
manifest_worktree_sha == manifest_blob_sha = 9cf3672d…c79088
$ # 仅用提交 blob 重建清单（C 排序）再 diff
RECONSTRUCT_DIFF_EXIT=0 ; reconstructed_lines=24
$ grep -c da5bd554 sha256sums.txt      # 0（旧 verification.log 陈旧哈希已消失）
  目录文件 25 个 = 24 个被哈希 + sha256sums.txt 自身（清单按设计排除自身），与 24 行一致
```

结论：**F-1 已消除**。证据包在干净检出中可独立复算，且清单本身等于提交 blob 的字节哈希——不再依赖工作树行尾假设。

## 4. F-2 实测（重跑可重复）

在 `.pilot/docs-fix2`（detached `5158908`，运行前 `git status --short` 为空）完整执行脚本（含全量 pytest，未中途 kill；日志 `02-f2-script-raw.log`、摘要 `03-f2-rerun.txt`）：

```
command: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 bash evidence/release-docs/20261029T115211Z/verify_release_docs.sh
SCRIPT_EXIT=0
===== self-check (sha256sum -c) =====
… 24/24 OK
sha256sum -c exit=0
```

- 场景退出码（重跑生成 `exit-codes.txt`）：`3 0 0 1 0 0 0 0 0 1`，与提交版逐字节相同（`git diff --quiet` exit 0）。
- pytest：`253 passed, 2 skipped in 158.72s`（`pytest-default.log`，与提交值一致；时长差异属正常）。
- 清单同步重建：`sha256sums.txt` 被重写（9 条哈希变更，其余为空文件/未变文件），重跑后独立再跑 `sha256sum -c` → exit 0；未留陈旧值。
- 日志语义修正生效：`verification.log` 为**截断写**（106 行，`log_closed_utc=` 仅 1 处），不再 `tee -a` 重复追加。
- Git Bash 解析：`sed -i 's/\r$//'` 与 `find -printf '%P\0' | LC_ALL=C sort -z | xargs -0 -r sha256sum -b` 在 MSYS bash 5.3.15 下无告警、无解析问题；重跑后目录内无 CR 字节。

重跑后 `git status --short`（设计使然，**须与清单一起提交**）：

```
 M evidence/release-docs/20261029T115211Z/m1-new.json
 M …/m2-goal-create-auth.json   M …/m2-goal-create.json   M …/m2-new.json
 M …/m3-active.json             M …/m3-evaluate.json      M …/m3-evaluating.json
 M …/pytest-default.log         M …/sha256sums.txt        M …/verification.log
?? .f2-run.out   ?? .openssl-pytest.log        # 仅本次复核工具产生，非证据包内容
```

`exit-codes.txt`、各 `*.stderr`、`verify_release_docs.sh` 未变（内容确定性）。上述 10 个证据文件的变脏是脚本重跑必然结果，与交接 §8 的“重跑后必须一并提交证据文件与清单”一致。

## 5. D-1 实测

在临时 Git 仓库（`project_memory init --install none`，创建含 C1/C2 的 Goal），使用 `PYTHONPATH` 指向 `5158908` 的干净 worktree（日志 `04-d1-cli.txt`）：

| 命令 | 结果 |
|---|---|
| `goal create … --criterion 'C1 …' --criterion 'C2 …'` | exit 0 |
| **新示例** `goal evidence --criterion C2 --kind manual --ref 'https://github.com/example/repo/pull/12#pullrequestreview-1' --approved-by 'owner@example.com'` | **exit 0**；存储 `ref` 原样保留 |
| **旧示例** `--ref 'review:https://...'` | **exit 1**（`manual 证据的 ref 必须是批准链接、PR/Issue 编号或 40 位提交 SHA`） |
| 旧变体 `--ref 'review:https://example.com/review/1'` | exit 1（同上） |

与 `coordination.py:65` 的 `APPROVAL_REF` 一致：`https?://\S+` 命中新示例；`review:https://…` 因 `review` 分支要求后接数字而被拒。**D-1 已修正且实测可用。**

## 6. 证据语义未变

对比 `dbc858d` 与 `5158908` 的提交 blob（日志 `05-evidence-semantics.txt`）：

- `m3-evaluate.json` 仅 `head` 变化；关键字段完全一致：
  `{"satisfied": false, "evaluation_status": "insufficient_evidence", "no_required_criteria": true, "status_problems": ["no_required_criteria"], "effective_status": "evaluating", "status_trusted": null}`
- `m1-new.json` 仅 `EXE-*`/`commit_sha`/`repo_id`/`log_sha256`/时间戳变化；`trust=local_untrusted`、`isolation.mode=none`、`os_isolation=false` 不变。
- `m2-new.json` 仅时间戳变化；`status=approved`、`approved_by=owner@example.com`、`approvals[0].approval_authority=claimed_unverified` 不变。
- `m3-transition.json` 为 0 字节（失败转移无 stdout）；stderr 仍为 `insufficient_evidence`，与修复前一致。
- `m1-old.json` 为空、stderr 仍为“拒绝执行：…必须二选一…”；`exit-codes.txt` 逐字节相同。

结论：修复只动字节呈现（行尾/清单），未改任何判定语义，未见伪造。

## 7. 交接订正准确性

§8 的四条描述与实际行为逐条吻合：

1. `.gitattributes` 新增 `evidence/release-docs/** text eol=lf`——实测 `check-attr` 为 `text: set / eol: lf`。
2. 清单从 LF 字节重建、`sha256sum -b`、`LC_ALL=C` 排序、排除自身——脚本第 148–153 行与实测重建一致。
3. 日志截断写、结束时归一 LF、重生成清单并 `sha256sum -c`——实测 106 行、1 个 `log_closed`、自检 exit 0。
4. “重跑后必须一并提交证据文件与清单”——实测 10 个证据文件变脏，其中含 `sha256sums.txt`，描述准确。

**N-1（Low，新增）：** 交接 §6 仍列出 `workflows.md` 的 SHA-256 为 `2ad15019…93334`，该值是 `dbc858d` 的 blob；因本次 D-1 修改了该文件，`5158908` 的实际 blob 为 `6d9ab3f7…0032f`（`06-handoff-hash.txt`）。README 与 OPERATIONS 两项哈希仍匹配。影响：读者若按 §6 校验 `workflows.md` 会得到不匹配，误以为被篡改；不影响证据包自校验、不影响示例行为、不涉及代码。建议在 §6 直接更新该哈希或在 §8 追加一行说明。因本轮 handoff 被限定为“仅追加”，此项属可选收尾，不改变 PASS 判定。

## 8. 回归

- 脚本内全量默认：`pytest -q -p no:cacheprovider` → **253 passed, 2 skipped**，exit 0（158.72s）。
- 可选：`PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量（本机 OpenSSL 3.5.9 可用）→ **253 passed, 2 skipped, exit 0**（180.30s，`08-openssl-pytest.txt`）。
- 本轮被审增量无 `.py`/测试改动，默认全量已可证明未误触代码。

## 9. 判定表

| # | 判据 | 实测 | 结果 |
|---|---|---|---|
| 1 | 范围仅允许路径、无删除 | 14 文件、0 删除、禁用路径 0 命中 | PASS |
| 2 | 干净检出 `sha256sum -c` 24/24 exit 0 | 24/24、exit 0 | PASS |
| 3 | 工作树字节 == 提交 blob | 24/24 一致；清单自身一致 | PASS |
| 4 | 清单可由 blob 重建、无陈旧哈希 | diff exit 0；`da5bd554` 0 命中 | PASS |
| 5 | 脚本 exit 0、末尾自检 24/24 | exit 0、24 OK、exit 0 | PASS |
| 6 | 10 场景退出码一致 | 3/0/0/1/0/0/0/0/0/1，逐字节同提交 | PASS |
| 7 | pytest 253/2 | 253 passed / 2 skipped | PASS |
| 8 | 重跑重建清单、变脏可解释 | 清单 9 条更新、独立复算 exit 0、10 文件变脏 | PASS |
| 9 | D-1 新示例可执行、旧示例被拒 | 0 / 1 | PASS |
| 10 | 证据语义未变 | 仅 ID/时间戳/SHA 变化 | PASS |
| 11 | 交接 §8 与实际一致 | 四条均吻合 | PASS |
| 12 | 交接 §6 哈希准确性 | README/OPERATIONS 匹配；workflows 过期 | **N-1（Low）** |

**DOCS_VERDICT: PASS**（N-1 为 Low 元数据问题，不阻断）。

## 10. NOT VERIFIED / 边界

1. `test-run --trusted`（WSL2 隔离）未执行；仅沿用 R1/先前复核的静态结论。
2. 未重跑 B0–B5B/H1 的独立场景；本轮仅重跑发布文档脚本与全量默认 pytest。
3. 未复核生产 anchor、ACL、POSIX 安装、WSL2 attestation 真实性等 `REVIEW-FINAL` §5 既有未验证项。
4. 未联网查询 tag/Release；未合并、未 Approve、未打 tag、未建 PR；未修改 `pm-pilot-02`。
5. 本报告不构成 v1.0 GO；发布决定属人类审批者。

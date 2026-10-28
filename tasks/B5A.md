# B5A — CLI 不得被同名 `project_memory` 模块顶替

- 任务 ID：`B5A`
- 状态：`draft`（派发前冻结）
- 优先级：P0 / security
- 来源：B1 独立复核 HIGH（`pilot/rounds/B1/handoff-close.md` §5）
- 说明：`B5A` 是 B1 发现的新 HIGH，**不是** RC3 的 B5（默认 `test-run` 隔离，另作 `B5B`）
- 基线：`dev/v1.0` 的 B5A 任务卡合并提交；精确 SHA 见 Issue
- 候选分支：`fix/b5a-module-shadowing`
- Goal：`G-B5A`
- 依赖：B0/B1/B2/B3 已合并

## 1. 问题

`project_memory` 是普通 Python 包。以下任一方式都可能让**同名恶意包**先被导入：

1. cwd 下放一个 `project_memory/`，再 `python -m project_memory ...`；
2. `PYTHONPATH=/tmp/shadow`，其中放 `project_memory/`；
3. 通过 console script 启动，但 `PYTHONPATH` 仍可前插同名包。

一旦恶意包被导入，CLI 的验签、收据、Goal 状态机都可能是假的；用户以为在跑受信工具，实际在跑攻击者代码。B1 复核已确认基线同样成立。

`test-run` 的 `_local_env` 已剥离 `PYTHONPATH`/`PYTHONHOME` 并把 `PYTHONPATH` 设为快照树；这只能保护子进程，**不能保护 CLI 自身**。

## 2. 目标

- 受信 CLI 启动时不得导入 cwd/`PYTHONPATH` 中的同名包；
- 无法保证时 **fail closed**，而不是静默运行；
- 正常安装/正常 `python -m project_memory` 仍可用；
- `test-run` 不因本修复回归；
- 不靠“让用户自己加 `-I`”作为唯一修复。

## 3. 范围

允许修改：

- `project_memory/__main__.py`、`project_memory/cli.py`（只在必要时）
- 新的 bootstrap/launcher 入口（包外或独立脚本）
- `pyproject.toml`/打包入口（console script）
- `project_memory/execution.py`（如子进程环境需要补充）
- `tests/`、`docs/decisions/`、`docs/` 启动/部署文档
- `evidence/B5A/`

不允许：

- 修改 B0–B3 的判据/任务卡/冻结候选；
- 放宽 authority/签名/来源门禁；
- 删除/跳过既有测试；
- 只改文档、只要求用户加 `-I`；
- 把 B5B（默认 `test-run` 隔离）夹带进来。

## 4. 设计选项（PM-02 选一个并写 ADR）

1. **独立 bootstrap + 隔离解释器**
   - 入口脚本在导入 `project_memory` 之前，用绝对路径的受信 Python 启动 `-I -P -m project_memory`（或等价隔离）；
   - 校验 `project_memory.__file__` 位于安装根，否则拒绝；
   - console script 指向该 bootstrap，而不是直接 import 包。
2. **启动时校验 + fail closed**
   - 在包导入后检查 `__file__`/`sys.path` 是否可信；不可信则非零退出；
   - 注意：恶意包可能已经执行，所以此方案只能作为纵深防御，不能单独作为主方案。
3. **子进程环境加固**
   - `test-run` 已剥离 `PYTHONPATH`/`PYTHONHOME`；补充 `-P`/`PYTHONSAFEPATH`、cwd 校验；
   - 记录 receipt 的环境清理状态。

必须在 ADR 说明：为什么“只检查 `__file__`”不够、攻击者能否在检查前执行代码、Windows/POSIX 差异。

## 5. 验收标准

| AC | 判据 | 方法 | 通过条件 |
|---|---|---|---|
| AC-1 | `PYTHONPATH` 假冒包不能劫持 CLI | 构造 `/tmp/shadow/project_memory/__init__.py` 写 marker | marker 不出现；CLI 拒绝或使用受信包 |
| AC-2 | cwd 假冒包不能劫持 CLI | cwd 放 `project_memory/`，`python -m project_memory` | 同上 |
| AC-3 | console script 不被 `PYTHONPATH` 劫持 | 用安装入口 + 恶意 `PYTHONPATH` | 同上 |
| AC-4 | 正常调用仍可用 | 正常安装/正常 cwd | `--help`/基本命令成功 |
| AC-5 | `test-run` 不回归 | 恶意 `PYTHONPATH` + 子进程 | 子进程不导入假冒包；收据记录环境清理 |
| AC-6 | 失败关闭 | 无法证明受信时 | 非零退出；不执行命令、不写“成功”收据 |
| AC-7 | 回归 | 213 passed / 2 skipped + 新增 | 全绿；无删除/跳过 |
| AC-8 | ADR/文档 | 启动模型、威胁边界、残余风险 | 与实现一致 |
| AC-9 | 证据 | 命令/退出/marker/日志/哈希 | 可复现 |
| AC-10 | 独立复核 | PM-03/独立审查者 | 负例“成功即 FAIL” |

## 6. 防作弊判据

以下“修复”判 **FAIL**：

1. 只在 `__main__` 里检查，但恶意包已经被导入；
2. 只检查 `PYTHONPATH` 环境变量，不检查 cwd/console script；
3. 只改文档，要求用户加 `-I`；
4. 让所有 CLI 调用都失败（AC-4 失败）；
5. 删除/跳过既有测试；
6. 放宽 authority/签名/来源门禁；
7. 把 marker 文件写进 fixture 目录就算“已阻止”。

## 7. Fixtures

- `fixtures/b5a/shadow/project_memory/__init__.py`：写 `SHADOW_MARKER`（不得执行成功）；
- `fixtures/b5a/cwd-shadow/project_memory/__main__.py`：cwd 劫持；
- `fixtures/b5a/run_matrix.sh`：四组正负命令；
- 由 PM-01 生成/维护；PM-02 可自建测试夹具，但最终审查用 PM-01 fixture。

## 8. 证据包

```
evidence/B5A/<run-id>/
  README.md
  environment.txt
  commands.jsonl
  shadow-pythonpath.json
  shadow-cwd.json
  shadow-console.json
  normal.json
  test-run-env.json
  pytest.log
  diffstat.txt
  sha256sums.txt
```

## 9. 判定语义

| 结论 | 条件 |
|---|---|
| **PASS** | AC-1..AC-10 全部满足；假冒包 marker 不出现；正常调用可用 |
| **FAIL** | 任一劫持成功；或所有调用被拒；或只做文档 |
| **BLOCKED** | 环境/安装/权限不可用 |
| **NOT VERIFIED** | 有 AC 未运行；整体不得记 PASS |

## 10. 不在范围

- B5B 默认 `test-run` 隔离、WSL_EXE；
- B4 审计防篡改；
- Release/部署；
- 人类身份/审批。

## 11. 阅读顺序

`pilot/PILOT_CLOSEOUT.md` → `pilot/rounds/B1/handoff-close.md` §5 → 本任务卡 → `project_memory/__main__.py`、`execution.py::_local_env`。

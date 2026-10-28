# ADR-0005：CLI 启动引导与同名包顶替防护（B5A）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28
- 任务：B5A（Issue #20）
- 基线：`ddd9dba28d518339348f55ebcc382aba070782d8`
- 影响范围：新增 `_project_memory_launcher.py`（包外启动器）、`project_memory/__main__.py`（启动守卫）、`pyproject.toml`（console script 与 `py-modules`）、`project_memory/execution.py`（`_local_env` 与收据环境记录）、`tests/test_security_b5a.py`（新增）、启动/运维文档、本文档
- 不涉及：`authority`/签名信任模型、`execution_provenance`/B2 来源门禁、Goal/判据语义、B5B 默认 `test-run` 隔离、B4、WSL_EXE、Release

## 1. 背景与问题

`project_memory` 是普通 Python 包，CLI 入口是 `python -m project_memory` 或 console script `project-memory`。两者在启动时都按 `sys.path` 解析 `project_memory`：

- `python -m project_memory`：`sys.path[0]` 是当前工作目录；
- `PYTHONPATH`：插在 cwd 之后、stdlib/site-packages 之前；
- console script（pip 生成）：脚本体是 `from project_memory.cli import main`，同样受 `sys.path` 影响。

因此 cwd 或 `PYTHONPATH` 中的同名包会先于受信包被导入。基线已复现：两条劫持命令输出 `SHADOW_INIT` / `SHADOW_MAIN` 并 exit 0（fixtures README，2026-10-28）。被顶替后，验签、收据、Goal 状态机全部是攻击者代码，用户却以为在运行受信 CLI。

`test-run` 的 `_local_env` 只保护子进程：它剥离 `PYTHONPATH`/`PYTHONHOME` 并把 `PYTHONPATH` 指向快照树，**不能保护 CLI 自身**，也没有 `PYTHONSAFEPATH`/用户站点隔离与收据中的清理记录。

## 2. 威胁模型

| 入口 | 攻击者控制点 | 谁先执行 |
|---|---|---|
| `python -m project_memory` | cwd（`sys.path[0]`）、`PYTHONPATH`、用户站点 | 同名包的 `__init__.py`，**早于** `project_memory/__main__.py` |
| console script | `PYTHONPATH`、用户站点、脚本导入名 | 同名包的 `__init__.py`，**早于** pip 脚本的 `import` |
| `python -I -P -m project_memory` | 无（`-I` 忽略 `PYTHONPATH`/用户站点，`-P` 不前置 cwd/脚本目录） | 仅安装根中的受信包 |
| 启动器（本 ADR） | 启动器模块自身、解释器路径 | 启动器先于包导入；它在**导入包之前**换成隔离解释器 |

信任根是“受信解释器 + 受信安装根”。攻击者若能改写解释器、site-packages 或启动器模块本身，已等价于整进程替换，见 §7。

## 3. 为什么“导入后检查 `project_memory.__file__`”不够

一旦同名包的 `__init__.py` 被解析为入口，它已经执行——可以打印、写文件、退出、甚至伪造后续所有输出。此时再在 `__main__.py` 或 `cli.py` 里检查 `__file__`：

- 检查代码根本没机会运行（攻击包自己实现 `__main__` 并 exit 0）；
- 或者检查的是攻击包自己的 `__file__`，可以随意伪装成安装根路径；
- 环境变量（`PYTHONPATH`）检查同样在导入之后，无法补救已执行的代码。

结论：**检查只能作为纵深防御；主防线必须是“在导入包之前就用隔离解释器启动”**。

## 4. 决策

采用“独立启动器（主）+ 包内 fail-closed 守卫（纵深）+ 子进程环境加固（配套）”三层。

### 4.1 主防线：包外启动器 `_project_memory_launcher.py`

- 模块位于**包外**（安装后位于 site-packages 根），名称与 `project_memory` 不同，因此“顶替 `project_memory`”不会自动顶替启动器。
- `[project.scripts] project-memory = "_project_memory_launcher:main"`：console script 指向启动器，而不再直接导入 `project_memory.cli`。
- 启动器**不导入 `project_memory`**；它构造子进程：
  - 解释器：`sys.executable`，必须是绝对路径且存在，否则 exit 3；
  - 参数：`-I -P`（`-I` 隔离：忽略 `PYTHONPATH`、用户站点，且不把脚本目录放入 `sys.path`；`-P` 显式禁止 cwd 前置）；
  - 环境：丢弃 `PYTHONPATH`/`PYTHONHOME`/`PYTHONSTARTUP`/`PYTHONUSERBASE`/`PYTHONSAFEPATH`/`PYTHONNOUSERSITE`，设置 `PYTHONNOUSERSITE=1`、`PYTHONSAFEPATH=1`；
  - 目标：启动器所在目录含 `project_memory/__init__.py` 时，用 `-c` 显式把该受信根插入 `sys.path` 后调用 `project_memory.cli.main`；否则 `-m project_memory`。
- 启动器所在目录即信任根：能被解析并执行启动器，说明该目录已被信任；攻击者若能顶替启动器模块名或改写该文件，已是整进程替换（§7）。
- 失败关闭：解释器不可信或子进程无法建立 → exit 3，不执行任何 CLI 命令、不写收据。

### 4.2 纵深：`python -m project_memory` 的启动守卫

`project_memory/__main__.py` 在调用 `cli.main` 之前：

1. `sys.flags.isolated and sys.flags.safe_path` 为真 → 解释器级隔离，直接运行；
2. 否则扫描 `sys.path`：任一条目（除受信根自身）存在 `project_memory/__init__.py` → **fail closed**（exit 3），错误信息写明“检测到同名包 + 路径”，不执行命令、不写“成功”收据；
3. 包路径不是绝对路径 → fail closed；
4. 无污染痕迹 → 正常运行（保持 `PYTHONPATH=. python3 -m project_memory` 等既有开发用法）。

**局限（必须明示）**：若同名包已在解析阶段胜出，本守卫不会运行；它只能拦截“受信包已导入、但 `sys.path` 上仍有同名包”的污染，例如仓库 cwd 在前、`PYTHONPATH` 另有假冒包的场景。它不是主防线。

### 4.3 配套：`test-run` 子进程环境加固

- `_local_env` 在原有剥离 `PYTHONPATH`/`PYTHONHOME` 与敏感名的基础上：
  - 额外剥离 `PYTHONSTARTUP`/`PYTHONUSERBASE`/`PYTHONSAFEPATH`/`PYTHONNOUSERSITE` 的宿主值；
  - 设置 `PYTHONSAFEPATH=1`（Python ≥3.11 的子进程不把 cwd/脚本目录前置）与 `PYTHONNOUSERSITE=1`；
  - `PYTHONPATH` 仍只指向不可变快照树；cwd 仍是快照树。
- 收据 `isolation.python_env` 记录清理状态：`path_source=snapshot-only`、`safepath=true`、`nousersite=true`、被剥离的变量名列表（只记名字，不记值）。
- `extra_env` 注入 `PYTHONPATH`/`PYTHONHOME` 及新增路径变量的行为继续拒绝。

## 5. 平台与打包差异

| 场景 | 行为 |
|---|---|
| POSIX 安装 | console script → 启动器；启动器 `exec` 子进程（`subprocess.call`），`-I -P` 与 POSIX 一致 |
| Windows 安装 | pip 生成 `.exe` 启动器，同样调用 `_project_memory_launcher:main`；`-I -P` 在 3.11+ 可用；`sys.executable` 为绝对路径 |
| checkout（未安装） | `python -m project_memory` 可用（守卫生效）；启动器以脚本方式运行（`python _project_memory_launcher.py`）时，信任根为启动器所在目录 |
| 可编辑安装 | 子进程 `-I -P` 仍能看到 site-packages 的 editable `.pth`；信任根为 site-packages |
| 直接 `python -I -P -m project_memory` | 视为受信入口（无需启动器），守卫按隔离标志放行 |
| 原始 `python -m project_memory`（未隔离） | 尽力而为：可检测时 fail closed；cwd/PYTHONPATH 假冒包已在解析阶段胜出时无法拦截（§7） |

## 6. 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 只改文档、要求用户加 `-I` | 任务卡明令禁止作为唯一修复；用户仍会误用裸入口 |
| 只检查 `PYTHONPATH` 环境变量 | 覆盖不了 cwd（`sys.path[0]`）与 console script；且检查发生在导入之后 |
| 只检查 `project_memory.__file__` | 假冒包的 `__init__` 已执行，检查可能根本轮不到；路径可伪装 |
| 只改 console script 指向 `project_memory.cli:main` | 仍然是包导入，`PYTHONPATH` 可顶替 |
| 安装级 `sitecustomize`/`.pth` 全局钩子 | 对解释器全局生效、易与其他工具冲突；`.pth` 的 `import` 行本身可被 `PYTHONPATH` 顶替成执行载体；属于安装器/发布范围（本任务停止条件），本轮不做 |

## 7. 残余风险

1. **解释器/启动器被替换**：攻击者能改写 `sys.executable` 指向的解释器、site-packages，或顶替启动器模块名——等价于整进程替换，任何进程内防护都失效。
2. **原始裸入口**：`python -m project_memory` 在 cwd 或 `PYTHONPATH` 已有同名包并胜出时，受信代码不会执行；本轮只能通过启动器/隔离标志规避，并在可检测污染时 fail closed。
3. **安装目录可写**：site-packages 或 checkout 对攻击者可写时，受信包本身可被改写。
4. **用户显式绕过**：`PYTHONPATH` 指向不可信包并直接调用该包，属于用户主动选择；产品只能保证自身的受信入口。
5. **共享解释器的其他钩子**：`usercustomize`、`.pth`、审计钩子等若由第三方控制，不在本设计防护范围。
6. **子进程**：`test-run` 只加固 Python 解释器的路径解析；非 Python 子进程、被测试代码自身的动态加载不在本轮范围（B5B）。

## 8. 与任务卡 AC 的对应

| AC | 本 ADR 对应 |
|---|---|
| AC-1 | §4.1 启动器 + §4.2 守卫（PYTHONPATH 场景；原始裸入口边界见 §7.2） |
| AC-2 | §4.1 启动器（cwd 场景） |
| AC-3 | §4.1 console script 指向启动器 |
| AC-4 | §4.2 无污染时正常放行 |
| AC-5 | §4.3 `_local_env` 加固 + 收据 `isolation.python_env` |
| AC-6 | 启动器 exit 3、守卫 exit 3；不执行命令、不写收据 |
| AC-7 | 既有测试不动，新增 `tests/test_security_b5a.py` |
| AC-8 | 本文档 |

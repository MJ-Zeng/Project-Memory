---
id: "ADR-0005"
status: "proposed"
owner: "MJ-Zeng"
related_issues: [20]
---

# ADR-0005：CLI 启动引导与同名包顶替防护（B5A）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28；B5A.1 整改：2026-10-29
- 任务：B5A（Issue #20），B5A.1 整改（PR #22）
- 基线：`ddd9dba28d518339348f55ebcc382aba070782d8`
- 影响范围：新增 `bin/project-memory`（POSIX）与 `bin/project-memory.cmd`（Windows）原生入口包装器、`_project_memory_launcher.py`（包外启动脚本，按绝对路径调用）、`project_memory/__main__.py`（启动守卫）、`pyproject.toml`（移除 `module:function` console script，改用 `script-files` 安装原生包装器）、`project_memory/execution.py`（`_local_env` 与收据环境记录）、`tests/test_security_b5a.py`、启动/运维文档、本文档
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
| pip `module:function` console script（B5A 原候选，**已废弃**） | `PYTHONPATH`、用户站点、cwd（当 cwd 在 `sys.path` 时）、被导入的顶层模块名 | pip 生成的 `from _project_memory_launcher import main` 在**任何隔离之前**按环境 `sys.path` 解析顶层模块名；同名文件抢先执行（`FAKE_LAUNCHER`），受信启动器根本不运行 |
| `python -I -P -m project_memory` | 无（`-I` 忽略 `PYTHONPATH`/用户站点，`-P` 不前置 cwd/脚本目录） | 仅安装根中的受信包 |
| **原生 OS 包装器（本 ADR 采纳）** `bin/project-memory[.cmd]` | 包装器文件自身、解释器路径 | 包装器是原生脚本（经 OS `PATH`/绝对路径调用，**不经 `sys.path`**）；它先以 `-I -P` 启动解释器，再按**绝对路径**运行启动脚本——顶层模块名从不被 `sys.path` 解析 |
| 启动脚本 `_project_memory_launcher.py` | 脚本文件自身、解释器路径 | 由包装器按绝对路径、在 `-I -P` 下运行；它在导入包之前定位受信根并换成隔离解释器 |

信任根是“受信解释器 + 受信安装根”。攻击者若能改写解释器、site-packages、原生包装器或启动脚本本身，已等价于整进程替换，见 §7。

**B5A.1 关键更正**：B5A 原候选把 console script 指向 `_project_memory_launcher:main`，误以为“启动器在包外就不会被顶替”。PM-01 复现证明这是错的——`module:function` 形式在加载入口时**已经过一次 `sys.path` 解析**，`PYTHONPATH`（以及 cwd 在 `sys.path` 上的调用形式）里的同名 `_project_memory_launcher.py` 会先于受信启动器执行，输出 `FAKE_LAUNCHER` 并 exit 0，主防线根本不运行。根因是“受信入口本身是一个由 `sys.path` 解析的顶层 Python 模块”。因此受信入口必须**在解析任何顶层模块名之前**就完成隔离，且不能是可按名字导入的模块——见 §4.1。

## 3. 为什么“导入后检查 `project_memory.__file__`”不够

一旦同名包的 `__init__.py` 被解析为入口，它已经执行——可以打印、写文件、退出、甚至伪造后续所有输出。此时再在 `__main__.py` 或 `cli.py` 里检查 `__file__`：

- 检查代码根本没机会运行（攻击包自己实现 `__main__` 并 exit 0）；
- 或者检查的是攻击包自己的 `__file__`，可以随意伪装成安装根路径；
- 环境变量（`PYTHONPATH`）检查同样在导入之后，无法补救已执行的代码。

结论：**检查只能作为纵深防御；主防线必须是“在导入包之前就用隔离解释器启动”**。

## 4. 决策

采用“独立启动器（主）+ 包内 fail-closed 守卫（纵深）+ 子进程环境加固（配套）”三层。

### 4.1 主防线：原生 OS 包装器 → 隔离解释器 → 绝对路径启动脚本

受信入口分两级，核心是“**在解析任何顶层 Python 模块名之前就完成隔离**”：

**第 0 级 — 原生 OS 包装器（`bin/project-memory` / `bin/project-memory.cmd`）**

- 是原生 shell / cmd 脚本，经 OS `PATH` 或绝对路径调用，**不经过 Python `sys.path`**，因此 `PYTHONPATH`/cwd 里的同名 `.py` 无法顶替它。
- 它做的第一件事就是用 `-I -P` 启动解释器：`-I`（隔离）忽略 `PYTHONPATH`/用户站点、不前置脚本目录；`-P`（safe path）不前置 cwd。隔离在**任何 Python 代码运行之前**由 OS 层建立。
- 它按**绝对路径**运行启动脚本（`<trusted>/_project_memory_launcher.py`），而不是 `import _project_memory_launcher`——顶层模块名从不被 `sys.path` 解析，`FAKE_LAUNCHER` 无从注入。
- 解释器选择顺序：`PROJECT_MEMORY_PYTHON`（显式覆盖）→ 同目录 venv 解释器（`bin/python3`、`Scripts/python.exe`）→ `PATH` 上的 `python3`/`python`；都找不到则 exit 3。
- 启动脚本定位顺序：包装器同目录（安装布局）→ 包装器上级目录（checkout 布局）→ 找不到则 exit 3。

**第 1 级 — 启动脚本 `_project_memory_launcher.py`（包外、按绝对路径运行）**

- 位于**包外**，且**不再是可按名字导入的 console 目标**（已从 `py-modules`/`[project.scripts]` 移除）；只由包装器按绝对路径、在 `-I -P` 下运行。
- 它**不导入 `project_memory`**，而是定位受信根（自身所在目录）并构造子进程：
  - 解释器：`sys.executable`，必须是绝对路径，否则 exit 3；
  - 参数：`-I -P`；
  - 环境：丢弃 `PYTHONPATH`/`PYTHONHOME`/`PYTHONSTARTUP`/`PYTHONUSERBASE`/`PYTHONSAFEPATH`/`PYTHONNOUSERSITE`，设置 `PYTHONNOUSERSITE=1`、`PYTHONSAFEPATH=1`；
  - 目标：受信根含 `project_memory/__init__.py` 时，用 `-c` 显式把该受信根插入 `sys.path` 后调用 `project_memory.cli.main`（checkout 布局）；否则 `-m project_memory`（已安装到 site-packages 的布局）。
- 受信根即启动脚本所在目录：能被按绝对路径运行，说明该目录已被信任；攻击者若能改写该文件或包装器、替换解释器，已是整进程替换（§7）。
- 失败关闭：解释器不可信、找不到启动脚本或子进程无法建立 → exit 3，不执行任何 CLI 命令、不写收据。

> 为什么不能继续用 pip `[project.scripts]`：pip 生成的入口体是 `from <module> import <func>`，`<module>` 必是按 `sys.path` 解析的顶层名，且这一步发生在**未隔离**的解释器里。无论把 `<module>` 取什么名字（`_project_memory_launcher`、`project_memory.*` 或任何“冷门”名），`PYTHONPATH`/cwd 都能前插同名文件抢先执行。这是 `module:function` 形式的固有缺陷，无法在其内部补救——受支持的入口必须换成原生包装器。见 §6。

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
| POSIX 安装 | `script-files` 把 `bin/project-memory`（sh）与 `_project_memory_launcher.py` 装入 `bin/`（同目录）；包装器 `exec python3 -I -P <bin>/_project_memory_launcher.py`，启动脚本再 `subprocess.call` 隔离子进程 |
| Windows 安装 | `script-files` 把 `bin/project-memory.cmd` 与 `_project_memory_launcher.py` 装入 `Scripts/`；`.cmd` 调用 `python.exe -I -P <Scripts>\_project_memory_launcher.py`；`-I -P` 在 3.11+ 可用；`sys.executable` 为绝对路径 |
| checkout（未安装） | 包装器在 `bin/`，启动脚本在仓库根（包装器上级目录），包装器按 `../_project_memory_launcher.py` 定位；信任根为仓库根。`python -m project_memory` 亦可用（守卫生效） |
| 直接运行启动脚本 | `python _project_memory_launcher.py`（未隔离）仍安全：启动脚本换成隔离子进程；这是既有测试路径 |
| 可编辑安装 | 子进程 `-I -P` 仍能看到 site-packages 的 editable `.pth`；信任根为启动脚本所在目录 |
| 直接 `python -I -P -m project_memory` | 视为受信入口（无需包装器），守卫按隔离标志放行 |
| 原始 `python -m project_memory`（未隔离） | 尽力而为：可检测时 fail closed；cwd/PYTHONPATH 假冒包已在解析阶段胜出时无法拦截（§7.2） |
| **`[project.scripts]` console script** | **不再提供**。pip 的 `module:function` 入口在未隔离解释器里按 `sys.path` 解析顶层模块名，`PYTHONPATH`/cwd 可抢先（B5A.1）；受支持入口改为原生包装器 |

> 打包说明：`script-files` 是 setuptools 的原始脚本安装机制（在当前 setuptools 80.x 仍可用，属已弃用键，可能产生弃用告警）。之所以用它而非 `[project.scripts]`，正是因为后者只会生成不安全的 `module:function` 入口。把原生包装器自动装入各平台的 `PATH` 目录、并处理可执行位/`.cmd` 关联，属于安装器/打包范畴；本轮提供机制、测试与文档，并把它作为已知的后续打包项（见 §7.7 与 handoff），不静默声称 `pip install` 一定生成 `PATH` 命令。

## 6. 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 只改文档、要求用户加 `-I` | 任务卡明令禁止作为唯一修复；用户仍会误用裸入口 |
| 只检查 `PYTHONPATH` 环境变量 | 覆盖不了 cwd（`sys.path[0]`）与 console script；且检查发生在导入之后 |
| 只检查 `project_memory.__file__` | 假冒包的 `__init__` 已执行，检查可能根本轮不到；路径可伪装 |
| 只改 console script 指向 `project_memory.cli:main` | 仍然是包导入，`PYTHONPATH` 可顶替 |
| **console script 指向 `_project_memory_launcher:main`（B5A 原候选）** | **PM-01 复现：`module:function` 在未隔离解释器里按 `sys.path` 解析 `_project_memory_launcher`，`PYTHONPATH`（及 cwd 在 `sys.path` 的调用形式）里的同名文件抢先执行 `FAKE_LAUNCHER`、exit 0，主防线根本不运行。“启动器在包外”不足以防护——入口模块名本身仍可被顶替** |
| 给启动器换一个“冷门”顶层模块名 | -security-by-obscurity：任何顶层名都可被 `PYTHONPATH`/cwd 前插同名文件顶替，换名不改变固有缺陷 |
| 安装级 `sitecustomize`/`.pth` 全局钩子 | 对解释器全局生效、易与其他工具冲突；`.pth` 的 `import` 行本身可被 `PYTHONPATH` 顶替成执行载体；属于安装器/发布范围（本任务停止条件），本轮不做 |

## 7. 残余风险

1. **解释器/包装器/启动脚本被替换**：攻击者能改写 `PATH` 命中的解释器、site-packages、原生包装器（`bin/project-memory[.cmd]`）或启动脚本——等价于整进程替换，任何进程内防护都失效。包装器经 OS `PATH`/绝对路径解析，不经 `sys.path`；把不可信目录放进 `PATH`（尤其 Windows 上 `.` 在 `PATH`）属于 OS 层配置风险。
2. **原始裸入口**：`python -m project_memory` 在 cwd 或 `PYTHONPATH` 已有同名包并胜出时，受信代码不会执行；本轮只能通过包装器/隔离标志规避，并在可检测污染时 fail closed。
3. **安装目录可写**：site-packages 或 checkout 对攻击者可写时，受信包本身可被改写。
4. **用户显式绕过**：`PYTHONPATH` 指向不可信包并直接调用该包，或**手写** `from _project_memory_launcher import main`（旧的 `module:function` 形式）——属于用户主动选择非受支持入口；产品只保证原生包装器这一受信入口，该 import 形式仍固有可被顶替，已在文档中标注为**不受支持**。
5. **共享解释器的其他钩子**：`usercustomize`、`.pth`、审计钩子等若由第三方控制，不在本设计防护范围。
6. **子进程**：`test-run` 只加固 Python 解释器的路径解析；非 Python 子进程、被测试代码自身的动态加载不在本轮范围（B5B）。
7. **打包自动化（后续项）**：本轮用 setuptools `script-files` 安装原生包装器（当前版本可用、属已弃用键）。把它稳健地装入各平台 `PATH` 目录、处理 POSIX 可执行位与 Windows `.cmd` 关联、以及跨 checkout/venv/系统安装的解释器发现，属于安装器/打包范畴；若需自定义 build backend 则触及任务停止条件，留作后续项，不在本轮静默声称完成。

## 8. 与任务卡 AC 的对应

| AC | 本 ADR 对应 |
|---|---|
| AC-1 | §4.1 原生包装器 + 启动脚本 + §4.2 守卫（PYTHONPATH 场景；原始裸入口边界见 §7.2） |
| AC-2 | §4.1 原生包装器（cwd 场景：`-P` 不前置 cwd，启动脚本按绝对路径运行） |
| AC-3 | §4.1 受支持 console 入口改为原生包装器（`bin/project-memory[.cmd]`），在解析任何顶层模块名前隔离；`[project.scripts] module:function` 已移除（§2 B5A.1 更正、§6） |
| AC-4 | §4.2 无污染时正常放行；包装器正常调用输出真实 help |
| AC-5 | §4.3 `_local_env` 加固 + 收据 `isolation.python_env` |
| AC-6 | 包装器/启动脚本 exit 3、守卫 exit 3；不执行命令、不写收据 |
| AC-7 | 既有测试保留，`tests/test_security_b5a.py` 新增 console 入口与打包守卫测试 |
| AC-8 | 本文档（含 B5A.1 整改） |

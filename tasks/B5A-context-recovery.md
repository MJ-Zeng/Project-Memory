# B5A 上下文恢复

- 任务：B5A（Issue #20）— CLI 不得被同名 `project_memory` 模块顶替
- 基线：`ddd9dba28d518339348f55ebcc382aba070782d8`（PR #21 merge commit）
- 任务卡：`tasks/B5A.md`，SHA-256 `88e31661ac766b7963ec655eb13de0e448ca51fa2e235cffc24161a1ef9681b9`（本会话实测一致）
- 候选分支：`fix/b5a-module-shadowing`（从 `ddd9dba` 新建）
- 接手分钟数：约 14 分钟（只读恢复 + 两条劫持复现 + 环境探测）

## 1. 六项事实

1. **任务/Issue/哈希一致**：工作树干净，`HEAD = ddd9dba`，任务卡哈希与派发值一致；`tasks/B5A.md`、`frozen/*`、B0–B3 任务卡本轮只读。
2. **威胁已在基线复现**（WSL Ubuntu / Python 3.14.4）：
   - `cd /tmp && PYTHONPATH=/mnt/c/.../fixtures/b5a/shadow python3 -m project_memory --help` → `SHADOW_INIT` / `SHADOW_MAIN` / exit 0；
   - `cd /tmp/b5a-cwd`（cwd 含 `project_memory/`）→ `SHADOW_INIT` / `SHADOW_MAIN` / exit 0；
   - 正常调用 `cd repo && PYTHONPATH=. python3 -m project_memory --help` → 真实用法 / exit 0。
3. **当前启动链**：`project_memory/__main__.py` 只做 `from .cli import main; raise SystemExit(main())`；`pyproject.toml` 的 console script 直接指向 `project_memory.cli:main`。两条入口都在**包导入之后**，而 cwd/PYTHONPATH 中的同名包会在导入阶段先执行——这正是任务卡 §6 防作弊第 1 条判 FAIL 的情形。
4. **`test-run` 现状**：`execution._local_env` 已剥离 `PYTHONPATH`/`PYTHONHOME` 与敏感名，并设 `PYTHONPATH=<快照树>`、`PYTHONDONTWRITEBYTECODE=1`；未设 `PYTHONSAFEPATH`/`PYTHONNOUSERSITE`；收据 `isolation` 未记录环境清理状态。cwd 为快照树。
5. **Fixtures 在仓库外**：`verification-lab/fixtures/b5a/{shadow,cwd-shadow}` 存在（只读，不修改）；任务卡 §7 提到的 `run_matrix.sh` **不存在**；fixtures README 的“正常调用”示例用 `PYTHONPATH=.`（即 checkout，未安装）。
6. **环境限制**：WSL Python 3.14.4 无 `pip`/`ensurepip`（`python3 -m venv` 失败），无法在 WSL 安装 console script；Windows Anaconda Python 3.12.4 的 venv + pip 24.0 可用，console script 用 Windows venv 测试。任务卡 AC-3 本身写明“如环境可安装”。

## 2. 必须询问的问题（不阻塞本轮）

1. **原始 `python -m project_memory` 的信任边界**：当 cwd/PYTHONPATH 中的同名包在解释器解析阶段胜出时，产品代码尚未获得执行机会，任何包内检查都无法阻止（等价于“整进程/模块解析被替换”）。本轮按 ADR-0005 选择“受信入口 = 启动器（隔离解释器）+ 包内可检测时 fail closed”，并在 Handoff 披露原始 `-m` 的残余风险；若审查要求“原始 `-m` 在恶意 PYTHONPATH 下也必须 fail closed”，需要安装级解释器钩子（如 sitecustomize/.pth），属于安装器范围，应另行授权。
2. 任务卡 §7 的 `run_matrix.sh` 缺失；本轮用自建矩阵脚本（不改 fixture），最终审查仍应以 PM-01 fixture 为准。
3. 顶层模块 `_project_memory_launcher.py`（包外）是否按“新的 bootstrap/launcher 入口（包外或独立脚本）”计入允许范围——按任务卡 §3 理解为允许。

## 3. contamination

- none。仅读取本 Clone、任务卡/试点文档、仓库外只读 fixtures 与环境信息；未读取主管/审查者会话、终端历史或工作树；未读 `key-a.pem`；未修改 fixture。

# REVIEW — B5A（CLI 不得被同名 `project_memory` 模块顶替）

- 审查：PM-03 Independent Reviewer（独立会话，程序性复核）
- 日期：2026-10-29
- 复审对象：B5A.1（上一候选 `85b1a4e` 的整改）
- 本报告**不是**安全认证，**不是** v1.0 GO；合并由人类决定。

---

## 0. 恢复（6 项事实 / 接手时间 / 待问 / 污染）

**6 项事实**

1. 任务是在受支持的 CLI 入口上防止同名 `project_memory`（及启动器模块 `_project_memory_launcher`）被 cwd/`PYTHONPATH` 顶替；被顶替则验签、收据、Goal 状态机全是攻击者代码。
2. 上一候选 `85b1a4e` 用 pip `[project.scripts] project-memory = "_project_memory_launcher:main"`（`module:function`）。该形式在**未隔离**解释器里按 `sys.path` 解析顶层模块名，`PYTHONPATH`/cwd 中的同名文件先执行（`FAKE_LAUNCHER`），主防线不运行 —— 这是 B5A.1 要修的阻断缺陷。
3. 基线 `ddd9dba`，候选 `9288818`（B5A.1）是基线后代，也是 `85b1a4e` 的后代；PR head `399ca2d` 仅比候选多出证据包与开发 Handoff，**无代码改动**。
4. 候选主防线：删除 `[project.scripts]` 与 `py-modules`，改由原生 OS 包装器 `bin/project-memory`（sh）/ `bin/project-memory.cmd` 启动：先 `-I -P` 起解释器，再**按绝对路径**运行包外 `_project_memory_launcher.py`；启动器再起隔离子进程从受信根导入 `project_memory`。
5. `project_memory/__main__.py` 守卫（检测 `sys.path` 上同名包 → exit 3）是**纵深防御**，ADR 明说它在假冒包已胜出时没有执行机会；裸 `python -m` 未隔离且假冒包先胜出是已披露残余（ADR §7.2）。
6. `test-run` 的 `_local_env` 增补剥离 `PYTHONSTARTUP/USERBASE/SAFEPATH/NOUSERSITE` 并置 `SAFEPATH=1/NOUSERSITE=1`，收据 `isolation.python_env` 记录清理；测试新增 `tests/test_security_b5a.py`，开发自报 226 passed / 2 skipped。

- 任务卡 SHA-256：`88e31661ac766b7963ec655eb13de0e448ca51fa2e235cffc24161a1ef9681b9`（**与给定一致**）。
- 候选/基线/PR head 一致，候选为基线后代 → **不 BLOCKED，继续**。

**接手分钟数**：约 **14 分钟**（读完收尾、B1 §5、任务卡、ADR、Handoff、fixtures、PR 元数据与候选代码，到可开始动态复现）。

**必须询问的问题（均非阻断）**

- RQ-1：POSIX 包装器按 `python3` 优先自动发现解释器；本机 PATH 上 `python3` 是 Windows Store 存根（rc 49）。是否接受“需 `PROJECT_MEMORY_PYTHON` 或健全的 `python3`”作为运行时前提，并在文档显式写明？
- RQ-2：本轮以已弃用的 setuptools `script-files` 交付原生包装器、把 `pip`/`PATH` 安装自动化列为后续项（ADR §7.7），是否被人类接受为 B5A 范围内？
- RQ-3：`_project_memory_launcher.py` 仍在仓库根、是可导入的顶层模块；旧的 `from _project_memory_launcher import main` 形式仍可被顶替。是否需后续把它移到不可按名导入的位置（本轮 ADR §7.4 已标为“不受支持”，非必需）。

**污染（contamination）**：none。独立会话，仅读 GitHub 工件 + 共享 `verification-lab/fixtures/b5a`；未读 PM-01/PM-02 的会话/终端/工作树；未读 `key-a.pem`。仅用本机 Git 凭据在内存中读取 PR #22 元数据（未落盘）。共享 fixture 原始哈希与开发 `environment.txt` 记录一致（`launcher-shadow`=`5a865e16…`、`shadow/__init__`=`e46bdb7a…`），证明用的是同一夹具、非特判。

---

## 1. 候选与标识

| 项 | 值 |
|---|---|
| 基线 | `ddd9dba28d518339348f55ebcc382aba070782d8` |
| 上一候选 | `85b1a4ecad13675a83cb8cf47b3e6cd7cf757672`（launcher module 可被顶替） |
| 候选（B5A.1） | `9288818351bcc4318ccde67b58d9abb07ac5d9e7` |
| PR head | `399ca2d868fc2c343e1fb9978c85a528f625e180`（= 候选 + 证据 + 开发 Handoff） |
| PR | https://github.com/MJ-Zeng/Project-Memory/pull/22 |
| 分支 | `fix/b5a-module-shadowing`；本审分支 `review/b5a-9288818`（基于候选） |
| 任务卡 | `tasks/B5A.md`，SHA-256 `88e31661…9681b9`（一致） |

候选→PR head 仅 `A tasks/B5A-handoff-run-20261029T001414Z.md` 与 `evidence/B5A/run-20261029T001414Z/`，无代码差异。

---

## 2. 静态检查

| 检查项 | 结果 |
|---|---|
| `pyproject.toml` 移除 `[project.scripts] project-memory=…` 与 `py-modules` | **是**（仅注释提及；`[tool.setuptools] packages=["project_memory"] + script-files=[…]`） |
| 原生包装器在导入任何顶层模块前完成隔离 | **是**（sh：仅 shell 内建 → `exec "$_py" -I -P "$_launcher"`；cmd：`set/if/where` → `"%PY%" -I -P "%LAUNCHER%"`） |
| 按**绝对路径**运行启动脚本，非 `module:function` | **是**（两包装器均传绝对路径 `_project_memory_launcher.py`） |
| 清除/固定 `PYTHONPATH`/`PYTHONHOME` 等 | **是**（解释器级 `-I` 忽略 `PYTHON*` 环境；启动器 `_trusted_env()` 再显式丢弃 6 个 `PYTHON*` 并置 `NOUSERSITE/SAFEPATH=1`） |
| 失败关闭 exit 3 | **是**（找不到启动脚本、找不到解释器、`sys.executable` 非绝对路径、子进程 `OSError`、`__main__` 守卫 → 均 exit 3） |
| `__main__.py` 守卫仅纵深、非主防线 | **是**（docstring + ADR §3/§4.2 明示；守卫在假冒包胜出时不执行） |
| `test-run` 的 `_local_env` 仍剥离 `PYTHON*` 并记录 `isolation.python_env` | **是**（`_PYTHON_PATH_VARS` 6 项；`python_env={path_source,safepath,nousersite,stripped}`） |
| 删除/跳过测试 | **否**（仅新增 `test_security_b5a.py`；无删除、无新增 skip/xfail） |
| 放宽 authority/签名/来源门禁 | **否**（代码改动仅 `.gitattributes`、`_project_memory_launcher.py`、两个 `bin/`、`__main__.py`、`execution.py`、`pyproject.toml`；未触 `authority/cli/goal/provenance`） |
| ADR-0005 说明 `module:function` 为何不够 / Windows·POSIX 差异 / 残余风险 | **是**（§2 威胁模型含 `module:function` 校正行；§4.1 引用块；§5 平台表；§6 被拒方案；§7 残余风险 7 条） |

静态结论：主防线与证据链自洽，未见放宽门禁或删测。

---

## 3. 动态复现矩阵

环境：Windows 11 / CPython 3.12.4（Anaconda）；POSIX 包装器经 Git Bash `sh` 执行，Windows 包装器经 `cmd.exe` 执行。共享夹具 `fixtures/b5a/{shadow,launcher-shadow,cwd-shadow}`；另用**自建 marker 夹具**（写 `B5A_MARKER` 文件）交叉验证。POSIX 包装器以 `PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python.exe` 固定解释器（见残留风险 R-1）。

| 入口 \ 恶意面 | 正常 | PYTHONPATH=fake launcher | PYTHONPATH=fake package | cwd=fake package | cwd+PYTHONPATH 混合 |
|---|---|---|---|---|---|
| **POSIX 包装器（checkout）** | exit0 真 help | exit0 无 FAKE | exit0 无 SHADOW | exit0 无 SHADOW | exit0 无 FAKE/SHADOW |
| **Windows 包装器（checkout）** | exit0 真 help | exit0 无 FAKE | exit0 无 SHADOW | exit0 无 SHADOW | — |
| **POSIX 包装器（venv 安装模拟）** | exit0 真 help | exit0 无 FAKE | exit0 无 SHADOW | exit0 无 SHADOW | — |
| **Windows 包装器（venv 安装模拟）** | exit0 真 help | exit0 无 FAKE | exit0 无 SHADOW | exit0 无 SHADOW | — |

- 所有“受支持入口”用例：`FAKE_LAUNCHER / SHADOW_INIT / SHADOW_MAIN` 均**未出现**，marker 文件**未写入**，输出真实 `用法：project-memory …`，exit 0。
- 夹具有效性（非特判）：同一 `launcher-shadow` 对**旧 `module:function` 探针**（`console_entry_probe.py`）在基线/上一候选/本候选均输出 `FAKE_LAUNCHER`、exit 0 —— 证明夹具确实能劫持 `module:function` 入口，而本候选的原生包装器不中招。

### 3.1 裸 `python -m` 残余（**记录，不计为通过**）

| 场景 | 结果 | 处置 |
|---|---|---|
| `cd /tmp && PYTHONPATH=shadow python -m project_memory --help` | exit0，`SHADOW_INIT`+`SHADOW_MAIN` | 固有边界：假冒包在解析阶段先执行，产品代码无机会运行 |
| `cd <cwd-shadow> && python -m project_memory --help` | exit0，`SHADOW_INIT`+`SHADOW_MAIN` | 同上（cwd 在 `sys.path[0]`） |
| `cd <repo> && PYTHONPATH=shadow python -m project_memory --help` | **exit3**，无 SHADOW，stderr 含“检测到同名…” | 守卫（纵深）在可检测污染时 fail closed |
| `python -I -P -m project_memory --help`（未安装） | exit1（ModuleNotFoundError），无 SHADOW | 隔离生效；未安装不可用 |

**判定**：候选**没有**把裸 `python -m` 当作受支持入口——ADR §7.2、§5、Handoff §6.1 均明确其为残余/不受支持，受信入口是原生包装器。符合复核口径“裸 `-m` 明确标为不支持入口并记录”。

---

## 4. 上一候选对照

| 场景 | `85b1a4e`（`module:function`，已废弃） | `9288818`（原生包装器，本候选） |
|---|---|---|
| `pyproject.toml` 入口 | `project-memory = "_project_memory_launcher:main"` + `py-modules` | 无 `[project.scripts]`；`script-files` 安装原生包装器 |
| old-form 探针 + `PYTHONPATH=launcher-shadow` | **FAKE_LAUNCHER**，exit0 | **FAKE_LAUNCHER**（旧形式固有可顶替——已不再随包提供） |
| 实际受支持入口 + `PYTHONPATH=launcher-shadow` | （无原生包装器） | exit0，无 FAKE，真 help |
| 实际受支持入口 + `PYTHONPATH=shadow` / cwd | （启动器隔离，但入口可被顶替） | exit0，无 SHADOW，真 help |
| 基线 `ddd9dba` 裸 `-m` + `PYTHONPATH=shadow` | `SHADOW_INIT/MAIN`（基线易感） | 残余仍在（同上），属已披露边界 |

差异明确：**同一夹具**能劫持 `module:function`（旧探针），却劫持不了候选的原生包装器；不是 fixture 特判。

---

## 5. `test-run` 与回归

- 独立 `test-run` 探针（`probe_testrun.py`，用 `run_command` 在恶意宿主 `PYTHONPATH` 下执行子进程）：**9/9 断言为真**——宿主 `PYTHONPATH` 不泄漏、子进程 `PYTHONPATH=快照树`、`SAFEPATH=1`、`NOUSERSITE=1`、`sys.path[0]=快照树`、泄漏模块不可导入、假 package 未执行（无 `SHADOW_INIT`）、收据 `isolation.python_env.{safepath,nousersite}=true` 且 `stripped` 含 `PYTHONPATH`。
- 全量测试（`C:\SoftWare\Anconda\python.exe -m pytest -q -p no:cacheprovider`）：
  - 基线 `ddd9dba`：**213 passed, 2 skipped**（skip 为 `tests/test_security_rc3.py` 既有 Windows 符号链接用例）。
  - 候选 `9288818`：**226 passed, 2 skipped**（+13，全部为 B5A 新增；同样 2 个既有 symlink skip）。
  - 单跑 `tests/test_security_b5a.py`：**13 passed**。
  - 无删除测试、无新增 skip/xfail、无门禁回归。

---

## 6. 新发现（按严重度）

- **无 HIGH / 阻断。** 核心修复（受支持入口在解析任何顶层模块名前隔离）成立。
- **LOW（环境/可用性，非安全回归）**：POSIX 包装器按 `python3` → `python` 优先自动发现解释器；本机 PATH 上 `python3` 是 Windows Store 存根，导致 `exit 49`、无输出（未执行任何 `project_memory` 代码，未中招）。需 `PROJECT_MEMORY_PYTHON` 或健全的 `python3`。建议文档显式写明该前提与覆盖变量。
- **LOW（打包）**：`script-files` 为 setuptools 已弃用键；`pip`/`PATH` 安装自动化未交付（ADR §7.7 已披露）。我只做了“venv + 手工拷贝”的安装布局模拟，未跑真实 `pip install`。
- **INFO（残余向量）**：`_project_memory_launcher.py` 仍在仓库根、可被 `import` 导入；旧的 `from _project_memory_launcher import main` 仍可被 `PYTHONPATH` 顶替（已复现 `FAKE_LAUNCHER`）。候选已移除随包提供的该入口，ADR §7.4 标为“不受支持”；可选后续将其移到不可按名导入的位置。
- **INFO（残余）**：裸 `python -m` 且假冒包先胜出仍执行假冒包 —— 固有边界，已文档化，非通过项。
- **INFO（鲁棒性）**：包装器 exit 3 仅覆盖显式条件；若 `PROJECT_MEMORY_PYTHON` 指向不可执行文件，`exec`/`%PY%` 返回 shell 的 126/127 而非 3（仍非零、未执行命令）。

---

## 7. 残余风险 / NOT VERIFIED

- **NOT VERIFIED — 真实 `pip install`（setuptools `script-files`）**：可执行位、Windows `.cmd` 关联、装入 `bin/`/`Scripts/` 的最终行为未经真实 `pip` 跑；我只做了手工安装布局模拟。
- **NOT VERIFIED — 真 POSIX 主机安装**：POSIX 包装器在 Git Bash checkout + venv 模拟下通过，未在真实 POSIX 安装后端到端跑。
- **NOT VERIFIED — Windows Store `python3` 前提**：本机 POSIX 包装器自动发现需覆盖变量（见 R-1）。
- **BY DESIGN（非通过项）**：裸 `python -m` 在 cwd/`PYTHONPATH` 先胜出时的假冒执行（ADR §7.2）。
- 解释器/包装器/启动脚本被改写 = 整进程替换（ADR §7.1），不在进程内防护范围。

以上未验证项**不属于任务卡 AC 的缺口**（AC-1..AC-10 均已在本轮运行）；它们是打包/部署层面的已知后续项（ADR §7.7）。

---

## 8. 与开发自报的差异

- 测试计数**一致**：开发自报 226/2，我独立复跑 226/2（基线 213/2，+13）。
- 夹具哈希**一致**：我用共享 `fixtures/b5a`，哈希与开发 `environment.txt` 所记相同（非特判）。
- 裸 `-m` 残余**一致**：开发 `bare/residual-*` 记 `SHADOW_INIT`，我独立复现同结果（均标为残余、非通过）。
- 开发 Handoff §2 称“启动脚本与 `__main__.py` 逻辑未改”——我核对 `85b1a4e..9288818` 增量：二者仅 docstring 变化，符合。
- 新增：我额外做了 **POSIX+Windows 双端“安装布局”模拟**（venv 手工安装）与 **自建 marker 夹具**交叉验证；开发将 POSIX 安装列为 NOT VERIFIED，我补充了 POSIX 安装布局模拟（仍非真实 `pip`）。
- 无“把残余写成通过”的表述；开发未宣布 PASS。

---

## 9. 最终判定

**VERDICT: PASS**（程序性独立复核，非安全认证，非 v1.0 GO；合并由人类决定）

依据：
- 受支持入口（原生包装器，POSIX+Windows，checkout+安装模拟）在 fake launcher / fake package / cwd / 混合场景下均**未被顶替**：无 `FAKE_LAUNCHER`/`SHADOW_*`、marker 未写入、真实 help、exit 0。
- `pyproject.toml` 已移除 `module:function` 入口；包装器在解析任何顶层模块名前 `-I -P` 隔离并绝对路径启动。
- 正常调用可用；`test-run` 环境清理与收据 `python_env` 正确；回归 226 passed / 2 skipped，无删测/新增 skip/门禁放宽。
- 裸 `python -m` 明确标为不受支持并记录残余（不计入通过）。

---

## 10. 污染 / 偏差 / 接手耗时

- **污染**：none（见 §0）。
- **偏差**：
  1. 在候选 worktree（`.pilot/b5a-candidate`）上创建 `review/b5a-9288818`，而非切换主 clone 的 `dev/v1.0`，以免扰动开发主线（等价于“基于候选建复审分支”）。
  2. PM-01 的 `fixtures/b5a/run_matrix.sh`（任务卡 §7 声明）不存在；我用自写 `drive.py`/`probe_testrun.py` 采集矩阵，**未修改**共享夹具。
  3. 安装布局以 `venv` + 手工拷贝模拟（非真实 `pip install`），已列入 NOT VERIFIED。
  4. POSIX 包装器在本机以上述 `PROJECT_MEMORY_PYTHON` 固定解释器运行（`python3` 为 Windows Store 存根）。
- **接手耗时**：约 **14 分钟**（上下文恢复至可复现）。
- **产物**：`review/B5A/REVIEW-B5A.md`、`evidence/B5A/review-20261029T011209Z/`。本审仅推 `review/b5a-9288818`；未合并、未 Approve、未 force push、未改 Goal。

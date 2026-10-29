# B5A.1 evidence pack — run-20261029T001414Z

- 任务：B5A.1 整改 —— 受支持的 console 入口不得被同名顶层模块 `_project_memory_launcher` 抢先执行（FAKE_LAUNCHER）。
- 基线：`ddd9dba28d518339348f55ebcc382aba070782d8`（PR #21 合并提交）。
- 上一候选（被 PM-01 复现阻断）：`85b1a4ecad13675a83cb8cf47b3e6cd7cf757672` —— pip `[project.scripts] project-memory = "_project_memory_launcher:main"`，`module:function` 形式在隔离之前经环境 `sys.path` 解析顶层模块名，可被同名 `.py` 前插顶替。
- 本候选：`9288818351bcc4318ccde67b58d9abb07ac5d9e7`（分支 `fix/b5a-module-shadowing`）—— 原生 OS 包装器（`bin/project-memory`、`bin/project-memory.cmd`）在解析任何 Python 模块名之前以 `-I -P` 启动解释器，并按**绝对路径**运行包外启动脚本；`pyproject.toml` 移除 `[project.scripts]`，改用 `script-files`。
- 任务卡 SHA-256：`88e31661ac766b7963ec655eb13de0e448ca51fa2e235cffc24161a1ef9681b9`
- 环境：Windows 10.0.26300 / Python 3.12.4（Anaconda）/ pytest 9.1.1；解释器 `C:\SoftWare\Anconda\python.exe`。
- fixture：`C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a`（未修改）。

本包只记录本轮实际执行的命令、输出与退出码，不包含任何 PASS / VERIFIED 结论；判定权归审查者 / 人类。

## 0. 阻断复现（针对上一候选 `85b1a4e` 的 pip 安装体）

`repro-blocker/` 保存了对**上一候选**入口的复现，证明 `module:function` console script 确实可被顶替：

| 文件 | 入口 / 恶意面 | exit | 输出 |
|---|---|---|---|
| `pythonpath-console-fake-launcher` | 上一候选 venv console `.exe`；`PYTHONPATH=<fixtures/launcher-shadow>` | 0 | `FAKE_LAUNCHER`（被顶替） |
| `pythonpath-probe-fake-launcher` | `python -c`（隔离前解析）；同上 `PYTHONPATH` | 0 | `FAKE_LAUNCHER` |
| `cwd-onpath-console-fake-launcher` | console 体，cwd 在 `sys.path` 上且含假冒 `_project_memory_launcher.py` | 0 | `FAKE_LAUNCHER` |
| `cwd-scriptdir-console-fake-launcher` | 探针被复制进攻击者 cwd（`sys.path[0]`=脚本目录） | 0 | `FAKE_LAUNCHER` |
| `cwd-console-real-exe` | console 体，cwd 含假冒但 cwd 不在 `sys.path` | 0 | 真实 help（未被顶替） |
| `cwd-windowsexe-not-preempted` | Windows `.exe` 入口，cwd 假冒不生效 | 0 | 真实 help |
| `normal-console` | console 体，无恶意面 | 0 | 真实 help |

结论：只要攻击者能让同名 `_project_memory_launcher.py` 出现在 `PYTHONPATH` 或 `sys.path` 上的 cwd，上一候选入口即打印 `FAKE_LAUNCHER`、exit 0，启动器主防线从不运行。这正是本候选要消除的入口。

## 1. 本候选用例矩阵（`results.json` / `commands.jsonl`）

### 1.1 checkout 布局原生包装器（`bin/project-memory.cmd --help`）

| case | 恶意面 | exit | FAKE_LAUNCHER | SHADOW | 真实 help |
|---|---|---|---|---|---|
| `candidate/normal` | 无 | 0 | 否 | 否 | 是 |
| `candidate/pythonpath-fake-launcher` | `PYTHONPATH=<fixtures/launcher-shadow>` | 0 | 否 | 否 | 是 |
| `candidate/cwd-fake-launcher` | cwd 含假冒 `_project_memory_launcher.py` | 0 | 否 | 否 | 是 |
| `candidate/pythonpath-fake-package` | `PYTHONPATH=<fixtures/shadow>` | 0 | 否 | 否 | 是 |
| `candidate/cwd-fake-package` | cwd 含假冒 `project_memory/` | 0 | 否 | 否 | 是 |
| `candidate/cwd-both-plus-pythonpath` | cwd 双假冒 + `PYTHONPATH` 假冒启动器 | 0 | 否 | 否 | 是 |

`checkout_marker_written=false`：所有用例均未写出攻击者标记文件。

### 1.2 pip 安装布局原生包装器（fresh venv，`Scripts/project-memory.cmd --help`）

`installed/pip-install` exit 0（`Successfully installed project-memory-skill-0.1.0`）；`Scripts/` 含 `project-memory`、`project-memory.cmd`、`_project_memory_launcher.py`。

| case | 恶意面 | exit | FAKE_LAUNCHER | SHADOW | 真实 help |
|---|---|---|---|---|---|
| `installed/normal` | 无 | 0 | 否 | 否 | 是 |
| `installed/pythonpath-fake-launcher` | `PYTHONPATH=<fixtures/launcher-shadow>` | 0 | 否 | 否 | 是 |
| `installed/pythonpath-fake-package` | `PYTHONPATH=<fixtures/shadow>` | 0 | 否 | 否 | 是 |
| `installed/cwd-both` | cwd 双假冒 | 0 | 否 | 否 | 是 |

`installed_info.marker_written=false`。安装布局下 `project_memory` 由 `-m` 从 site-packages 解析，假冒面全部无效。

### 1.3 裸 `-m` 边界（披露，非受支持入口）

| case | 入口 / cwd | exit | 结果 |
|---|---|---|---|
| `bare/guard-pythonpath-fake-package` | `python -m project_memory`（仓库内，受信根在 `sys.path`） | 3 | `__main__.py` 守卫 fail closed，无 help、无标记 |
| `bare/residual-bare-pythonpath-fake-package` | `python -m project_memory`（`/tmp`，`PYTHONPATH=<fixtures/shadow>`） | 0 | `SHADOW_INIT`（假冒包在模块解析阶段已胜出） |

`bare/residual-*` 是**已知残余风险**：裸 `-m` 属不受支持入口，解释器解析模块名时假冒包已胜出，产品代码尚未获得执行机会，包内检查无法拦截。受支持入口是原生包装器 / 绝对路径启动器 / `-I -P`；详见 `docs/decisions/ADR-0005-cli-bootstrap.md` §7.2。本包保留该行为作为披露，不视为通过。

### 1.4 test-run 子进程环境（`test-run-env.json`）

宿主 `PYTHONPATH=...\hostile` 下运行 `test-run`，子进程环境断言 7 项全部为 true：
`host_path_absent_from_child_env`、`child_pythonpath_is_snapshot`、`safepath_enabled`、`nousersite_enabled`、`sys_path0_is_explicit_pythonpath`、`shadow_probe_not_importable`、`receipt_records_python_env`。

### 1.5 测试

- `b5a-pytest.log`：`13 passed`（`tests/test_security_b5a.py`；含 `ConsoleEntryTest` 6 项 + `ShadowLaunchTest` + `LocalExecutionEnvTest`）。
- `pytest.log`：`226 passed, 2 skipped`（2 skipped 为既有 Windows symlink 用例，未删除、未跳过任何既有用例）。

## 2. AC 映射（Section 4 至少 7 项）

| # | 验收项 | 本包证据 |
|---|---|---|
| 1 | console 入口 + `PYTHONPATH` 假冒启动器 → 无 FAKE_LAUNCHER | `candidate/pythonpath-fake-launcher`、`installed/pythonpath-fake-launcher`（对照 `repro-blocker/pythonpath-console-fake-launcher`） |
| 2 | console 入口 + cwd 假冒启动器 → 无 FAKE_LAUNCHER | `candidate/cwd-fake-launcher`、`candidate/cwd-both-plus-pythonpath` |
| 3 | console 入口正常调用 → 真实 help | `candidate/normal`、`installed/normal` |
| 4 | 启动器 + 假冒 `project_memory` → 无 SHADOW_* | `candidate/pythonpath-fake-package`、`candidate/cwd-fake-package`、`installed/pythonpath-fake-package` |
| 5 | 裸 `-m` + 假冒 `project_memory` → 既有守卫 / 文档边界，无回归 | `bare/guard-*`（exit 3）、`bare/residual-*`（披露残余） |
| 6 | test-run 环境清理不回归 | `test-run-env.json`（7 断言 true）+ `tests/test_security_b5a.py::LocalExecutionEnvTest` |
| 7 | 既有 220 + 新增测试全绿 | `pytest.log`（226 passed / 2 skipped）、`b5a-pytest.log`（13 passed） |
| — | ADR / OPERATIONS / pyproject 打包入口更新 | `docs/decisions/ADR-0005-cli-bootstrap.md`、`docs/OPERATIONS.zh-CN.md`、`pyproject.toml`（代码提交 `9288818` 内） |
| — | 独立复核 | 不在本包；由 PM-03 / 人类另行执行 |

## 3. 目录结构

```text
run-20261029T001414Z/
├── README.md                     # 本文件
├── environment.txt               # 主机 / Python / fixture 哈希
├── commands.jsonl                # 逐条命令、退出码、结果摘要
├── diffstat.txt                  # git diff --stat ddd9dba 9288818
├── results.json                  # 结构化矩阵（checkout / installed / bare）
├── pytest.log                    # 全量测试（226 passed / 2 skipped）
├── b5a-pytest.log                # B5A 测试（13 passed）
├── test-run-env.json             # test-run 子进程环境断言（7 true）
├── repro-blocker/*.{out,err,exit}  # 上一候选 85b1a4e 的 FAKE_LAUNCHER 复现
├── candidate/*.{out,err,exit}    # 本候选 checkout 包装器原始输出
├── installed/*.{out,err,exit}    # 本候选 pip 安装包装器原始输出
├── bare/*.{out,err,exit}         # 裸 -m 守卫与残余原始输出
├── collect_evidence.py           # 矩阵采集器（只记录观测行为）
├── test_run_env_probe.py         # test-run 子进程环境探针
├── make_sha256sums.py            # 生成 sha256sums.txt
├── verify_hashes.py              # 校验 sha256sums.txt
└── sha256sums.txt                # 清单（不含自身）
```

## 4. 校验方法

```bash
python verify_hashes.py     # 期望：OK: <n> entries verified (LF-normalized); 0 external fixture record(s) not present
```

包内文件按 LF 归一化后的字节计算哈希（CRLF 工作树与 LF 检出均可校验）；外部 fixture `.py` 按原始字节计算，仅在文件存在时校验。

## 5. 边界与未证明

- 安装级验证只在 Windows venv 完成（`script-files` 把 `bin/project-memory`、`bin/project-memory.cmd`、`_project_memory_launcher.py` 装入 `Scripts/`）；未在 POSIX 安装布局端到端验证。
- `pyproject.toml` 使用 setuptools 已弃用的 `script-files`（80.9.0 仍可用）。跨平台 PATH 安装自动化（wheel 内置 wrapper、安装器脚本）作为后续项记录于 ADR §7.7，未在本轮实现。
- 裸 `-m` 且假冒包在模块解析阶段胜出的场景按设计无法拦截（ADR §7.2）；本包保留该基线行为作为披露。
- 不改 `authority` / 签名 / 来源门禁；不涉及 B5B / B4 / Release。
- 未验证 PyPI/wheel 之外的发行形态（single-file zipapp、系统包管理器脚本等）。

# B5A evidence pack — run-20261028T154334Z

- 任务：B5A CLI 不得被同名 `project_memory` 模块顶替
- 基线：`ddd9dba28d518339348f55ebcc382aba070782d8`（PR #21 合并提交）
- 候选：`85b1a4ecad13675a83cb8cf47b3e6cd7cf757672`（分支 `fix/b5a-module-shadowing`）
- 任务卡 SHA-256：`88e31661ac766b7963ec655eb13de0e448ca51fa2e235cffc24161a1ef9681b9`
- 环境：Windows 10.0.26300 / Python 3.12.4 / pytest 9.1.1；WSL Ubuntu 26.04 / Python 3.14.4（无 pip）
- fixture：`C:/Documents/02_Research/Code/project-memory-verification-lab/fixtures/b5a`（未修改）

本包只记录本轮实际执行的命令、输出与退出码，不包含任何 PASS / VERIFIED 结论。

## 1. 用例矩阵

### 基线（`ddd9dba`，假冒包成功即证明风险成立）

| case | 入口 | 恶意面 | exit | 假冒标记 | 真实 help |
|---|---|---|---|---|---|
| `baseline/shadow-pythonpath` | `python3 -m project_memory` | `PYTHONPATH=<fixtures/shadow>` | 0 | `SHADOW_INIT` / `SHADOW_MAIN` | 否 |
| `baseline/shadow-cwd` | `python3 -m project_memory` | cwd = 假冒包副本 | 0 | `SHADOW_INIT` / `SHADOW_MAIN` | 否 |
| `baseline/normal` | `python3 -m project_memory` | 无（仓库内） | 0 | 无 | 是 |
| `baseline/shadow-console` | `project-memory.exe`（venv） | `PYTHONPATH=<fixtures/shadow>` | 1 | `SHADOW_INIT`，随后 `ImportError: no project_memory.cli` | 否 |

### 候选（`85b1a4e`）

| case | 入口 | 恶意面 | exit | 假冒标记 | 真实 help |
|---|---|---|---|---|---|
| `candidate/shadow-pythonpath-launcher` | `_project_memory_launcher.py` | `PYTHONPATH=<fixtures/shadow>` | 0 | 无 | 是 |
| `candidate/shadow-cwd-launcher` | `_project_memory_launcher.py` | cwd = 假冒包副本 | 0 | 无 | 是 |
| `candidate/shadow-pythonpath-guard` | `python3 -m project_memory`（仓库内） | `PYTHONPATH=<fixtures/shadow>` | 3 | 无 | 否（fail closed） |
| `candidate/shadow-pythonpath-bare` | `python3 -m project_memory`（`/tmp`） | `PYTHONPATH=<fixtures/shadow>`（解析即胜出） | 0 | `SHADOW_INIT` / `SHADOW_MAIN` | 否 |
| `candidate/isolated-runpy` | `python3 -I -P -c`（显式受信根） | cwd + `PYTHONPATH` 均为假冒包 | 0 | 无 | 是 |
| `candidate/normal-bare` | `python3 -m project_memory`（仓库内） | 无 | 0 | 无 | 是 |
| `candidate/shadow-console` | `project-memory.exe`（venv） | `PYTHONPATH=<fixtures/shadow>` | 0 | 无 | 是 |
| `candidate/shadow-console-cwd` | `project-memory.exe`（venv） | cwd = 假冒包副本 | 0 | 无 | 是 |
| `candidate/normal-console` | `project-memory.exe`（venv） | 无 | 0 | 无 | 是 |

`candidate/shadow-pythonpath-bare` 是**已知残余风险**：裸 `-m` 在解释器解析模块名时假冒包已经胜出，产品代码尚未获得执行机会，任何包内检查都无法拦截。受支持的受信入口是 console script / `_project_memory_launcher.py` / `-I -P`；详见 `docs/decisions/ADR-0005-cli-bootstrap.md` §7.2。

### test-run 子进程

`test-run-env.json` 记录：宿主 `PYTHONPATH=...\hostile` 下运行 `test-run`，子进程环境 `PYTHONPATH` 指向不可变快照树、`PYTHONSAFEPATH=1`、`PYTHONNOUSERSITE=1`、`sys.path[0]` 为显式快照树、探针模块 `b5a_shadow_probe` 不可导入；收据 `isolation.python_env` 记录 `path_source=snapshot-only`、`safepath=true`、`nousersite=true`、`stripped` 六项。7 项断言全部为 true。

### 测试

- `b5a-pytest.log`：`7 passed`（`tests/test_security_b5a.py`）。
- `pytest.log`：`220 passed, 2 skipped`（既有 213 + 新增 7；2 skipped 为既有 Windows symlink 用例，未删除、未跳过任何既有用例）。

## 2. AC 映射

| AC | 本包证据 |
|---|---|
| AC-1 PYTHONPATH 假冒包不能劫持 CLI | `baseline/shadow-pythonpath`（劫持成立）→ `candidate/shadow-pythonpath-launcher`、`candidate/shadow-console` |
| AC-2 cwd 假冒包不能劫持 CLI | `baseline/shadow-cwd` → `candidate/shadow-cwd-launcher`、`candidate/shadow-console-cwd` |
| AC-3 console script 不被 PYTHONPATH 劫持 | `baseline/shadow-console`（泄漏）→ `candidate/shadow-console` |
| AC-4 正常调用仍可用 | `candidate/normal-bare`、`candidate/normal-console`、`candidate/isolated-runpy` |
| AC-5 test-run 子进程不被假冒包劫持 | `test-run-env.json` + `tests/test_security_b5a.py::LocalExecutionEnvTest` |
| AC-6 无法证明受信时 fail closed | `candidate/shadow-pythonpath-guard`（exit 3，无收据写入）；启动器无绝对解释器/启动失败时 exit 3 |
| AC-7 既有 213 项与新增测试全绿 | `pytest.log`（220 passed / 2 skipped）、`b5a-pytest.log` |
| AC-8 ADR/文档 | `docs/decisions/ADR-0005-cli-bootstrap.md`、`docs/OPERATIONS.zh-CN.md`（代码提交内） |
| AC-9 证据 | 本包 + `sha256sums.txt`（`verify_hashes.py` 可校验），7 类新增测试见 `tests/test_security_b5a.py` |
| AC-10 独立复核 | 不在本包；由 PM-03 另行执行 |

## 3. 目录结构

```text
run-20261028T154334Z/
├── README.md                     # 本文件
├── environment.txt               # 主机 / Python / fixture 哈希 / 使用的 checkout 与 venv
├── commands.jsonl                # 逐条命令、退出码、结果摘要
├── diffstat.txt                  # git diff --stat ddd9dba 85b1a4e
├── pytest.log                    # 全量测试
├── b5a-pytest.log                # 新增测试
├── shadow-pythonpath.json        # AC-1/AC-6 结构化结果
├── shadow-cwd.json               # AC-2 结构化结果
├── shadow-console.json           # AC-3 结构化结果
├── normal.json                   # AC-4 结构化结果
├── test-run-env.json             # AC-5 结构化结果（含收据 isolation.python_env）
├── baseline/*.{out,err,exit}     # 基线原始输出
├── candidate/*.{out,err,exit}    # 候选原始输出
├── matrix_wsl.sh                 # WSL 用例脚本（本轮实际执行）
├── matrix_console_windows.sh     # Windows console script 用例脚本
├── test_run_env_probe.py         # test-run 子进程环境探针
├── collect_evidence.py           # 从原始输出生成 *.json
├── make_sha256sums.py            # 生成 sha256sums.txt
├── verify_hashes.py              # 校验 sha256sums.txt
└── sha256sums.txt                # 清单（不含 sha256sums.txt 自身）
```

## 4. 校验方法

```bash
python verify_hashes.py     # 期望：OK: <n> entries verified (LF-normalized); 0 external fixture record(s) not present
```

包内文件按 LF 归一化后的字节计算哈希（CRLF 工作树与 LF 检出均可校验）；四个外部 fixture `.py` 按原始字节计算，仅在文件存在时校验。

## 5. 边界与未证明

- 未做安装级其它平台验证：console script 只在 Windows venv 验证（WSL 无 pip/ensurepip）。
- 裸 `-m` 且假冒包在模块解析阶段胜出的场景按设计无法拦截（ADR §7.2）；本包保留该基线行为作为披露，不视为通过。
- 不做受保护执行器隔离（B5B 范围）、不改 `authority`/签名/来源门禁。
- 未验证 PyPI/wheel 之外的发行形态（single-file zipapp、系统包管理器脚本等）。

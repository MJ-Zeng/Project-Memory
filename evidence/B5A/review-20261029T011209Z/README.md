# B5A 独立复核证据包 — run 20261029T011209Z

PM-03 独立会话复核候选 `9288818`（B5A.1）的证据。所有产物由本会话独立生成；不使用开发日志代替复现。

## 文件

| 文件 | 说明 |
|---|---|
| `environment.txt` | 平台/Python/各 SHA/任务卡哈希/共享夹具哈希 |
| `commands.jsonl` | 执行命令与退出码/结果摘要 |
| `fake-launcher.json` | 原生包装器 + 假冒 `_project_memory_launcher`（POSIX/Windows、共享+自建 marker 夹具） |
| `fake-package.json` | 原生包装器 + 假冒 `project_memory`（PYTHONPATH/cwd/混合，POSIX/Windows） |
| `normal.json` | 正常调用（两包装器 + 裸 `-m`） |
| `bare-m.json` | 裸 `python -m` 残余（记录，不计为通过）+ 守卫 exit 3 |
| `prev-candidate.json` | 上一候选 `85b1a4e` / 基线 `ddd9dba` 对照（证明夹具非特判） |
| `installed.json` | venv 安装布局模拟（POSIX/Windows 各 4 例） |
| `matrix.json` | 上述动态矩阵汇总 |
| `test-run-env.json` | `test-run` 子进程环境清理 + 收据 `isolation.python_env`（9/9 断言） |
| `pytest.log` | 候选全量：226 passed / 2 skipped |
| `pytest-base.log` | 基线全量：213 passed / 2 skipped（2 个既有 symlink skip） |
| `diffstat.txt` | 三组 diff 统计（含 code-only 文件清单） |
| `drive.py` / `probe_testrun.py` | 复现脚本 |
| `sha256sums.txt` | 证据文件与候选代码哈希 |

## 复现要点

- POSIX 包装器：`PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python.exe sh bin/project-memory --help`
- Windows 包装器：`cmd /c bin\project-memory.cmd --help`
- 恶意面：`PYTHONPATH=<fixtures>/b5a/{launcher-shadow,shadow}`；`cwd` 放 `cwd-shadow/project_memory/`
- 不含私钥/token/其他项目数据。

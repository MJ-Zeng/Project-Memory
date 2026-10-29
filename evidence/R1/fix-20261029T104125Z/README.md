# R1 文档订正证据（F1 / F2）

- 基线：`bb06037c469b6586b95fbcd69b6965585f2c977e`（`fix/release-gates`）
- 范围：只订正文档；不改代码、测试、schema、版本，不重写 `evidence/B5B/**` 历史文件
- 环境：Windows 10.0.26300；Git Bash；实际解释器 `C:\SoftWare\Anconda\python.exe`
  （本机 `python3`、`python` 均为 Microsoft Store 别名桩，exit 49）

## 1. F1 — B5B 清单逐文件复测

命令（脚本见同目录 `reproduce-b5b.sh`）：

```bash
bash evidence/R1/fix-20261029T104125Z/reproduce-b5b.sh > evidence/R1/fix-20261029T104125Z/b5b-recheck.log 2>&1
```

结果（`b5b-recheck.log`，exit 0）：

| 项 | 值 |
|---|---|
| 清单条目 | 42 |
| 工作树原始字节命中 | 29 |
| LF 归一化命中 | 17 |
| git blob 内容命中 | 19 |
| **至少一种表示命中** | **41/42** |
| 唯一不命中 | `run-20261029T015035Z/environment.txt` |

唯一不命中项的四种字节：

- 清单哈希：`d4f6d19fab1a3cd728c44f24724fc21e17139a2ca277fcf92e3aa2c4ce88f5c3`
- 工作树原始字节：`44c6eba74e51fd726c607588d50f1bff5a6f6883dc495ea354cacd74fbc90a52`
- LF 归一化：`a78b12ed17ebc4c613474c1102d44b794d04c554af837f3f88318e63710246c2`
- git blob 内容 SHA-256：`a78b12ed17ebc4c613474c1102d44b794d04c554af837f3f88318e63710246c2`
  （git 对象 id `e27a17fc7bee71aacf2888afa538772c222db463`，与 PM-03 报告一致）

行尾变体、BOM、尾随换行亦不命中；按 B5B README §3 的规则列为**需人工解释项**。该文件由 B5B 提交 `78b8394` 引入，R1 与本次订正均未改其字节（`git diff bb06037..HEAD` 不含该文件）。成因（清单生成后文件被改写或清单陈旧）属 B5B 历史，未回溯。

NUL 日志事实不变（`b5b-recheck.log`）：

- `receipts/trusted/run.log`：345 字节，42 个 NUL
- `receipts/trusted-host-attempt/run.log`：443 字节，42 个 NUL

## 2. F2 — Windows `python3` 说明

在 `README.md` 与 `docs/OPERATIONS.zh-CN.md` 的 `python3 -m pytest` 代码块之后各加一句：Windows 上 `python3` 可能是 Store 别名桩（exit 49），请用实际解释器执行。未新增命令段，未改原有命令。

## 3. 全量回归

```bash
PYTHONUTF8=1 /c/SoftWare/Anconda/python.exe -m pytest -q -p no:cacheprovider
```

`pytest-default.log`：**253 passed, 2 skipped**，exit 0（329.41s）。

## 4. 未验证 / 边界

- 不重算、不改写 B5B 清单与任何证据文件；`environment.txt` 的漂移成因未回溯。
- 未验证远端 tag/Release/PR 状态。
- 本目录只记录执行者的命令与输出，不代替 PM-03 下结论。

## 5. 字节约定

本目录及 `changed-docs.sha256` 的哈希均对 LF 字节计算（`pytest-default.log` 由 pytest 在 Windows 写出 CRLF，已统一为 LF 后再入 `sha256sums.txt`）。`evidence/R1/**` 有 `text eol=lf` 属性；三份文档的 LF 字节与提交 blob 一致，可用 `git cat-file blob HEAD:<path> | sha256sum` 复核。

```bash
cd evidence/R1/fix-20261029T104125Z && sha256sum -c sha256sums.txt
```

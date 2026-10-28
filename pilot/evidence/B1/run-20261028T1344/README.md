# B1 证据包 — run-20261028T1344

- 角色：PM-02 Developer（执行者，不判定）
- 任务卡：`pilot/rounds/B1/task.md`（SHA-256 `0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d`）
- Issue：https://github.com/MJ-Zeng/Project-Memory/issues/1 ｜ Goal：`G-B1` ｜ 轮次：1
- 基线：`25a919d63c7181fd4083e0fc1af33734d74c5515`（`dev/v1.0` 的后代，已由 seq 2/3 验证）
- 候选：`89ea4bd7fdbddaf90f640d4cc1b71d66fd1a63e3`（分支 `fix/b1-openssl-verifier`）
- 改动文件：`project_memory/authority.py`、`tests/test_authority_verifier.py`（新增）、
  `docs/decisions/ADR-0002-inprocess-signature-verifier.md`（新增）
- `authority.py` SHA-256：基线 `4805b06b45e208013013a872cce0e6b5f5e2c67794f8ea237eb1e07ff384a88d`
  → 候选 `163a08ad4585d3d488ca628c9c30554029767b5a45784fe6f7e2bcc6537518ea`

> 本包只记录**我观察到的命令与退出码**。PASS / FAIL / VERIFIED 由 PM-03 与人类判定。
> 未运行的项一律写在 `NOT VERIFIED`（见 Handoff），不以任何近似结果代替。

## 1. 命令台账

`commands.jsonl` 每行含 command / cwd / exit_code / 日志路径 / 日志 SHA-256 / env 说明；
日志正文在 `logs/<seq>-<label>.log`。

| seq | 命令（摘要） | 退出码 | 我观察到的结果 |
|---|---|---|---|
| 1 | `git status --short --branch` | 0 | 分支 `fix/b1-openssl-verifier`，仅本轮允许范围内的未跟踪文件 |
| 2 | `git rev-parse 25a919d…` | 0 | 基线可解析 |
| 3 | `git merge-base --is-ancestor 25a919d… origin/dev/v1.0` | 0 | 基线在 `dev/v1.0` 上 |
| 4 | 任务卡 SHA-256 | 0 | 与 Issue / `criteria.sha256` / 派发一致 |
| 5 | Windows `python --version` | 0 | Python 3.12.4 |
| 6 | `pytest --version` | 0 | pytest 9.1.1 |
| 7 | WSL `python3 --version` | 0 | Python 3.14.4（探针运行环境） |
| 8 | 基线 `pytest --collect-only -q` | 0 | 可收集 |
| 9 | 基线全量 `pytest -q` | 0 | 164 passed, 2 skipped |
| 10 | `git archive 25a919d` → 临时树 | 0 | 修复前探针的 CODE |
| 11 | 探针文件 SHA-256 校验 | 0 | 与 `pilot/kit/b1/README.md` 记录一致（`827ad0c2…`），探针未修改 |
| 12 | 修复前探针（第一次尝试） | 1 | 我的 WSL 输出解码包装崩溃，未产出探针结果；保留该条以可追溯 |
| 13 | 修复前探针（原始 kit 探针，CODE=基线树） | 0 | 见 §2 `probe-before.json` |
| 14 | 正向 fixture（CODE=基线树） | 0 | `goal_evidence_exit 0`，记录未被改动 |
| 15 | `pytest tests/test_authority_verifier.py`（修改后的工作树） | 0 | 26 passed |
| 16 | 全量 `pytest -q`（修改后的工作树） | 0 | 190 passed, 2 skipped |
| 17 | `git archive` 到未存在的目录 | 128 | 我的包装错误（目录未建），无副作用；由 seq 18 取代 |
| 18 | `git archive 89ea4bd` → 候选树 | 0 | 打印候选 `authority.py` SHA-256 |
| 19 | 修复后探针（同一未修改探针，CODE=候选树） | 0 | 见 §2 `probe-after.json` |
| 20 | 正向 fixture（CODE=候选树） | 0 | `goal_evidence_exit 0`，记录未被改动 |
| 21 | `pytest tests/test_authority_verifier.py`（候选提交） | 0 | 26 passed |
| 22 | 全量 `pytest -q`（候选提交） | 0 | 190 passed, 2 skipped；`pytest.log` 是该日志的逐字节副本 |

| 23 | `finalize.py`（第一次） | 0 | 排除规则有缺陷，把 654 个探针临时目录也哈希了；由 seq 24 取代 |
| 24 | `finalize.py`（修正排除后） | 0 | 生成 `pytest.log`/`positive.json`/`environment.txt`/`diffstat.txt`/`sha256sums.txt`（49 项） |
| 25 | `package.py` | 0 | 把证据文件的 CRLF 归一为 LF（37 个文件，只改行尾），重指 journal 的 `log_sha256`（24 条），重建清单 |
| 26 | `package.py`（第二遍） | 0 | 再处理 2 个 `probe-stderr.txt`（原字节是 `CR CR LF`） |
| 27 | `package.py` | 0 | README 修订后的重建清单（54 项） |
| 28 | 攻击链直测（CODE=候选树） | 0 | 见 §2.5：伪造签名的 `goal evidence` 退出码 1，`achieved` 退出码 1，Goal 停在 `evaluating` |
| 29 | 攻击链直测（CODE=基线树） | 0 | 同一条链在修复前：`goal evidence` 退出码 0（伪造签名被接受） |
| 30 | `finalize.py`（再跑一次） | 0 | §2.5 之后刷新 `environment.txt`/`diffstat.txt`/`positive.json`/`pytest.log` |
| 31 | `package.py` | 0 | 归一 §2.5 新增文件（7 个）并重建清单 |
| 32 | `package.py`（最后一次） | 0 | README §7 改写后的最终清单；此后不再改动证据文件 |

seq 15/16 与 21/22 之间的差别只是一处测试文件缩进（无逻辑改动）；15/16 保留在台账中。

### 行尾归一（seq 25/26）说明

`record.py` / `finalize.py` 当时用平台默认换行写文件，在 Windows 上产生 CRLF；仓库
`.gitattributes` 对 `pilot/**` 规定 `text eol=lf`，因此 CRLF 的磁盘字节与 git 存储的 blob
不一致，`sha256sum -c` 在别人检出候选后会失败。归一只改行尾、不改内容，且**没有回头修改任何
脚本**（`scripts/` 里保留的就是当时运行的版本）；每一条 journal 记录都把归一前的摘要保留在
`log_sha256_before_eol_normalization` 字段里，完整对照表在 `logs/25-package-eol-and-manifest.log`
与 `logs/26-package-eol-pass2.log`。

## 2. 探针：修复前 vs 修复后

`pilot/kit/b1/openssl_substitution.py` 未修改（seq 11 校验哈希）；两次都通过
`wsl.exe -u root -e python3 <probe> <CODE> <WORK> <OUT>` 运行，被 CLI 进程以 uid 1000 执行，
信任锚为 `/etc/pm-rc3-review/anchor-a.json`（root:root 644）。PM-02 未读取私钥、未签名。

| 探针结果键 | 修复前（`probe-before.json`） | 修复后（`probe-after.json`） |
|---|---|---|
| `control_rejected` | true（exit 1） | true（exit 1） |
| `path_substitution_accepted` | **true（exit 0）** | false（exit 1） |
| `path_evaluate_exit` / `path_achieved_exit` | **0 / 0** | 键不存在：PATH 替换那一步先被拒绝，后续步骤未运行 |
| `path_goal_status` | **"achieved"** | 键不存在（未到达该阶段） |
| `env_openssl_accepted` | **true（exit 0）** | false（exit 1） |
| `env_true_accepted` | **true（exit 0）** | false（exit 1） |
| `agent_owned_anchor_rejected` | true（exit 1） | true（exit 1） |

## 2.5 攻击链直测（`chain-before.json` / `chain-after.json`）

kit 探针只在 PATH 替换成功时才继续走 `evaluate → transition achieved`，所以修复后的
`probe-after.json` 里 `path_achieved_exit` / `path_goal_status` 这两个键**不存在**。
为了让 AC-7 不只是"键缺失"，`scripts/chain_probe.py` 以**只读 import** 复用 kit 模块里的
`build_case` / `bogus_record` / `cli`（kit 文件本身未修改，seq 11 已校验其哈希），
无论前一步成功与否都把整条链走到底，并记录每一步的退出码。

| 步骤 | 修复前（seq 29，CODE=基线树） | 修复后（seq 28，CODE=候选树） |
|---|---|---|
| `goal evidence`（伪造签名 + 假 openssl 前置 `PATH` + `PROJECT_MEMORY_OPENSSL`） | **0（被接受）** | 1，`没有可信授权来源（untrusted）：签名验证失败` |
| `goal evaluate` | 2，`satisfied=false` | 2，`satisfied=false` |
| `transition approved/active/evaluating` | 0 / 0 / 0 | 0 / 0 / 0 |
| `transition achieved` | 1，`insufficient_evidence` | 1，`insufficient_evidence` |
| 链结束时的 Goal | `status=evaluating`，`evidence=[]` | `status=evaluating`，`evidence=[]` |

必须说明的差异：`chain_probe.py` **没有**做 kit 探针在 evidence 被接受之后补的
`goal_criteria_sha256` 修复步骤。因此在基线树上这条链的 `achieved` 也返回 1，
这和 kit 探针自身在基线上的 `path_achieved_exit=0` / `path_goal_status="achieved"`
不同——**修复前的完整攻击链证据以 `probe-before.json`（seq 13）为准**，
本节只提供修复后"逐步退出码"的直接观测，不构成对基线行为的替代描述。

## 3. 正向 fixture（有效签名必须仍然可用）

`pilot/kit/b1/positive/`（人签名的 `VER-positive.json` + `template-repo.tar.gz`）未修改；
`positive_probe.py` 在副本上运行 `goal evidence`（该命令会追加证据，故不改 kit 本体）。

| 运行 | CODE | `goal_evidence_exit` | `goal_evidence_accepted` | `record_unchanged` | `anchor_matches_fixture_copy` | `hash_mismatches` |
|---|---|---|---|---|---|---|
| `positive-before.json`（seq 14） | 基线树 | 0 | true | true | true | [] |
| `positive-after.json`（seq 20） | 候选树 | 0 | true | true | true | [] |
| `positive.json` | — | 上述两次的索引 | | | | |

## 4. 新增测试覆盖（`tests/test_authority_verifier.py`，26 项）

- `VerifierIsNotEnvironmentSelectable`：植入打印 `Verified OK` 且 exit 0 的假 `openssl`/`openssl.bat`，
  同时前置 `PATH` 并设置 `PROJECT_MEMORY_OPENSSL`；伪造签名仍被拒、真签名仍被接受；
  并对 `authority` 模块做静态守卫（无 `shutil`/`subprocess`/`tempfile`/`_openssl`/`OPENSSL_ENV`，
  源码不含 `PROJECT_MEMORY_OPENSSL`/`powershell`/`Get-Acl`，`os.environ.get` 只出现一次且读锚点变量）。
- RSA 向量：有效签名接受；payload/签名字节篡改、截断、`s ≥ n`、他人公钥、1024 位模数、
  非法 base64、空签名、锚点缺公钥、公钥不可解析、算法与密钥类型不匹配、`ed25519` 全部拒绝。
- ECDSA 向量：P-256 有效签名接受；篡改 payload、非规范 `r`、`r = 0`、其它曲线、曲线外公钥点、
  退化 DER（含越过解析边界的字节）经生产入口 `_verify_signature` 一律拒绝且不抛异常。
- `AnchorIdentityTest`：当前主体拥有的锚点被拒绝（Windows 用 SID 比较，不查名字/PATH）。

## 5. 复现步骤（供 PM-03）

```bash
# Windows（仓库根）
C:/SoftWare/Anconda/python.exe -m pytest -q -p no:cacheprovider

# 修复前 / 修复后探针（需 WSL 与 root 锚点）
C:/SoftWare/Anconda/python.exe pilot/evidence/B1/run-20261028T1344/scripts/run_probe.py \
  --code <CODE_TREE> --work <WORK> --out probe-after.json --capture-dir <CAPTURE>

# 正向 fixture
C:/SoftWare/Anconda/python.exe pilot/evidence/B1/run-20261028T1344/scripts/run_positive.py \
  --code <CODE_TREE> --scratch <SCRATCH> --out positive-after.json --label positive-after
```

`scripts/` 内其余文件（保持当时运行的版本，未事后修改）：`record.py`（台账包装）、
`make_vectors.py`（生成测试向量）、`positive_probe.py`（WSL 内的 fixture 驱动）、
`finalize.py`（生成 `pytest.log`/`positive.json`/`environment.txt`/`diffstat.txt`/`sha256sums.txt`）、
`package.py`（seq 25/26 的行尾归一与最终清单）。

## 6. 目录内容

- 卡片要求：`README.md`、`environment.txt`、`commands.jsonl`、`probe-before.json`、
  `probe-after.json`、`positive.json`、`pytest.log`、`diffstat.txt`、`sha256sums.txt`
- 追加：`chain-before.json`、`chain-after.json`（§2.5 的逐步退出码）、
  `positive-before.json`、`positive-after.json`（`positive.json` 指向这两份原始输出）、
  `logs/`（每条命令的完整日志）、`scripts/`、`work/capture-before/`、`work/capture-after/`
  （WSL 原始 stdout/stderr/argv/退出码）
- **不纳入证据**：`work/before`、`work/after`、`work/chain-before`、`work/chain-after`、
  `work/positive-*-scratch` —— 探针自建的临时 git 仓库与临时锚点副本（含 root 公共锚点的副本），
  与结论无关且体积大；`sha256sums.txt` 也不覆盖它们。
- 不含私钥、token 或其它项目数据。

## 7. 校验

`sha256sums.txt` 覆盖本目录内除上面列出的临时目录、以及清单自身以外的全部文件
（每次打包 pass 会新增自己的日志，所以条目数只在清单里给出，正文不重复计数），
每行是 `<sha256>  <相对路径>`，全部 LF 行尾。在我这台机器上：

```bash
cd pilot/evidence/B1/run-20261028T1344 && sha256sum -c sha256sums.txt   # 我观察到逐行 OK，退出码 0
```

journal 里每条记录的 `log_sha256` 也各自对应 `logs/` 下的一个文件；
seq 12 与 seq 17 的退出码分别是 1 与 128（我的包装脚本错误），其余为 0。
清单是最后写入的文件，因此它不覆盖自己，也不覆盖"清单写好后才产生的自检输出"；
这类自检（例如 `git show` 对比 staged blob）的结果写在 Handoff 的观察记录里。

# B1 正向签名 fixture — 生成记录

- 生成对象：`B1` — AC-1（有效签名仍可用）
- 生成日期：2026-10-28
- 生成者：PM-01（人类在 2026-10-28 明确授权生成）
- 签名者：WSL Ubuntu `root` 调用 `openssl`，私钥 `/etc/pm-rc3-review/key-a.pem`
- 私钥处理：**未读取、未复制、未打印**；只把规范载荷交给 `openssl dgst -sign`，输出签名写入临时文件后删除
- 代码版本：`dev/v1.0` @ `a70ad1900b8ee8825766364976edb5345cba1000`（B0 合并后；后续 docs-only 提交不改变代码）

## 产物

| 文件 | 说明 |
|---|---|
| `template-repo.tar.gz` | 完整 fixture 仓库（含 `.git`，保留 root commit 与 remote 身份） |
| `anchor-a.json` | 与 `/etc/pm-rc3-review/anchor-a.json` 字节一致（仅公钥与元数据） |
| `pub-a.pem` | 与 `/etc/pm-rc3-review/pub-a.pem` 字节一致 |
| `VER-positive.json` | 已签名 Verification 记录（与仓库内副本一致） |
| `goal-evidence-result.json` | 在独立副本中以 uid 1000 运行 `goal evidence` 的成功输出（纯 UTF-8 JSON） |
| `sha256sums.txt` | 上述文件与记录/收据的 SHA-256 |

## 仓库身份

| 项 | 值 |
|---|---|
| remote | `https://github.com/pilot-org/b1-verifier` |
| 规范化 remote | `github.com/pilot-org/b1-verifier` |
| root commit | `3edabebbfb33bb0357be4e7509f9218b7192a8cb` |
| repo identity | `remote+root`，id `398f74eea875966179299bf201d02b910bac76582d8f2cbe1760494a714d7292` |

## Goal / Criterion

- Goal：`G-B1`，状态 `proposed`（fixture 不改变状态）
- Criterion：`C1` = `有效的真实签名仍可被验证`
- 判据摘要（签名载荷绑定）：`21edea396256934f0c0cfa7749b6fa41c3adcf52525239f2b8b3c9a9d9acce2f`
- 记录：`VER-positive`，`schema_version=1.2`，`status=VERIFIED`，`authority.status=trusted`
- 签名载荷 SHA-256：`47dc1463dfc08c219ad7a1c11b4116fbbdf45442888fee1679248481eab9476d`
- anchor：`anchor-rc3-a`；issuer：`RC3 Independent Test Signer <signer@test.invalid>`；algorithm：`rsa-sha256`

## 生成命令（摘要）

1. 建仓（Windows，Anaconda Python 3.12.4）：

```bash
git init; git config user.email b1-fixture@example.invalid; git config user.name "B1 Fixture"
# README.md + tests/check.py；提交 "base"；git remote add origin https://github.com/pilot-org/b1-verifier
python -m project_memory goal create --id G-B1 --title "B1 signed verifier" \
  --background "B1 AC-1" --outcome "valid signature accepted" --owner PM-01 \
  --criterion "有效的真实签名仍可被验证"
python -m project_memory test-run --command "<python> -c \"print('1 passed')\"" --commit <root> --agent pm01
python -m project_memory run start --goal G-B1 --task 4 --run-id run-target --agent dev-agent \
  --model-provider qodercn --model-id executor-model --base-sha <root> --role executor
python -m project_memory run finish --task 4 --run-id run-target --completed implemented \
  --remaining verify --head-sha <root> --test-command <cmd> --test-exit 0 --test-log <log>
python -m project_memory run start --goal G-B1 --task 4 --run-id run-verifier --agent verifier-agent \
  --model-provider qodercn --model-id verifier-model --base-sha <root> --role verifier
python -m project_memory verify --target-run run-target --verifier-run run-verifier \
  --standard acceptance --verdict pass --evidence-level locally_observed \
  --test-receipt <receipt> --criterion-evidence <mapping> --verification-id VER-positive
# 预期 exit 2（无签名者的本地 CLI 只能给出 MANUAL_REVIEW_REQUIRED）
```

2. 签名（WSL `root`，OpenSSL 3.5.5）：

```bash
openssl dgst -sha256 -sign /etc/pm-rc3-review/key-a.pem \
  -out signature.bin payload.bin
# payload = 记录去掉 authority 后的 canonical JSON（sort_keys, 紧凑分隔符, UTF-8）
```

3. 验证（WSL **uid 1000**，受保护 anchor）：

```bash
cp -a repo /tmp/repo-copy && cd /tmp/repo-copy
git config core.autocrlf true; git config core.fileMode false
PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json \
PYTHONPATH=<pm-pilot-01> python3 -m project_memory goal evidence \
  --repo . --id G-B1 --criterion C1 --kind verification --ref VER-positive
# exit 0；stderr 0 字节；记录 SHA-256 运行前后不变
```

## 使用方式（PM-02 / PM-03）

```bash
mkdir -p /tmp/b1-fixture && tar -xzf template-repo.tar.gz -C /tmp/b1-fixture
cp -a /tmp/b1-fixture/repo /tmp/b1-fixture/run-copy   # 不要直接在 repo/ 里跑，goal evidence 会改 Goal
cd /tmp/b1-fixture/run-copy
git config core.autocrlf true; git config core.fileMode false
PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json \
PYTHONPATH=<被测代码> python3 -m project_memory goal evidence \
  --repo . --id G-B1 --criterion C1 --kind verification --ref VER-positive
```

- 不得修改 `template-repo` 内的 Goal/Criterion/记录；不得重新签名。
- 该 fixture 只证明“key-a 对这条记录签名，且修复后仍被接受”，不证明人类批准或 Goal `achieved`。
- 记录中的 `target_repository` 记录的是生成时的绝对路径；跨路径可用性由 B0 的仓库身份逻辑处理，不要靠改路径“修复”。
- `goal evidence` 会追加 Goal 证据，因此必须在副本中运行；`template-repo` 本体保持干净。

## 残余说明

- 任务卡把该工件称作“schema 1.1 签名 fixture”；实际记录 `schema_version` 为 `1.2`（与 B0 fixture 相同），签名与验证语义不受影响。
- 期望输出保存为 `goal-evidence-result.json`（UTF-8，无 BOM），避免 B0 fixture 的 UTF-16/告警噪声问题（O-4）。

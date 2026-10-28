# ADR-0002：签名验签器进程内化（不再由 PATH / 环境变量选择验签器）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28
- 任务：B1（Issue #1）
- 基线：`25a919d63c7181fd4083e0fc1af33734d74c5515`（冻结参照 `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4`）
- 影响范围：`project_memory/authority.py`（签名验证路径、Windows 信任锚所有者检查）、`tests/test_authority_verifier.py`（新增）、本文档
- 不涉及：B2/B3/B4/B5 的判定语义、收据与快照格式、任务卡/判据/探针/评测器、`pilot/kit/`

## 1. 背景与问题

`verification_authority()` 判定一条 Verification 记录是否 `trusted` 的链路是：

```text
verification_authority → load_anchor（受保护公钥）
                       → _verify_signature(anchor, payload, signature_b64, algorithm)
                            → _openssl() = shutil.which(os.environ.get('PROJECT_MEMORY_OPENSSL') or 'openssl')
                            → subprocess.run([openssl, 'dgst', '-sha256', '-verify', ...])
                            → 返回 ok = (result.returncode == 0)
```

两个缺陷叠加：

1. **验签器身份由被验证的一方决定**：谁启动 CLI，谁就控制 `PATH` 和 `PROJECT_MEMORY_OPENSSL`；Agent 正是启动者。
2. **判定只信退出码**：不校验输出、不校验实现身份，`exit 0` 即等于“签名有效”。

RC3 在 `0d08a1a` 上的实测结果（`pilot/kit/b1/README.md`）：PATH 前置假 `openssl` → `path_substitution_exit=0`、`PROJECT_MEMORY_OPENSSL=/bin/true` → `env_true_accepted=true`，随后无需私钥即可把 Goal 推到 `path_goal_status=achieved`。

## 2. 信任根：修复前后

| 项 | 修复前 | 修复后 |
|---|---|---|
| 名义信任根 | root 持有的 anchor 文件中的公钥 | 同（不变） |
| **实际执行判定的对象** | `PATH`/环境变量解析出的任意可执行文件 | 本模块内的确定性密码学运算 |
| 判定依据 | 子进程退出码 | 公钥数学：签名整数与 payload 摘要的结构性等式 |
| 调用者可控输入 | `PATH`、`PROJECT_MEMORY_OPENSSL`、`USERNAME`/`USER`（Windows 所有者检查）、anchor 路径 | **仅** anchor 路径（`PROJECT_MEMORY_TRUST_ANCHOR`），由 `anchor_is_protected()` 约束不可写、非当前主体所有、非仓库内 |

要点：修复后不存在“验签器二进制”这个东西，因此不存在替换它的攻击面；也不存在“二进制缺失时的回退”，因为没有任何二进制。

## 3. 决策

### 3.1 进程内验签（仅标准库）

`_verify_signature()` 改为纯 Python 实现，删除验证路径上的 `subprocess`、`shutil.which`、`tempfile` 与 `OPENSSL_ENV`。`pyproject.toml` 的运行依赖保持 `[]`（不引入 `cryptography`）。

- **`rsa-sha256`** = RSASSA-PKCS1-v1_5 + SHA-256：
  - 公钥从 PEM 的 `SubjectPublicKeyInfo` 严格 DER 解析出 `(n, e)`；
  - 要求 `n ≥ 2048` 位、`e` 为奇数且 `≥ 3`；
  - 签名长度必须等于模长、整数必须 `< n`；
  - `m = s^e mod n` 必须精确匹配 `00 01 FF…FF 00 DigestInfo(SHA-256)`（填充至少 8 字节，`DigestInfo` 按完整 DER 前缀比对，不做“只比摘要”的宽松解析）；
  - 比较用逐字节累积异或，不提前返回。
- **`ecdsa-sha256`** = ECDSA over **P-256** + SHA-256：
  - 仅接受 `prime256v1` 的未压缩公钥点（`04‖X‖Y`，65 字节），其它曲线拒绝；
  - 签名 DER：`SEQUENCE{INTEGER r, INTEGER s}`，整数必须最小编码、非负；
  - 校验 `1 ≤ r,s < n`、`Q` 在曲线上、`u1·G + u2·Q` 非无穷远点且 `x1 mod n == r`；
  - `z` 取 SHA-256 摘要的完整 256 位整数。
- 任何解析/算术异常一律返回 `(False, 原因)`，即 **fail closed**；不重试、不换路径、不回退。
- 公共 API 与返回形态保持不变：`_verify_signature(anchor, payload, signature_b64, algorithm) -> tuple[bool, str]`（B0 的 `tests/test_repo_identity.py` 直接调用该函数，签名不变即可继续通过）。

### 3.2 同族弱点：Windows 信任锚所有者检查

`_windows_owner()` 原来通过 `subprocess` 调裸名 `powershell.exe`（靠 `PATH` 解析），并把 `USERNAME`/`USER` 环境变量当作“我是谁”的来源。这与 §1 的缺陷同族：判定信任根的环境输入仍由调用者控制。

改为直接调用系统 API：

```text
owner SID = advapi32.GetNamedSecurityInfoW(path, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION)
self SID  = advapi32.OpenProcessToken(当前进程, TOKEN_QUERY) + GetTokenInformation(TokenUser)
判定      = advapi32.EqualSid(owner, self)；相等 ⇒ 不是独立信任根
任何一步失败 ⇒ 无法确认所有者 ⇒ 拒绝该 anchor（fail closed）
```

不再有名字字符串大小写比较，不再有 `PATH` 查找，不再有环境变量身份来源。POSIX 分支保持原有 `st_uid`/`st_mode` 检查不变。

## 4. 被拒方案

1. **固定绝对路径 + SHA-256 + 所有者校验的 openssl**（AC-6 字面允许的方案）。拒因：
   - 摘要随发行版/补丁漂移，运维压力最终表现为“放宽 pin 或关掉校验”，防线被自己磨掉；
   - pin 的是外壳二进制，真正的密码学在 `libcrypto.so` / `libcrypto-*.dll` 里，`LD_PRELOAD`、`LD_LIBRARY_PATH`、Windows DLL 搜索顺序仍可劫持实际运算 ⇒ 攻击类别没有消除；
   - 判定仍是“子进程退出码”，只是候选集变小；`Verified OK` 类绕过仍取决于对二进制的完整信任；
   - 没有 openssl 的宿主（或 Windows 无安装）直接不可用，伤 AC-1 的可用性；
   - 轮换需要同时分发新 pin，形成第二个需要保护的秘密配置。
2. **除退出码外还要求 stdout 含 `Verified OK`**。任务卡 §5.3 明确判 FAIL（AC-5 就是打这个）。
3. **引入 `cryptography`（pyca）**。运行依赖从 0 变成 1，且原始探针在 WSL 里用系统 `python3`（uid 1000，未安装第三方包）执行被测代码 ⇒ 该环境会因导入失败而拒绝一切签名，AC-1 在 PM-03 的复现路径上直接失败。
4. **只在测试里净化 `PATH`/环境变量**，生产代码仍读环境变量。任务卡 §5.5 判 FAIL。
5. **让所有签名都失败**（例如把验签整体短路）。任务卡 §5.1 判 FAIL；AC-1 的正向 fixture 与原始探针的 control 项会同时暴露它。
6. **对探针路径 `/tmp/pm-rc3-fakebin` 或文件名做特判**。任务卡 §5.4 判 FAIL，本方案完全不出现任何路径/文件名常量判定。

## 5. 失败关闭矩阵

| 场景 | 结果 |
|---|---|
| 未配置 `PROJECT_MEMORY_TRUST_ANCHOR` | `unconfigured`，拒绝 |
| anchor 在仓库内 / 可写 / 属于当前主体 / POSIX 组或其他可写 | 拒绝（`anchor_is_protected`） |
| Windows 取不到 owner SID 或令牌 SID | 拒绝（无法确认所有者） |
| `authority.anchor_id`/`issuer`/`algorithm` 与 anchor 不符 | 拒绝 |
| `signed_payload_sha256` 与记录内容不符 | 拒绝 |
| `signature_b64` 缺失、非法 base64、长度不符、`≥ n` | 拒绝 |
| 公钥 PEM 非 SPKI、非 RSA/P-256、RSA 模数 < 2048 位、`e` 非法 | 拒绝 |
| 签名 DER 非规范（长度/前导零/负数/多余字节）、`r` 或 `s` 越界、`Q` 不在曲线 | 拒绝 |
| 篡改 payload / 换公钥 / 截断签名 / 翻转签名任意位 | 拒绝 |
| `PROJECT_MEMORY_OPENSSL`、`PATH` 上放假验签器（含打印 `Verified OK` 的） | **与本模块无关**：验证路径不查询环境，也不执行子进程 ⇒ 拒绝 |

## 6. 残余风险

1. **自研密码学实现的正确性**（最主要的新增风险）。缓解：只用公开运算、不含密钥材料；严格 DER 与边界检查；与本机 OpenSSL 3.5.9 交叉验证（同 payload 的真实签名必须接受、篡改 1 字节必须拒绝，RSA 2048 与 ECDSA P-256 各一组，见证据包）；人类预签的 `pilot/kit/b1/positive/VER-positive.json` 必须继续验证通过。请 PM-03 独立复核模长/填充/`DigestInfo` 与 ECDSA 边界条件。
2. **解释器与模块来源仍可被环境控制**：`PYTHONPATH`/`sys.path` 上更早出现的同名 `project_memory` 会顶替本模块，`python3` 本身也可替换。这不属于 B1 的判定（B1 要求的是“验签器不被环境替换”），由 B5/沙箱与 PM-03 的独立复核（从基线工作树取探针、从候选 SHA 取代码）承担。
3. **`LD_PRELOAD` / DLL 侧加载**：对验签路径不再适用（无子进程）；对本项目其它子进程（`git`、`powershell` 已移除）仍需部署层保护。
4. **root 妥协**：能以 root 写 `/etc/pm-rc3-review/` 的主体可以替换公钥，从而伪造信任根。`anchor_is_protected` 只从当前进程视角检测可写性/所有权，不防 root，也不声称防 root。
5. **无吊销机制**：私钥泄露后，旧 anchor 会继续接受其签名，直到按 §7 轮换 anchor。
6. **时间侧信道**：RSA 比较走常量时间累积；ECDSA 未做常量时间。验证只使用公钥，不涉及本项目秘密，判定为可接受。
7. **算法收敛**：仅 `rsa-sha256`、`ecdsa-sha256`(P-256)。Ed25519、RSASSA-PSS、其它曲线一律 fail closed；如需支持，另开轮次。
8. **性能**：纯 Python ECDSA 约毫秒级，本工具每次验证只调用一次，不构成风险。

## 7. 如何校验与轮换“固定验签器”

修复后，“固定验签器”不是一个二进制，而是 `project_memory/authority.py` 里的这段实现，因此：

- **校验身份**：记录该文件在候选 SHA 上的 blob SHA-256 与 commit SHA；PM-03 从候选 SHA 读代码、从**基线工作树**读探针（`pilot/kit/b1/README.md` 要求）。任何改动都会在 `git diff --stat` 与文件哈希上显形。
- **校验正确性**：证据包内保存与 OpenSSL 的交叉验证结果（接受真签名 / 拒绝篡改 / 拒绝他人公钥），以及正向 fixture 的 `goal evidence` 退出码。
- **轮换签名者（人类操作）**：由 root 在 `/etc/pm-rc3-review/` 写入新 anchor（新 `anchor_id`/`issuer`/公钥）→ 旧记录因 `authority.anchor_id` 不匹配自动变 `untrusted`（预期行为：历史证据只做人工复核，不追溯改写）→ 之后由新私钥重新签发。Agent 不写该目录、不生成密钥、不签名。
- **轮换验签实现**：正常 PR + PM-03 复现；判据与探针不变。若将来必须重新引入外部二进制，必须先在本 ADR 追加“为什么进程内实现不再够用”，并同时给出 `libcrypto` 层的完整性方案（§4.1 的失败原因不得被绕过）。

## 8. 与验收标准的对应

| AC | 实现/判定点 | 证据 |
|---|---|---|
| AC-1 | 未改动 anchor/载荷语义，RSA 验证接受真实签名 | `positive.json`（`goal evidence` exit 0）、交叉验证日志 |
| AC-2/3/4 | 验证路径不再查询 `PATH`/`PROJECT_MEMORY_OPENSSL` | 原始探针 `probe-after.json` |
| AC-5 | 判定来自公钥数学，不看任何输出字符串 | 新增负向测试（植入会打印 `Verified OK` 且 exit 0 的假 `openssl`/`openssl.bat`，前置 `PATH` 并设 `PROJECT_MEMORY_OPENSSL`）+ `probe-after.json`；任务卡要求由 PM-03 自建变体，本行只是同型自测 |
| AC-6 | 无环境选择、无回退、解析失败一律拒绝 | `authority.py` diff、新增单测 |
| AC-7 | `trusted` 无法被伪造 ⇒ 链路停在 `goal evidence` | `probe-after.json`；原始探针只在替换成功时才继续走状态链，所以修复后它的 `path_achieved_exit`/`path_goal_status` 两键不存在。逐步退出码的直接观测在 `chain-after.json`（`goal evidence` exit 1 → `transition achieved` exit 1，Goal 停在 `evaluating`；见证据包 README §2.5） |
| AC-8 | 不删/不跳既有测试 | `pytest.log` |
| AC-9 | 信封/摘要/anchor 检查全部保留 | 既有 RC3 测试 + 新增负向测试 |
| AC-10 | 本文档 | 本文件 |
| AC-11 | 仅动 `authority.py` + 新增测试 + 文档 + 证据 | `diffstat.txt` |

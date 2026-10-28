# B1 正向签名 fixture（待人类生成）

## 目的

证明修复后“有效签名仍可正常验证”（AC-1），防止用“让所有签名都失败”的方式通过 B1。

## 需要生成的内容

```
positive/
  template-repo/            # 最小仓库：Goal + Criterion + Verification 记录
  anchor-a.json             # 与 /etc/pm-rc3-review/anchor-a.json 一致
  pub-a.pem                 # 对应公钥
  VER-positive.json         # 用 key-a.pem 正确签名的记录
  GENERATION.md             # 生成命令、时间、执行者、SHA-256
  sha256sums.txt
```

## 生成规则

- 由**人类**在仓库外以 root 运行生成脚本；私钥不进入仓库、不进入提示词、不进入日志。
- `template-repo` 的 Goal/Criterion 必须与签名载荷绑定；使用者不得修改判据。
- 记录必须通过 `project_memory.authority` 的签名校验，且 `authority.status = trusted`。
- 生成后计算所有文件的 SHA-256，写入 `sha256sums.txt`。

## 当前状态

**未生成。** 这是 B1 派发前的阻塞项（W11）。PM-02/PM-03 不得自行签名或伪造 fixture。

## 使用方式

- PM-02：把 `template-repo` 复制到临时目录，运行 `goal evidence --ref VER-positive`，期望 exit 0；把结果写入证据包。
- PM-03：从 `.pilot/base/pilot/kit/b1/positive/` 读取，独立重跑；不得修改 Goal/Criterion。

## 安全

- 不在本目录放 `key-a.pem` / `key-b.pem`。
- 不在 `GENERATION.md` 里写私钥内容或口令。
- 如果私钥泄露或 anchor 被替换，停止本轮并通知人类。

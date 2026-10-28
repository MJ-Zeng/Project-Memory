# B2 验证工具包

B2 的 fixture 与 B1 不同：B1 只需要“有效签名”，B2 需要区分**内容完整性**与**执行真实性**。

## 需要的 fixture

| 名称 | 内容 | 期望 |
|---|---|---|
| `VER-b2-forged-untrusted` | 手写收据，`valid=true`、`provenance.trusted=false`，有效签名 | 拒绝 |
| `VER-b2-forged-claimed-trusted` | 手写收据，谎报 `trusted=true`，无 attestation，有效签名 | 拒绝 |
| `VER-b2-genuine-trusted` | 带可验证 attestation 的真实/测试执行，有效签名 | 接受 |
| `VER-b2-local-untrusted` | 本地未受信收据，有效签名 | 默认拒绝，或仅显式人类例外 |

## 目录（待生成）

```
pilot/kit/b2/
  receipts/           # 收据、快照、日志
  attestations/       # 可验证 attestation（如设计使用）
  verifications/      # 已签名 Verification 记录
  exceptions/         # 显式人类例外（如设计使用）
  README.md
  sha256sums.txt
```

- 由 PM-01/人类用 anchor-a 签名；私钥不入库。
- 正向 fixture 无法生成时标 `NOT VERIFIED`；不得用伪造 `trusted=true` 冒充当正。
- 当前状态：**待生成**。PM-02 可先用测试夹具/测试 attestation 开发；PM-03 用 PM-01 提供的独立 fixture 复核。

## 安全

- 不读 `/etc/pm-rc3-review/key-a.pem`。
- 不把“手写 trusted=true”当正向。
- 不改 fixture 让它通过；失败要记录为产品/测试问题。

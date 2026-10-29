## PM-03 独立复核 — R1 发布门槛：**PASS**（程序性复核，非安全认证、非 v1.0 GO）

> 由 PM-03 独立会话产出；本会话无 GitHub 凭据，请 PM-01 代为转发。合并/发布由人类决定。

- 基线：`85bf6a05542aa6bca3ab0d9ef51c6216f76b6080`
- 候选：`bb06037c469b6586b95fbcd69b6965585f2c977e`
- 任务卡 SHA-256：`5949420f784feeb1484c8b8465cec40e7646931d5ff6c0a6af865113f13131f1`（未改）
- 复核分支：`review/r1-bb06037`；证据：`evidence/R1/review-20261029T102343Z/`（清单自校验 26/26 OK）

### 结论要点

| 项 | 结果 |
|---|---|
| #19 空必达（唯一 required 改 false / 删除全部 required） | evaluate exit 0 且 `satisfied=false`、`insufficient_evidence`、`no_required_criteria=true`；show 可读且 `status_problems` 含该标记、`effective_status≠achieved`；transition→achieved exit 1、状态不变、无 checkpoint request、审计 `rejected`。**四路一致 fail closed** |
| 对照（普通未满足） | evaluate 仍 exit 2（exit-0 未掩蔽其它未满足） |
| goal create 无必达 | 仍拒绝（exit 1） |
| openssl 缺省 / 开关开启 / 存在 | 37 skipped / 37 errors（消息含 openssl 与开关名）/ 37 passed×2；仅测试层、无运行时依赖、无默认注入 |
| 契约 | schema 实数 21 与文档一致；audit/checkpoint 字段与代码一致；样例 0 problem；自造真实条目 valid |
| 历史证据 | R1 清单 36/36 OK；`git hash-object` vs `HEAD:` 37/0；B5B 仅新增 README、B4 零改动 |
| 回归 | 默认 253 passed/2 skipped；开关 253/2；定向 57 passed；2 skip 均为 rc3 符号链接 |

### 发现

- **F1（Medium，建议合并前顺手订正，不阻断）**：`evidence/B5B/README.md` 写“42/42 至少命中一种表示”，实测 **41/42**——`run-20261029T015035Z/environment.txt` 在工作树原始字节 / LF 归一化 / git blob 三种表示下**全部不匹配**其清单哈希（行尾变体、BOM、尾随换行、CR-only 亦不命中）。该文件由 B5B 提交 `78b8394` 引入，**R1 未改动**（对基线 diff 为空），属 B5B 既有字节漂移。README 其余计数（29/17/19）与 NUL 日志（345B/42、443B/42）完全吻合。建议：把计数改为 41/42 并将该文件列为需人工解释项；**不要重写历史证据/清单**。
- **F2（Low）**：文档命令使用 `python3`，本机为 Microsoft Store 别名桩（exit 49）；已用真实解释器等价执行通过。建议补一句 Windows 用实际解释器。
- **F3（Info）**：空必达 exit 0 为 AC-1 明确取舍；并存 open high 缺陷时结构化输出仍保留 `open_high_defects`，仅看退出码的调用方需注意。

### 未验证（NOT VERIFIED）

远端 tag/Release 与 PR 实时状态（无凭据）；POSIX 实装/CI；生产 anchor-a 端到端签名；`fixtures/b5b` 的 `--trusted` 真实执行（按要求仅静态核对）；B5B `environment.txt` 漂移成因（属 B5B 历史）。

细节见 `review/R1/REVIEW-R1.md` 与 `evidence/R1/review-20261029T102343Z/`。

# Pangram 单检测器映射

## 产品边界

Paperlight 当前只有两个检测模式：确定性 `mock` 和真实 `pangram`。不再运行多供应商融合、共识下限或分歧判断。检测结果是概率性的“AI 写作风险检测”和“内部风险信号”，不是作者身份或学术不端判决，也不是论文查重。

## 官方契约

截至 2026-07-19，Pangram 官方文档把当前单文本接口定义为异步任务：

- `POST https://text.external-api.pangram.com/task`
- `GET https://text.external-api.pangram.com/task/{task_id}`
- 请求头 `x-api-key`
- 成功结果包含 `version`、`prediction_short`、三个 `fraction_*` 和带字符索引的 `windows`

官方已把同步 `POST https://text.api.pangram.com/v3` 列入 deprecated endpoints。实现以[当前 AI Detection 文档](https://docs.pangram.com/api-reference/ai-detection)和[废弃端点清单](https://docs.pangram.com/api-reference/deprecated-endpoints)为准。

## 内部映射

| Pangram 字段 | Paperlight 字段 | 规则 |
|---|---|---|
| `version` | `providerModelVersion` | 必须符合有限长度的版本格式 |
| `prediction_short` | `prediction` | 只接受官方类别 AI、AI-Assisted、Human、Mixed |
| `fraction_ai` | `aiGeneratedPercent` | 0–1 且有限，乘 100 |
| `fraction_ai_assisted` | `aiAssistedPercent` | 0–1 且有限，乘 100 |
| `fraction_human` | `humanPercent` | 0–1 且有限，乘 100 |
| 前两项之和 | `combinedRiskPercent` | 透明相加，不称为“精准 AI 率” |
| window AI-Generated | `classification=ai_generated` | 深蓝高亮 |
| window AI-Assisted | `classification=ai_assisted` | 浅蓝高亮 |
| window Human | 不保存高亮 | 仍计入人工写作比例 |

每个非人工 window 的全局字符范围必须逐字匹配提交文本，再精确拆到稳定段落 ID 和段内 `start/end`。越界、重叠、文本不一致、未知分类、未知置信度或无法映射都会让整次检测失败关闭，不保存近似范围。

## 错误与费用保护

- 401/403：鉴权或权限失败；402：余额不足；429：限流；5xx：服务暂时不可用。前端只收到稳定的清洗错误，不收到供应商原始正文。
- 创建任务的 POST 没有官方幂等机制，所以只发送一次；结果未知的超时不会自动再次计费提交。
- 已获得 task ID 后，轮询 GET 可使用有限退避重试。
- Key 只存在于 Railway 后端变量。日志、数据库正文、前端静态产物、测试快照和文档都不得包含 Key。
- 真实模式需要 Key 与 `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` 两道门；在数据条款和费用确认前保持 Mock。

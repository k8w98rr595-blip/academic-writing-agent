# Pangram 4 单检测器映射

## 产品边界

Paperlight 只有确定性 `mock` 和真实 `pangram` 两种检测模式。结果是概率性的“AI 写作风险检测”和“内部风险信号”，不是作者身份或学术不端判决，也不是论文查重。生产默认保持 Mock；未经数据条款、费用和单次真实验收三道人工批准，不上传文稿到 Pangram。

## 2026-08-08 官方契约

Pangram 当前单文本 API 是异步任务：

1. `GET https://text.external-api.pangram.com/models` 获取当前 API Key 实际可用、按顺序返回的模型选择器。
2. `POST https://text.external-api.pangram.com/task`，请求头为 `x-api-key`，请求体显式发送 `text`、`model: "pangram-4"` 和 `public_dashboard_link: false`。
3. 仅轮询同一个 `GET https://text.external-api.pangram.com/task/{task_id}`，直到 `STAGE_SUCCESS` 或 `STAGE_FAILED`。

同步 `POST https://text.api.pangram.com/v3` 已被官方列入 deprecated endpoints。`pangram-4` 是从 `GET /models` 返回、且需要账号 entitlement 的选择器；Paperlight 不把 `default` 猜成 Pangram 4。参考：[API Overview](https://docs.pangram.com/api-reference/introduction)、[Models](https://docs.pangram.com/api-reference/models)、[AI Detection](https://docs.pangram.com/api-reference/ai-detection)、[Deprecated Endpoints](https://docs.pangram.com/api-reference/deprecated-endpoints)。

Pangram 3 与 Pangram 4 的可验证区别：Pangram 4 使用选择器 `pangram-4`，成功响应示例版本为 `4.0`，窗口类别严格为 `AI-Generated`、`AI-Assisted`、`Human Written`，并为每个窗口返回 `is_humanized` 与 `humanizer_score`。Pangram 3 当前价格单位较大，且旧同步 V3 接口已废弃。Paperlight 只接受可用模型目录中的 `pangram-4`，并要求实际响应版本以 `4.` 开头。

## 内部映射

| Pangram 字段 | Paperlight 字段 | 规则 |
|---|---|---|
| 请求 `model` | `providerModel` | 固定为已从 `/models` 发现的 `pangram-4` |
| 响应 `version` | `providerModelVersion` | 安全字符串且必须以 `4.` 开头 |
| `task_id` | `taskReference` / `requestId` | 只保存 SHA-256 引用，不保存原始任务 ID |
| `prediction_short` | `prediction` | Pangram 4 只接受 `AI`、`Human`、`Mixed` |
| `fraction_ai` | `aiGeneratedPercent` | 0–1 有限数，乘 100 |
| `fraction_ai_assisted` | `aiAssistedPercent` | 0–1 有限数，乘 100 |
| `fraction_human` | `humanPercent` | 0–1 有限数，乘 100 |
| 前两项之和 | `combinedRiskPercent` | 透明相加，不称为“精准 AI 率” |
| `AI-Generated` window | `classification=ai_generated` | 深蓝高亮 |
| `AI-Assisted` window | `classification=ai_assisted` | 浅蓝高亮 |
| `Human Written` window | 不保存高亮 | 仍计入人工写作比例 |

Pangram 4 可能规范化返回文本，官方说明窗口偏移指向返回的顶层 `text`。Paperlight 不猜测规范化映射：只有返回文本与提交文本逐字相同时才映射到稳定段落 ID；否则整次结果以 `range_mismatch` 失败关闭，不保存百分比或高亮。

## 错误、费用和滥用保护

- `/models` 在付费任务前验证 entitlement；目录缺失、无效或不含 `pangram-4` 时不发送检测 POST。
- 401/403、402、429、422、5xx 和超时会转换为脱敏错误；供应商正文不进入前端或日志。
- 创建任务的 POST 没有官方幂等头，只发送一次。结果未知的超时不自动重交；已经获得 task ID 后只轮询该任务。
- 按正文和模型生成内容哈希；相同内容 24 小时内拒绝重复提交。只保存二次哈希后的幂等元数据。
- 默认 Pangram 上限为每小时提醒 1 次、硬限制 2 次、每日 4 次、并发 1 次；连续 5 次失败后熔断 15 分钟。
- Key 只能位于 Railway `api` 服务变量。真实模式同时要求 `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` 和 `PANGRAM_PAID_CALLS_ENABLED=1`；任一门槛缺失均在启动时失败，不会静默回落或伪装成真实结果。

## 尚待供应商/账号确认

- 单文本 `/task` 的正式最小和最大输入长度，官方 API 参考页未公布数值硬限制；Paperlight 继续使用自己的 800–5,000 英文词限制。
- 单文本任务及结果的精确保留期限未在 API 参考页说明；48 小时只明确适用于 Bulk 元数据与结果。
- 官方隐私政策说注册账号提交会被收集、不用于模型训练，并可从历史删除；“零数据保留”只作为 Enterprise 可洽谈选项出现，不视为当前账号默认能力。
- 轮询 GET 是否明确为零费用未在公开计费条款逐项说明。实现不会把轮询当作新任务，但首次付费验收前仍需在账号或供应商书面确认。

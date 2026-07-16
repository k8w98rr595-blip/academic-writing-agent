# Pangram 与 Copyleaks 检测 Provider

本文记录 2026-07-16 按两家官方文档核对后的实现边界。AI 检测是概率性写作风险信号，不是作者身份或学术不端判决；本功能不包含相似度语料库，因此不能称为“查重”。

## 官方接口事实

| 项目 | Pangram | Copyleaks |
|---|---|---|
| 认证 | 每次请求使用 `x-api-key` | 用邮箱和 API Key 调用登录端点，换取 48 小时 Bearer Token；进程内缓存并提前 5 分钟刷新 |
| 当前文本端点 | `POST https://text.external-api.pangram.com/task`，随后轮询 `GET /task/{task_id}` | `POST https://api.copyleaks.com/v2/writer-detector/{scanId}/check` |
| 处理方式 | 异步任务；终态为 `STAGE_SUCCESS` 或 `STAGE_FAILED`；官方当前文本接口没有回调字段 | 原始文本端点同步返回；文件/URL 的 Authenticity API 是另一套异步 webhook 流程，本项目未使用 |
| 输入限制 | 当前 `/task` 参考页未公布单文本硬上限；计费按每开始的 1,000 词计一单位。Paperlight 仍限制 800–5,000 英文词 | 255–100,000 字符；`scanId` 为 3–36 个允许字符。Paperlight 的 800–5,000 词产品限制通常更严格，但仍在调用前检查字符上限 |
| 局部结果 | `windows[]` 返回文本、标签、AI assistance score、置信等级和全局字符起止位置；它是 segment/window，不保证天然等同语法句 | `results[]` 返回 Human/AI 分类，`matches.text.chars` 返回全局字符起点和长度；section `probability` 已被官方标记为弃用 |
| 限流 | 开发者实时 API 当前公开为 5 QPS；超限返回 429 | 默认 10 请求/秒；登录端点 12 次/15 分钟；超限返回 429 |
| 典型错误 | 400、401、402 余额不足、403、404、413、422、429、500 | 400、401、402/余额错误、429、500/503；官方结构化错误还区分无余额、暂时不可用和超时 |
| 数据保留 | 单任务保留时长未在当前 `/task` 参考中明确；官网只明确企业方案可签零保留，批任务终态后保留 48 小时 | `/v2/writer-detector` 的明确保留/删除保证未在公开文本端点文档中找到；Authenticity `/v3/submit` 默认为最多 2,880 小时，但不是本项目使用的端点。公开资料未确认文本 API 的零保留承诺 |
| 计费 | 开发者实时接口公开价为 USD 0.05/1,000 词，批量为 USD 0.04/1,000 词；以账户结算页为准 | 官方以 250 词为一 credit，但 API/教育定价可能为合同价；以账户套餐和 API Dashboard 为准 |

官方来源：

- Pangram [API Overview](https://docs.pangram.com/api-reference/introduction)、[AI Detection](https://docs.pangram.com/api-reference/ai-detection)、[API pricing](https://www.pangram.com/solutions/api)
- Copyleaks [Authentication](https://docs.copyleaks.com/using-the-apis/authentication)、[AI Text Detector](https://docs.copyleaks.com/reference/actions/writer-detector/check/)、[AI result schema](https://docs.copyleaks.com/reference/data-types/authenticity/results/ai-detection)、[Rate Limits](https://docs.copyleaks.com/using-the-apis/rate-limits)、[Errors](https://docs.copyleaks.com/using-the-apis/api-errors)

## 统一 Provider 结果

每家 Provider 无论成功或失败都输出同一结构，失败字段为 `null` 或空数组，不伪造数值：

```json
{
  "overallScore": 63.0,
  "sentenceSpans": [{ "paragraphId": "p_...", "start": 0, "end": 87, "score": 0.76, "confidence": 0.8 }],
  "confidence": 0.8,
  "provider": "Pangram",
  "providerModelVersion": "3.3",
  "requestId": "provider-request-id",
  "warnings": [],
  "isMock": false,
  "latencyMs": 812,
  "status": "success",
  "error": null
}
```

映射规则：

1. Pangram 的 `overallScore` 为 `fraction_ai + fraction_ai_assisted`，上限为 100%。返回中会明确提示包含 AI-assisted 内容。
2. Pangram 仅将非 Human 的 window 作为局部证据；字符范围必须与本次提交文本逐字一致，否则整家 Provider 以 `range_mismatch` 失败关闭。
3. Copyleaks 的 `overallScore` 使用 `summary.ai`；局部证据只采用 `classification=2`。由于 section `probability` 已进入弃用期，缺失时使用 `summary.ai` 作为 span 强度，不依赖该字段存在。
4. 两家原始全局字符范围先严格检查边界，再按 `\n\n` 段落分隔映射回稳定段落 ID，最后投影到 Paperlight 自己的句子边界。任何数组错位、越界或非数字值都会失败关闭。
5. `providerModelVersion`、Provider 请求 ID 和端到端调用耗时随分析结果保存；正文、响应全文、Token 和 Key 不进入日志或审计详情。

## 双检测融合规则

分数不做简单平均，也不假装经过跨供应商概率校准。

1. 先把每家原始分数分为 `low < 20`、`elevated 20–<50`、`high >= 50` 三个风险区间。
2. 两家都成功且处于同一区间时，融合分数取两者较低值，作为“共识下限”；原始分数始终分别保留。
3. 两家成功但风险区间不同：`fusionStatus=disagreement`，`overallScore=null`，前端显示“检测结果不一致”。
4. 任一家失败：`fusionStatus=partial`，`overallScore=null`；另一家的句子仍可作为浅蓝单家证据，但绝不升级为深蓝或“双重确认”。
5. 句子证据的区间交集被拆成原子范围。两家同时覆盖的范围为 `consensus`（深蓝），仅一家覆盖为 `single`（浅蓝）；共识强度取两家局部强度的较低值。
6. 文稿生成新版本后，分析记录的 `versionId` 不再等于当前版本，现有 `isStale` 机制立即将全部旧高亮标为过期。

## 错误与重试

- 鉴权失败、余额不足、参数无效和字符错位不重试。
- 429、连接错误、超时和 5xx 最多尝试两次，指数退避并尊重短 `Retry-After`；若服务要求等待超过 5 秒，本次请求直接返回受控失败，避免阻塞工作线程和重试风暴。
- Pangram 创建任务没有官方幂等头，因此提交只发送一次；其状态轮询可以有限重试。Paperlight 的分析 ID 作为内部幂等上下文保存。
- Copyleaks 用分析 ID 派生稳定且合规的 `scanId`，同一逻辑任务的有限重试复用该 ID。401 仅允许刷新一次缓存 Token。
- 双 Provider 并行执行；失败对象仅返回安全错误码和可读原因，不透传供应商响应正文。

## 隐私与费用风险

真实模式默认存在两道关闭门：`DETECTOR_MODE=mock` 和 `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0`。只有完成合同/数据条款确认后才能同时改变。

上线前必须书面确认：

- 是否允许发送未发表学生论文、处理地区、分包商、训练用途、保留期限、删除 SLA、事件通知与 DPA；
- Pangram 账户是否实际包含零保留，而不只是官网列出的企业可选能力；
- Copyleaks `/v2/writer-detector` 的文本保留和删除政策。不能把 `/v3/submit` 的 120 天说明误套到同步文本端点，也不能推断其为零保留；
- 账户单价、最低购买额、credit 有效期、自动充值开关、退款和限额。

建议单人阶段关闭两家的自动充值，并在应用外建立：日调用数/词数、周信用点消耗、月预算 50%/80%/100% 告警，以及 429、5xx、重复分析 ID、单任务重试次数异常告警。Pangram 公开单价可按提交词数预估；Copyleaks 必须使用账户 credit balance/usage API 或 Dashboard 的实际合同计价。

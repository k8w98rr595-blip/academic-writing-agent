# Provider setup

The application defaults to `DETECTOR_MODE=mock` and `REWRITE_MODE=mock`.

## DeepSeek V4

Paperlight uses `deepseek-v4-pro` to prepare a reviewable patch and then asks
`deepseek-v4-flash` for a separate semantic-safety decision. A deterministic
server check still rejects changes to citations, numbers, quotations, URLs, and
abbreviations. The model never writes directly into the document.

```dotenv
REWRITE_MODE=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<configure-in-secret-manager>
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_VALIDATOR_MODEL=deepseek-v4-flash
```

Configuration rules:

1. Create a key at <https://platform.deepseek.com/api_keys>.
2. Store `DEEPSEEK_API_KEY` only in the backend secret manager. Do not put it in
   GitHub Pages variables, `NEXT_PUBLIC_*`, source control, screenshots, or chat.
3. On Railway, add the key to the `api` service and set
   `REWRITE_MODE=deepseek`. Keep the two V4 model variables above.
4. After Railway finishes redeploying, `/api/health` must report
   `providerMode.rewrite` as `deepseek`. Complete a harmless owner-only rewrite
   before sending unpublished work.
5. Set the GitHub Actions variable `PAPERLIGHT_EXPECTED_REWRITE_MODE=deepseek`
   and run the `Production smoke` workflow.

The adapter follows DeepSeek's official OpenAI-compatible
[`/chat/completions`](https://api-docs.deepseek.com/api/create-chat-completion)
contract and JSON Output requirements. Current model names and availability are
documented in DeepSeek's [model list](https://api-docs.deepseek.com/api/list-models).
Provider authentication, balance, rate-limit, timeout, malformed JSON, unsafe
semantic drift, and protected-token changes fail closed without logging the
provider response or paper text.

## Pangram and Copyleaks

```dotenv
DETECTOR_MODE=dual
PANGRAM_API_URL=https://api.pangram.com/v1/predict
PANGRAM_API_KEY=<configure-in-secret-manager>
COPYLEAKS_API_URL=https://api.copyleaks.com/v2/writer-detector
COPYLEAKS_ACCESS_TOKEN=<configure-in-secret-manager>
```

Real modes fail closed when credentials are absent. Before sending unpublished papers, verify commercial permission, processing region, retention, deletion, and no-training terms in writing.

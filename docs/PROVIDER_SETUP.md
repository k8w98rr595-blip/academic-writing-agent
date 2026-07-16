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
DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1
PANGRAM_API_URL=https://text.external-api.pangram.com
PANGRAM_API_KEY=<configure-in-secret-manager>
PANGRAM_POLL_INTERVAL_SECONDS=0.75
PANGRAM_MAX_POLL_SECONDS=45
COPYLEAKS_API_URL=https://api.copyleaks.com
COPYLEAKS_LOGIN_URL=https://id.copyleaks.com/v3/account/login/api
COPYLEAKS_EMAIL=<configure-in-secret-manager>
COPYLEAKS_API_KEY=<configure-in-secret-manager>
COPYLEAKS_SANDBOX=0
COPYLEAKS_SENSITIVITY=2
```

`COPYLEAKS_ACCESS_TOKEN` is no longer a deployment credential. The backend exchanges the email and permanent API Key for a 48-hour token and caches it only in process memory.

Real modes fail closed when credentials or the data-processing acknowledgement are absent. Keep `DETECTOR_MODE=mock` and `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0` until commercial permission, processing region, retention, deletion, and no-training terms are verified in writing. Full mappings, official references, fusion rules, and risks are in [Detector Providers](DETECTOR_PROVIDERS.md).

### Railway exact order

1. In the Railway `api` service, add `PANGRAM_API_KEY`, `COPYLEAKS_EMAIL`, and `COPYLEAKS_API_KEY` as backend Variables. Never add them to GitHub Variables, Pages, `NEXT_PUBLIC_*`, or a committed file.
2. Add the official endpoint and timeout values above, but leave `DETECTOR_MODE=mock` and the acknowledgement at `0`.
3. Redeploy and confirm `/api/health` still reports `detector: mock`.
4. After the DPA/retention review, change `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` and `DETECTOR_MODE=dual` in the same planned deployment. Do not enable one real Provider under a UI that claims dual confirmation.
5. Run `python scripts/acceptance_real_detectors.py --confirm-cost` with owner credentials supplied only through local environment variables. The script creates and deletes one synthetic paper and performs one paid dual analysis.
6. If acceptance fails, immediately restore `DETECTOR_MODE=mock`; do not delete or rotate credentials until the failure is classified. Rotate only if there is evidence of credential exposure.

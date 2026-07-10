# Provider setup

The application defaults to `DETECTOR_MODE=mock` and `REWRITE_MODE=mock`.

## DeepSeek V4

```dotenv
REWRITE_MODE=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<configure-in-secret-manager>
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_VALIDATOR_MODEL=deepseek-v4-flash
```

## Pangram and Copyleaks

```dotenv
DETECTOR_MODE=dual
PANGRAM_API_URL=https://api.pangram.com/v1/predict
PANGRAM_API_KEY=<configure-in-secret-manager>
COPYLEAKS_API_URL=https://api.copyleaks.com/v2/writer-detector
COPYLEAKS_ACCESS_TOKEN=<configure-in-secret-manager>
```

Real modes fail closed when credentials are absent. Before sending unpublished papers, verify commercial permission, processing region, retention, deletion, and no-training terms in writing.

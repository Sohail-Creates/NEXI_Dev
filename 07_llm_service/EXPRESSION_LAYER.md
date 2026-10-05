# Optional learned-memory expression

Retrieval remains in Central/TeachMe. Only approved textual memory reaches the
existing authenticated HTTPS `/api/v1/generate` contract. Provider selection is
owned by `llm_service/services/expression_service.py`; shared HTTP adapters live
in `providers.py`. The legacy `OpenRouterClient` import remains supported.

Set `LLM_ENABLED=0` in the environment of both Central and LLM, then restart
those services. Central's REST client short-circuits before any HTTP generation
request. The shared deterministic formatter expresses approved memory without
provider credentials. No camera, embeddings, or retrieval thresholds change.

For enabled mode, set `LLM_ENABLED=1`, `LLM_PROVIDER` to `groq`, `gemini`, or
`openrouter`, and the matching `*_MODEL` and `*_API_KEY`. Existing
`OPENROUTER_API_KEY_ENV` and previous-key credential rotation remain supported.
Missing/invalid configuration degrades optional generation rather than crashing
startup. No provider generation is performed at startup or during health polling.
Health is configuration/runtime capability status, not proof of model quality.

`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, and `LLM_TIMEOUT_SECONDS` configure generation.
Explicit REST sampling settings remain supported; the configured token limit is
an upper bound. One generation request is made, with no provider cascade.
Only existing current/previous-key authentication rotation may retry a rejected
credential, within the same timeout budget. Blocking HTTP runs off the event loop.

Provider failure, empty/malformed output, and rejected grounding fall back to
approved memory in Central. `/generate` itself continues returning the existing
failure contract: it cannot invent a deterministic answer from an arbitrary
prompt. Central owns approved records and the deterministic fallback.

No secrets or full prompts are logged. Set keys only in local/deployment
environment configuration; `.env.example` contains placeholders only.

Groq and Gemini wire formats follow their official HTTP APIs:
[Groq](https://console.groq.com/docs/api-reference),
[Gemini](https://ai.google.dev/api/generate-content).

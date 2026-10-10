# LLM Layer: Remove Vertex AI, Config-Driven Multi-Provider with Fallback

Date: 2026-10-10

## Goal

Replace the hard-coded `google-vertex:<model>` usage with a reliable, config-driven LLM layer that calls providers directly (Anthropic, OpenAI, Gemini via API key). No Vertex AI, no GCP project, no service-account setup. Each role's model (and fallbacks) is chosen purely by configuration.

## Scope

In scope: the LLM layer only (model construction, config, retry/timeout, dependency and env cleanup, tests).
Out of scope: product features (optimizer logic, coach, filters, Supabase, Stripe, etc.).

## Success Criteria

1. No Vertex or GCP code, env vars, or dependencies remain.
2. Changing a model or provider is config-only, e.g. `OPTIMIZATION_MODEL=anthropic:claude-sonnet-5-5` or `google-gla:gemini-2.5-flash`.
3. Retry and timeout handling no longer assumes Vertex error shapes.
4. A primary-provider failure on a transient error falls through to the next configured provider.

## Approach

Thin factory module on top of pydantic-ai 1.48 (already a dependency). pydantic-ai already supports `provider:model` strings and `FallbackModel`; we add no custom client layer.

## Design

### 1. Config and model factory

- New module `src/hr_breaker/llm.py` exposing `build_model(role) -> Model`.
- Roles map to existing settings: `OPTIMIZATION_MODEL` (optimizer, reviewer, parser, filters, auditor), `COACH_MODEL`, `NAME_EXTRACTOR_MODEL`.
- Each value is a comma-separated chain of `provider:model` strings. One entry = no fallback; more than one = `FallbackModel(primary, *fallbacks)`.
- Provider keys use standard env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). Startup validation checks that every provider referenced in a configured chain has its key; missing keys fail at boot with a clear message.
- `GEMINI_THINKING_BUDGET` and `get_model_settings()` are removed (Gemini-specific, decided to drop).
- Default chains (placeholders, adjustable): optimizer role `google-gla:gemini-2.5-flash,anthropic:claude-sonnet-5-5`; coach `google-gla:gemini-2.5-pro,anthropic:claude-sonnet-5-5`; name extractor `google-gla:gemini-2.5-flash-lite`.
- All agents (`optimizer`, `optimizer_v2`, `combined_reviewer`, `content_integrity`, `job_parser`, `auditor`, `coach`, `resume_editor`, `name_extractor`) call `build_model(role)` instead of the `google-vertex:` f-string. The auditor keeps its optional per-call `model` override.

### 2. Retry and fallback

- `FallbackModel` is configured to fall through only on transient failures: HTTP 429, 5xx (incl. 529), connection errors, timeouts. 400/401 do not fall through.
- `utils/retry.py::with_model_retry` is kept but made provider-neutral: retryable statuses 429, 500, 502, 503, 504, 529, plus timeouts. It keeps the per-attempt timeout, the global concurrency semaphore, and full-jitter backoff. When the whole chain fails (`FallbackExceptionGroup`) it backs off and retries per its attempt limit.
- Concurrency cap stays global (`MODEL_MAX_CONCURRENCY`); no per-provider caps (YAGNI).
- Log the provider/model that served each call; log each fallback hop at WARNING.

### 3. Removal and cleanup

- Remove `vertexai.init` and the credentials-JSON block in `api/main.py`.
- Remove `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS*` from code and `.env.example`; remove `gcp_project`/`gcp_location` from `Settings`.
- Replace the CLI's `GOOGLE_CLOUD_PROJECT` check with the provider-key check.
- Dependencies: remove `google-cloud-aiplatform`; replace `pydantic-ai` with `pydantic-ai-slim` using only the `anthropic`, `openai`, `google` extras (plus any extras the code already needs beyond providers, to be verified during planning).
- Mark `docs/plans/2026-06-04-vertex-ai-setup.md` as superseded (header note, file kept).

## Testing

TDD. Tests first for:
1. Factory: single entry, multi-entry becomes `FallbackModel`, unknown provider errors clearly, missing key fails at startup validation.
2. Retry: fake model raising 429/503/timeout is retried with expected counts; 400/401 are not retried.
3. Fallback: primary fails with a transient error, secondary answers (pydantic-ai `FunctionModel`/`TestModel`).
4. Existing suite passes. Tests referencing Vertex/Gemini (e.g. `test_flash_comparison.py`, `test_caps_comparison.py`) are reviewed; live-API experiments are adapted or skipped by default.
5. One manual end-to-end run with a real key after tests pass.

## Risks / Notes

- Structured output and tool-calling behavior can differ between providers; fallback to a different provider may produce slightly different outputs. Prompts are not changed in this work.
- Slimming the pydantic-ai extras must not drop extras the app uses for non-provider features; verify in the plan.

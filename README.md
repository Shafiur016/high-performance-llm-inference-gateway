# LLM Inference Gateway — FastAPI + optional vLLM

A functional OpenAI-style `/v1/chat/completions` gateway with validated request schema, API key gate, per-process sliding-window rate limits, Redis caching for deterministic non-stream responses, SSE passthrough, request/latency/error metrics, estimated token-price tracking, and a concurrent load-test tool. `vLLM` provides server-side continuous batching and optional quantization; this gateway **does not implement GPU kernels or batching itself**.

## CPU-only smoke test (no GPU, no token required)

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
uvicorn gateway.app:app --reload
```

Visit http://localhost:8000/docs. With no `VLLM_URL`, requests return clearly marked **MOCK MODE** text, not AI-generated language. Start `python -m scripts.benchmark --requests 20 --concurrency 5` to measure HTTP overhead only.

## Optional real inference

Run a separate vLLM server with a suitable NVIDIA GPU. Official Docker image: `vllm/vllm-openai`. In another shell, configure `VLLM_URL=http://localhost:8001/v1` and `MODEL_NAME=<exact served model ID>`, restart the gateway, and send a completion request. `docker compose --profile gpu up` includes a GPU service but requires Docker NVIDIA runtime, GPU VRAM, model license approval where applicable, and Hugging Face network access. **No GPU or Docker benchmark was performed for this deliverable.** Quantization and model memory are configured on the vLLM server, not here.

## Evidence to collect
Actual vLLM P95 time-to-first-token, token generation speed, GPU memory, throughput versus concurrency and batching configuration, cache hit rate, rejected requests, and USD/token assumptions. Gateway `/metrics` records TTFT from upstream SSE first data line and non-stream request latency but does **not** measure GPU memory or token/s. In mock mode metrics must not be presented as LLM benchmarks.

## Security limitations
Per-process rate limiting, API-key in headers, minimal logging. Add distributed Redis limiter, key rotation, cost budgets, admission control, timeouts and circuit breakers, and full production observability before deployment.

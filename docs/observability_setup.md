# LLM Observability & Token Usage Monitoring Guide

`prism-reviewer` includes a pluggable monitoring and observability system to track LLM token consumption (`prompt_tokens`, `completion_tokens`, `total_tokens`), request duration, reasoning effort, and agent metadata.

You can monitor token usage locally using **Native In-App Observers** (Console & JSONL log exporter) and/or stream telemetry to external observability platforms using **LiteLLM Callbacks** (**Langfuse** and **OpenTelemetry**).

---

## 1. Quick Overview & Architecture

```
                               ┌──────────────────────────────────┐
                               │ Console Observer (stdout logs)   │
                               ├──────────────────────────────────┤
                               │ JSONL Observer (local file log)  │
┌─────────────────┐            └──────────────────────────────────┘
│  prism-reviewer │  Events                    ▲ Native Observers
│  LLM Engine     ├────────────────────────────┘
└────────┬────────┘
         │
         │ LiteLLM Callbacks
         ├────────────────────────────────────► 📊 Langfuse (Traces, Costs, Prompts)
         │
         └────────────────────────────────────► 📡 OpenTelemetry (Jaeger, Datadog, Grafana)
```

| Monitoring Target | Best For | Requirement |
| :--- | :--- | :--- |
| **Native JSONL Log** | Local audits & lightweight CI usage tracking | Zero external setup (Built-in) |
| **Langfuse** | Deep LLM prompt tracing, model cost analysis & agent latency trees | Langfuse Cloud account OR Self-hosted Docker server |
| **OpenTelemetry (OTel)** | Enterprise APM integration (Grafana Tempo, Datadog, Honeycomb) | OpenTelemetry Collector or APM backend |

---

## 2. Langfuse Setup Guide

Langfuse is a purpose-built LLM observability platform that tracks generation traces, prompt/completion history, token breakdowns, and dollar cost estimations for every agent node (Warden, Architect, Inspector, Verifier).

### Option A: Using Langfuse Cloud (Managed)

1. **Sign Up**: Create an account at [cloud.langfuse.com](https://cloud.langfuse.com).
2. **Create Project**: Create a new project (e.g. `prism-reviewer`).
3. **Generate API Keys**: Navigate to **Project Settings** -> **API Keys** and copy your `Public Key` and `Secret Key`.
4. **Install Python Package**:
   ```bash
   pip install langfuse
   ```
5. **Configure Environment Variables**: Add keys to `.env` or export them:
   ```env
   LANGFUSE_PUBLIC_KEY="pk-lf-..."
   LANGFUSE_SECRET_KEY="sk-lf-..."
   LANGFUSE_HOST="https://cloud.langfuse.com"
   ```
6. **Enable Langfuse Callback**:
   - In `prism_reviewer.toml`:
     ```toml
     [monitoring]
     enabled = "true"
     observers = "console,jsonl"
     litellm_callbacks = "langfuse"
     ```
   - Or via environment variable:
     ```env
     PRISM_MONITORING_LITELLM_CALLBACKS="langfuse"
     ```

---

### Option B: Self-Hosting Your Own Langfuse Server

If you prefer self-hosting for data privacy or local development, you can run your own Langfuse server using Docker Compose.

#### 1. Docker Compose Configuration
Create a `docker-compose.yml` file for your self-hosted Langfuse stack:

```yaml
version: '3.8'

services:
  langfuse-server:
    image: ghcr.io/langfuse/langfuse:2
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse_password@postgres:5432/langfuse
      - NEXTAUTH_SECRET=my-super-secret-nextauth-key-change-in-prod
      - NEXTAUTH_URL=http://localhost:3000
      - SALT=my-super-secret-salt-key-change-in-prod
      - TELEMETRY_ENABLED=false
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    restart: always
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse_password
      - POSTGRES_DB=langfuse
    ports:
      - "5432:5432"
    volumes:
      - langfuse_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse -d langfuse"]
      interval: 3s
      timeout: 3s
      retries: 10

volumes:
  langfuse_postgres_data:
```

#### 2. Start the Server
Run the docker container stack:
```bash
docker compose up -d
```

#### 3. Create Account & Generate Keys
1. Open your browser and navigate to `http://localhost:3000`.
2. Sign up for a local account.
3. Create a new organization and project.
4. Go to **Settings** -> **API Keys** -> **Create new API Keys**.

#### 4. Point `prism-reviewer` to Your Self-Hosted Server
Configure your `.env` or shell environment to point `LANGFUSE_HOST` to your local instance:
```env
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_HOST="http://localhost:3000"

PRISM_MONITORING_LITELLM_CALLBACKS="langfuse"
```

---

## 3. OpenTelemetry (OTel) Setup Guide

OpenTelemetry emits standardized GenAI spans and metrics to your organization's OpenTelemetry Collector or APM (Grafana Tempo, Datadog, Honeycomb, Jaeger).

### 1. Install OpenTelemetry Dependencies
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

### 2. Run Local OTel Collector / Jaeger (Optional for Local Testing)
For local testing, you can spin up a Jaeger OTLP collector via Docker:
```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```
*(Access Jaeger UI at `http://localhost:16686`)*

### 3. Configure OpenTelemetry Environment Variables
```env
OTEL_SERVICE_NAME="prism-reviewer"
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
OTEL_EXPORTER_OTLP_PROTOCOL="grpc" # or "http/protobuf"
```

### 4. Enable `otel` Callback in `prism-reviewer`
- In `prism_reviewer.toml`:
  ```toml
  [monitoring]
  enabled = "true"
  observers = "console,jsonl"
  litellm_callbacks = "otel"
  ```
- Or via environment variable:
  ```env
  PRISM_MONITORING_LITELLM_CALLBACKS="otel"
  ```

---

## 4. Concurrent Dual Observability (Langfuse + OpenTelemetry)

You can enable both Langfuse and OpenTelemetry at the same time to get both specialized LLM prompt/cost tracing in Langfuse and enterprise APM distributed tracing in OpenTelemetry.

* **In `prism_reviewer.toml`**:
  ```toml
  [monitoring]
  enabled = "true"
  observers = "console,jsonl"
  litellm_callbacks = "langfuse,otel"
  ```

* **Or via Environment Variables**:
  ```env
  LANGFUSE_PUBLIC_KEY="pk-lf-..."
  LANGFUSE_SECRET_KEY="sk-lf-..."
  LANGFUSE_HOST="http://localhost:3000"

  OTEL_SERVICE_NAME="prism-reviewer"
  OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

  PRISM_MONITORING_LITELLM_CALLBACKS="langfuse,otel"
  ```

---

## 5. Verifying Telemetry & Token Logs

### Checking Local JSONL Audit Logs
Inspect `.prism_reviewer/token_usage.jsonl`:
```bash
cat .prism_reviewer/token_usage.jsonl
```
Example JSON line output:
```json
{
  "timestamp": 1770997200.123,
  "model": "openai/gpt-4o",
  "prompt_tokens": 1420,
  "completion_tokens": 310,
  "total_tokens": 1730,
  "duration_seconds": 1.4521,
  "reasoning_effort": "high",
  "caller_context": {"agent": "warden", "region_index": 0}
}
```

### Checking Langfuse Dashboard
Log in to your Langfuse dashboard (`https://cloud.langfuse.com` or `http://localhost:3000`). You will see a breakdown of:
- **Traces**: Full execution spans across Warden, Architect, Inspector, and Verifier.
- **Generations**: Input prompts and output responses.
- **Token Metrics**: Total input, output, and reasoning tokens.
- **Cost Analytics**: Estimated dollar costs grouped by model name.

### Checking OpenTelemetry / Jaeger UI
Log in to your Jaeger UI (`http://localhost:16686`) or Grafana Tempo dashboard:
- Select service: `prism-reviewer`.
- Inspect spans named `litellm:completion` with GenAI semantic attributes (`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`).

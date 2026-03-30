# Patient Dataset Generation

Async pipeline for generating synthetic patient datasets using FastAPI + Celery + RabbitMQ + PostgreSQL + AWS Bedrock. The pipeline runs 8 sequential steps, each an independent Celery worker, producing clinical artifacts for a single patient.

## Pipeline Steps

| Step | Phase | Output artifact |
|------|-------|-----------------|
| 1 | `step1_metadata` | `metadata.json` |
| 2 | `step2_referral_packet` | `referral_packet.txt`, `medication_list.json` |
| 3 | `step3_ambient_scribe` | `ambient_scribe.txt` *(if enabled)* |
| 4 | `step4_gap_answers` | `tap_tap_gap_answers.json` |
| 5 | `step5_oasis_gold_standard` | `oasis_gold_standard.json` |
| 6 | `step6_consistency_validation` | `validation_report.json` |
| 7 | `step7_llm_audit` | `llm_audit_report.json` *(if requested)* |
| Repair | `repair_gap_answers` → `repair_gold_standard` | In-place fixes *(on validation failure)* |

All artifacts are written to `output/{patient_external_id}/`.

## Stack

Two Docker Compose files are used:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Main app — FastAPI, Celery workers, Postgres (app DB), RabbitMQ |
| `docker-compose.langfuse.yml` | Langfuse observability — Langfuse UI + its own dedicated Postgres |

Both stacks share the external Docker network `patient_gen_network` so app containers can reach Langfuse at `http://langfuse:3000` by container name.

## Quick Start

```bash
cd patient-dataset-generation
cp .env.example .env
# Add your AWS credentials to .env
./scripts/start.sh
```

This single script:
1. Creates the shared Docker network `patient_gen_network` (idempotent)
2. Starts the Langfuse stack and waits for its Postgres to be healthy
3. Starts the main stack (builds images, starts all services)
4. Waits for the main Postgres to be healthy
5. Runs Alembic migrations
6. Prints all service URLs

To follow logs after startup:

```bash
./scripts/start.sh --fg
```

## API

### Enqueue a patient

```bash
curl -X POST http://localhost:8081/api/v1/patient-generation/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "patient_external_id": "PATIENT-0001",
    "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "perform_llm_audit": false
  }'
```

### Poll status

```bash
curl http://localhost:8081/api/v1/patient-generation/<job_id>
```

### Manually trigger repair

```bash
curl -X POST http://localhost:8081/api/v1/patient-generation/<job_id>/repair
```

### Health check

```bash
curl http://localhost:8081/health
```

## Service UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| RabbitMQ management | http://localhost:15672 | `guest` / `guest` |
| Langfuse observability | http://localhost:3000 | set on first login |

## LLM Observability (Langfuse)

All Bedrock invocations are instrumented with [Langfuse](https://langfuse.com) (self-hosted via `docker-compose.langfuse.yml`). Each patient generation is tracked as a **Session** (grouped by `job_id`), with one **Trace** per pipeline step. Each trace captures:

- Input and output token counts
- Estimated cost (based on model pricing)
- Latency
- Full prompt and response content

### Enable tracing

Langfuse starts automatically with `./scripts/start.sh`. To start sending traces:

1. Open http://localhost:3000 and create an account + project
2. Copy the API keys from **Settings → API Keys**
3. Add to `.env`:

```ini
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

4. Restart api + workers:

```bash
docker compose up -d api worker worker-step2 worker-step3 worker-step4 worker-step5 worker-step6 worker-step7
```

> `LANGFUSE_HOST` is **not** needed in `.env` — it is automatically set to `http://langfuse:3000` (the container name) inside Docker via `docker-compose.yml`.

### How it works

- Tracing is **disabled by default** (`LANGFUSE_ENABLED=false`). When disabled, there is zero overhead — no callbacks are attached and no network calls are made.
- All tracing logic lives in `app/services/llm/langfuse_tracing.py`. The central `BedrockClient.invoke_json()` attaches a `LangfuseCallbackHandler` before each LLM call — generators require no changes.
- Step context (`step_name`, `patient_id`, `model_id`) is stored in a `ContextVar` by each Celery task, isolated per worker thread.

### Langfuse data model

```
Session  (session_id = job_id)
  └── Trace: step1_metadata
  └── Trace: step2_referral_packet
        └── Generation: referral packet LLM call
        └── Generation: medication list LLM call
  └── Trace: step3_ambient_scribe
  └── ...
```

## Notes

- Model invocation requires valid AWS credentials available to containers (via environment variables or an IAM instance profile).
- The Langfuse container uses a dedicated `postgres-langfuse` service with its own volume, completely separate from the application database.

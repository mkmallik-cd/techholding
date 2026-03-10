# Patient Dataset Generation (Step 1)

Standalone service for Step 1 of the workflow: generate dummy patient metadata asynchronously using FastAPI + Celery + RabbitMQ + PostgreSQL, then write artifacts to a local folder.

## What Step 1 Does

- Accepts enqueue request with `patient_external_id` and dynamic `model_id`.
- Creates tracking row in `patient_generation_jobs`.
- Enqueues Celery task to RabbitMQ.
- Worker generates patient metadata with Bedrock.
- Writes artifacts under `output/{patient_external_id}/`:
  - `metadata.json` (PRD Section 0D.1 schema)
  - `docs/placeholders/referral_summary.txt`
  - `docs/placeholders/clinical_summary.txt`
  - `docs/placeholders/oasis_draft.txt`

## Quick Start

```bash
cd patient-dataset-generation
cp .env.example .env
docker compose up --build
```

Run migration in a second terminal:

```bash
docker compose exec api alembic upgrade head
```

## API

1. Enqueue

```bash
curl -X POST http://localhost:8081/api/v1/patient-generation/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "patient_external_id": "PATIENT-0001",
    "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "hardcoded_seed": "default-step1-seed"
  }'
```

2. Get Status

```bash
curl http://localhost:8081/api/v1/patient-generation/<job_id>
```

## RabbitMQ UI

- URL: `http://localhost:15672`
- Username: `guest`
- Password: `guest`

## Notes

- This implementation is intentionally limited to Step 1.
- Model invocation requires valid AWS credentials available to containers.

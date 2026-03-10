from fastapi import FastAPI

from app.api.v1.patient_generation import router as patient_generation_router
from app.config.settings import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(patient_generation_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

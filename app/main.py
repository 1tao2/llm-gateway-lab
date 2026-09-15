from typing import Literal, TypedDict

from fastapi import FastAPI

from app.config import get_settings


class HealthResponse(TypedDict):
    status: Literal["ok"]


settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.get("/health", tags=["system"])
async def health() -> HealthResponse:
    return {"status": "ok"}

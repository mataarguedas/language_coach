import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, languages, segment, shadow, synthesize, voices


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="Pronunciation Coach API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(languages.router, prefix="/api", tags=["languages"])
app.include_router(voices.router, prefix="/api", tags=["voices"])
app.include_router(segment.router, prefix="/api", tags=["segment"])
app.include_router(synthesize.router, prefix="/api", tags=["synthesize"])
app.include_router(shadow.router, prefix="/api/shadow", tags=["shadow"])

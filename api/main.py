from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.routes.v1 import router as v1_router


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="EchoWhale API for scene-based English conversation practice.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix=settings.api_prefix)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

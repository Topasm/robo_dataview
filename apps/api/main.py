from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    annotations,
    datasets,
    episodes,
    exports,
    frames,
    jobs,
    rerun,
    search,
    versions,
)


app = FastAPI(
    title="Robot Data Studio API",
    version="0.1.0",
    description="API for Lance-native LeRobot dataset curation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):30[0-9]{2}$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router, prefix="/api")
app.include_router(episodes.router, prefix="/api")
app.include_router(frames.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(rerun.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(versions.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

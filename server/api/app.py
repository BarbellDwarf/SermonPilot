"""SermonPilot read-only API bridge (Phase 4a).

Serves GET-only JSON over ``/api/*`` from the live SQLite database opened
read-only, plus the built SPA from ``web/dist`` when present. The Streamlit
app and the processing pipeline are untouched.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from server.api.routers.jobs import router as jobs_router
from server.api.routers.sermons import router as sermons_router
from server.api.routers.status import router as status_router

DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def create_app() -> FastAPI:
    app = FastAPI(title="SermonPilot read-only bridge")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(status_router)
    app.include_router(sermons_router)
    app.include_router(jobs_router)

    dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist.is_dir():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):  # type: ignore[no-redef]
            candidate = (dist / path).resolve() if path else None
            if (
                candidate is not None
                and str(candidate).startswith(str(dist))
                and candidate.is_file()
            ):
                return FileResponse(str(candidate))
            return FileResponse(str(dist / "index.html"))

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "server.api.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8504")),
    )


if __name__ == "__main__":
    main()

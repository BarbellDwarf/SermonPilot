"""SermonPilot read-only API bridge (Phase 4a).

Serves GET-only JSON over ``/api/*`` from the live SQLite database opened
read-only, plus the built SPA from ``web/dist`` when present. The Streamlit
app and the processing pipeline are untouched.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from server.api.accounts import migrate
from server.api.routers.app_config import router as app_config_router
from server.api.routers.auth import router as auth_router
from server.api.routers.cloud import proxy_router as cloud_proxy_router
from server.api.routers.cloud import router as cloud_router
from server.api.routers.jobs import router as jobs_router
from server.api.routers.llm_config import router as llm_config_router
from server.api.routers.media import router as media_router
from server.api.routers.meta import router as meta_router
from server.api.routers.sermons import library_router as library_router
from server.api.routers.sermons import router as sermons_router
from server.api.routers.status import router as status_router
from server.api.routers.userdata import (
    admin_backup_router,
    explore_router,
    files_router,
    me_router,
)
from server.api.routers.userdata import (
    router as userdata_router,
)
from server.api.routers.writes import router as writes_router

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
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    @app.on_event("startup")
    def _migrate_accounts() -> None:
        try:
            migrate()
        except Exception:  # pragma: no cover - read-only deployments keep working
            pass

    app.include_router(auth_router)
    app.include_router(status_router)

    from server.api.routers.auth import PUBLIC_PATHS

    @app.middleware("http")
    async def auth_gate(request, call_next):
        path = request.url.path
        if path.startswith("/api") and not any(
            path == p or path.startswith(p + "/") for p in PUBLIC_PATHS
        ):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not token and path.startswith("/api/media"):
                # <audio>/<video> cannot attach an Authorization header; the
                # media routes accept the session token as a query parameter.
                token = request.query_params.get("token", "").strip()
            from server.api.accounts import get_session_user, writable_conn
            if not token:
                return _auth_denied(path)
            try:
                with writable_conn() as conn:
                    user = get_session_user(conn, token)
            except sqlite3.OperationalError:
                return _auth_denied(path)  # accounts tables absent -> unbootstrapped
            if user is None:
                return _auth_denied(path)
            request.state.user = dict(user)
        return await call_next(request)

    def _auth_denied(path: str):
        from fastapi.responses import JSONResponse

        from server.api.accounts import count_users, writable_conn
        try:
            with writable_conn() as conn:
                bootstrapped = count_users(conn) > 0
        except sqlite3.OperationalError:
            bootstrapped = False
        return JSONResponse(
            status_code=401,
            content={"detail": {"needs_bootstrap": not bootstrapped, "message": "authentication required"}},  # noqa: E501
        )
    app.include_router(sermons_router)
    app.include_router(library_router)
    app.include_router(jobs_router)
    app.include_router(media_router)
    app.include_router(meta_router)
    app.include_router(userdata_router)
    app.include_router(me_router)
    app.include_router(admin_backup_router)
    app.include_router(writes_router)
    app.include_router(llm_config_router)
    app.include_router(app_config_router)
    app.include_router(files_router)
    app.include_router(explore_router)
    app.include_router(cloud_router)
    app.include_router(cloud_proxy_router)

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

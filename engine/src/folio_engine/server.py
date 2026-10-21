from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .auth import require_token
from .config import ConfigStore

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "http://localhost:1420",
]


def create_app(token: str, data_dir: Path, **overrides: Any) -> FastAPI:
    app = FastAPI(title="Folio Engine", version=__version__)
    app.state.token = token
    app.state.data_dir = data_dir
    app.state.config = ConfigStore(data_dir / "settings.json")
    for name, value in overrides.items():
        setattr(app.state, name, value)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    return app

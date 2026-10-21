from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .auth import require_token
from .config import ConfigStore
from .hardware import detect_hardware, free_disk_gb, ollama_models_dir
from .ollama.client import OllamaClient
from .ollama.install import default_installer
from .pull import PullManager
from .routes import setup

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "http://localhost:1420",
]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup must never fail because of a download.
    with suppress(Exception):
        app.state.pull_manager.resume_if_needed()
    yield


def create_app(token: str, data_dir: Path, **overrides: Any) -> FastAPI:
    app = FastAPI(title="Folio Engine", version=__version__, lifespan=_lifespan)
    app.state.token = token
    app.state.data_dir = data_dir
    app.state.config = ConfigStore(data_dir / "settings.json")
    app.state.detect_hardware = detect_hardware
    app.state.ollama_client = OllamaClient()
    app.state.installer = default_installer(
        data_dir / "downloads", app.state.ollama_client
    )
    for name, value in overrides.items():
        setattr(app.state, name, value)
    if "pull_manager" not in overrides:
        # Built after overrides so it uses any injected client/config.
        app.state.pull_manager = PullManager(
            app.state.ollama_client,
            app.state.config,
            lambda: free_disk_gb(ollama_models_dir()),
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    app.include_router(setup.router)

    return app

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import require_token
from ..catalog import MODEL_CATALOG, recommend
from ..config import Settings
from ..hardware import ollama_models_dir
from ..ollama.detect import find_ollama, start_ollama

router = APIRouter(prefix="/setup", dependencies=[Depends(require_token)])


@router.get("/hardware")
def get_hardware(request: Request) -> dict[str, Any]:
    hw = request.app.state.detect_hardware(ollama_models_dir())
    return {"hardware": asdict(hw), "recommendation": asdict(recommend(hw))}


@router.get("/ollama")
def get_ollama(request: Request) -> dict[str, Any]:
    return asdict(find_ollama(request.app.state.ollama_client))


@router.post("/ollama/start")
def post_ollama_start(request: Request) -> dict[str, bool]:
    client = request.app.state.ollama_client
    status = find_ollama(client)
    return {"running": start_ollama(status, client)}


def _installer(request: Request):
    installer = request.app.state.installer
    if installer is None:
        raise HTTPException(
            400, "One-click install is only available on macOS and Windows."
        )
    return installer


@router.post("/ollama/install", status_code=202)
def post_ollama_install(request: Request) -> dict[str, bool]:
    _installer(request).start()
    return {"started": True}


@router.get("/ollama/install")
def get_ollama_install(request: Request) -> dict[str, Any]:
    return asdict(_installer(request).status())


class ModelChoice(BaseModel):
    model: str


@router.put("/model", status_code=202)
def put_model(choice: ModelChoice, request: Request) -> dict[str, bool]:
    tier = next((m for m in MODEL_CATALOG if m.name == choice.model), None)
    if tier is None:
        raise HTTPException(400, "That model isn't one Folio can set up.")
    pulls = request.app.state.pull_manager
    active = pulls.status()
    if active.state == "downloading" and active.model != tier.name:
        raise HTTPException(
            409,
            "Another model is already downloading. Wait for it to finish or retry.",
        )
    config = request.app.state.config
    current = config.load()
    config.save(
        Settings(
            provider="ollama",
            model=tier.name,
            base_url=current.base_url,
            setup_complete=False,
        )
    )
    pulls.start(tier.name, tier.size_gb)
    return {"started": True}


@router.get("/pull")
def get_pull(request: Request) -> dict[str, Any]:
    return asdict(request.app.state.pull_manager.status())


@router.post("/pull/retry", status_code=202)
def post_pull_retry(request: Request) -> dict[str, bool]:
    model = request.app.state.config.load().model
    if not model:
        raise HTTPException(400, "No model has been chosen yet.")
    size = next((m.size_gb for m in MODEL_CATALOG if m.name == model), None)
    request.app.state.pull_manager.start(model, size)
    return {"started": True}

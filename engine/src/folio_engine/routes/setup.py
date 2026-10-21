from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_token
from ..catalog import recommend
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

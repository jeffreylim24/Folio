from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request

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

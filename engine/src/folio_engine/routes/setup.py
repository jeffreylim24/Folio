from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..auth import require_token
from ..catalog import recommend
from ..hardware import ollama_models_dir

router = APIRouter(prefix="/setup", dependencies=[Depends(require_token)])


@router.get("/hardware")
def get_hardware(request: Request) -> dict[str, Any]:
    hw = request.app.state.detect_hardware(ollama_models_dir())
    return {"hardware": asdict(hw), "recommendation": asdict(recommend(hw))}

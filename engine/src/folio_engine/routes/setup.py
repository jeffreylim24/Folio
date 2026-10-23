from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel

from ..auth import require_token
from ..catalog import advise, find_model
from ..config import ProviderName, Settings
from ..hardware import ollama_models_dir
from ..ollama.detect import find_ollama, start_ollama
from ..providers import ProviderError, make_provider

router = APIRouter(prefix="/setup", dependencies=[Depends(require_token)])

MSG_KEYCHAIN_SAVE = (
    "Folio couldn't save your key to the system keychain. "
    "Check that you allowed access, then try again."
)
MSG_KEYCHAIN_READ = (
    "Folio couldn't read your key from the system keychain. "
    "Check that you allowed access, then try again."
)


@router.get("/hardware")
def get_hardware(request: Request) -> dict[str, Any]:
    hw = request.app.state.detect_hardware(ollama_models_dir())
    return asdict(advise(hw))


@router.get("/ollama")
def get_ollama(request: Request) -> dict[str, Any]:
    return asdict(find_ollama(request.app.state.ollama_client))


@router.post("/ollama/start")
def post_ollama_start(request: Request) -> dict[str, bool]:
    client = request.app.state.ollama_client
    status = find_ollama(client)
    running = start_ollama(status, client)
    if running:
        # Ollama may have been down when the engine started; pick up any
        # unfinished download now.
        request.app.state.pull_manager.resume_in_background()
    return {"running": running}


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


@router.post("/ollama/update", status_code=202)
def post_ollama_update(request: Request) -> dict[str, bool]:
    installer = _installer(request)
    if not find_ollama(request.app.state.ollama_client).updatable:
        raise HTTPException(
            400, "Folio can only update Ollama installed the standard way."
        )
    installer.start(update=True)
    return {"started": True}


@router.get("/ollama/install")
def get_ollama_install(request: Request) -> dict[str, Any]:
    return asdict(_installer(request).status())


class ProviderChoice(BaseModel):
    # API providers are saved by POST /setup/api-provider once the key works.
    provider: Literal["ollama"]


@router.put("/provider")
def put_provider(choice: ProviderChoice, request: Request) -> dict[str, bool]:
    """Save "run privately" as soon as it is picked, so a relaunch (e.g. after
    installing Ollama) continues from there."""
    config = request.app.state.config
    current = config.load()
    model = current.model if current.provider == "ollama" else None
    config.save(Settings(provider=choice.provider, model=model))
    return {"ok": True}


class ModelChoice(BaseModel):
    model: str


@router.put("/model", status_code=202)
def put_model(choice: ModelChoice, request: Request) -> dict[str, bool]:
    model = find_model(choice.model)
    if model is None:
        raise HTTPException(400, "That model isn't one Folio can set up.")
    pulls = request.app.state.pull_manager
    active = pulls.status()
    if active.state == "downloading" and active.model != model.tag:
        raise HTTPException(
            409,
            "Another model is already downloading. Wait for it to finish or retry.",
        )
    config = request.app.state.config
    current = config.load()
    config.save(
        Settings(
            provider="ollama",
            model=model.tag,
            base_url=current.base_url,
            setup_complete=False,
        )
    )
    pulls.start(model.tag, model.download_gb)
    return {"started": True}


@router.get("/pull")
def get_pull(request: Request) -> dict[str, Any]:
    return asdict(_pull_status(request.app.state.pull_manager))


def _pull_status(pulls):
    pulls.resume_in_background()
    return pulls.status()


@router.post("/pull/retry", status_code=202)
def post_pull_retry(request: Request) -> dict[str, bool]:
    model = request.app.state.config.load().model
    if not model or find_model(model) is None:
        raise HTTPException(400, "No model has been chosen yet.")
    # No full-size disk check here: part of the model may already be on disk.
    request.app.state.pull_manager.start(model, None)
    return {"started": True}


def _provider_error(exc: ProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"kind": exc.kind, "message": exc.message}
    )


class ApiProviderChoice(BaseModel):
    provider: ProviderName
    api_key: str
    base_url: str | None = None


@router.post("/api-provider")
def post_api_provider(choice: ApiProviderChoice, request: Request):
    if choice.provider == "ollama":
        raise HTTPException(400, "Ollama doesn't use an API key.")
    base_url = None
    if choice.provider == "openai_compatible":
        base_url = (choice.base_url or "").strip() or None
        if base_url is None:
            raise HTTPException(400, "A base URL is required for this provider.")
    state = request.app.state
    settings = Settings(provider=choice.provider, base_url=base_url)
    try:
        provider = make_provider(settings, state.secrets, api_key=choice.api_key)
        models = provider.list_models()
    except ProviderError as exc:
        return _provider_error(exc)
    try:
        state.secrets.set_api_key(choice.provider, choice.api_key)
    except KeyringError:
        return _provider_error(ProviderError("other", MSG_KEYCHAIN_SAVE))
    state.config.save(settings)
    return {"models": models}


class ApiModelChoice(BaseModel):
    model: str


@router.put("/api-model")
def put_api_model(choice: ApiModelChoice, request: Request) -> dict[str, bool]:
    config = request.app.state.config
    current = config.load()
    if current.provider is None or current.provider == "ollama":
        raise HTTPException(400, "Choose an API provider first.")
    config.save(
        Settings(
            provider=current.provider,
            model=choice.model,
            base_url=current.base_url,
            setup_complete=False,
        )
    )
    return {"ok": True}


@router.post("/test")
def post_test(request: Request):
    state = request.app.state
    settings = state.config.load()
    if settings.provider is None or not settings.model:
        return _provider_error(
            ProviderError("other", "Choose a provider and model first.")
        )
    try:
        provider = make_provider(
            settings, state.secrets, ollama_client=state.ollama_client
        )
        reply = provider.complete(
            [{"role": "user", "content": "Reply with exactly one word: ready"}]
        )
    except ProviderError as exc:
        return _provider_error(exc)
    except KeyringError:
        return _provider_error(ProviderError("other", MSG_KEYCHAIN_READ))
    settings.setup_complete = True
    state.config.save(settings)
    return {"reply": reply}


@router.get("/state")
def get_state(request: Request) -> dict[str, Any]:
    state = request.app.state
    settings = state.config.load()
    if (
        settings.provider == "ollama"
        and settings.model
        and find_model(settings.model) is None
    ):
        # Only catalog models are supported; forget any other saved choice.
        settings.model = None
        settings.setup_complete = False
        state.config.save(settings)
    try:
        has_key = bool(
            settings.provider
            and settings.provider != "ollama"
            and state.secrets.get_api_key(settings.provider)
        )
    except KeyringError:
        has_key = False  # the key flow will ask again and report the problem
    ollama = None
    if settings.provider in (None, "ollama"):
        ollama = asdict(find_ollama(state.ollama_client))
    return {
        "settings": asdict(settings),
        "has_api_key": has_key,
        "ollama": ollama,
        "pull": asdict(_pull_status(state.pull_manager)),
    }

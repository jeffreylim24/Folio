import hmac

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    """FastAPI dependency: checks the bearer token stored on app.state."""
    supplied = request.headers.get("Authorization", "").encode()
    expected = f"Bearer {request.app.state.token}".encode()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

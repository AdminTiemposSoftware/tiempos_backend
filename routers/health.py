from fastapi import APIRouter

from db import ping

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    ping()
    return {"status": "ok"}

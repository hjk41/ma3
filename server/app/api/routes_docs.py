from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse


router = APIRouter(tags=["docs"])

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"


@router.get("/agents.md", response_class=PlainTextResponse)
def get_agents_md() -> str:
    return (DOCS_DIR / "agents.md").read_text(encoding="utf-8")

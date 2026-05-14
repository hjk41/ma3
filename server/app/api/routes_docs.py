import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings


router = APIRouter(tags=["docs"])

DOCS_DIR   = Path(__file__).resolve().parents[1] / "docs"
CLIENT_DIR = Path(__file__).resolve().parents[3] / "client"

CLIENT_MANIFEST_FILES = [
    ("skills/ma3/scripts/ma3_client.py", "/client/ma3_client.py"),
    ("skills/ma3/SKILL.md", "/client/SKILL.md"),
    ("AGENTS.md", "/client/AGENTS.md"),
    ("examples/search-payload.example.json", "/client/examples/search-payload.example.json"),
    ("examples/ingest-payload.example.json", "/client/examples/ingest-payload.example.json"),
]


def _client_file(rel_path: str) -> Path:
    path = CLIENT_DIR / rel_path
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"client file not found: {rel_path}")
    return path


@router.get("/agents.md", response_class=PlainTextResponse)
def get_agents_md() -> str:
    text = (DOCS_DIR / "agents.md").read_text(encoding="utf-8")
    if settings.public_base_url:
        text = text.replace("https://hjk41.cc", settings.public_base_url.rstrip("/"))
    return text


@router.get("/install.sh", response_class=PlainTextResponse)
def get_install_sh() -> str:
    return (CLIENT_DIR / "install.sh").read_text(encoding="utf-8")


@router.get("/install.ps1", response_class=PlainTextResponse)
def get_install_ps1() -> str:
    return (CLIENT_DIR / "install.ps1").read_text(encoding="utf-8")


@router.get("/client/ma3_client.py", response_class=PlainTextResponse)
def get_ma3_client() -> str:
    return (CLIENT_DIR / "skills" / "ma3" / "scripts" / "ma3_client.py").read_text(encoding="utf-8")


@router.get("/client/SKILL.md", response_class=PlainTextResponse)
def get_skill_md() -> str:
    return (CLIENT_DIR / "skills" / "ma3" / "SKILL.md").read_text(encoding="utf-8")


@router.get("/client/AGENTS.md", response_class=PlainTextResponse)
def get_client_agents_md() -> str:
    return (CLIENT_DIR / "AGENTS.md").read_text(encoding="utf-8")


@router.get("/client/manifest.json")
def get_client_manifest() -> dict:
    files = []
    for rel_path, url in CLIENT_MANIFEST_FILES:
        path = _client_file(rel_path)
        content = path.read_bytes()
        files.append(
            {
                "path": rel_path,
                "url": url,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return {
        "client_version": settings.recommended_client_version,
        "min_client_version": settings.min_client_version,
        "recommended_client_version": settings.recommended_client_version,
        "files": files,
    }


@router.get("/client/uninstall.sh", response_class=PlainTextResponse)
def get_uninstall_sh() -> str:
    return (CLIENT_DIR / "uninstall.sh").read_text(encoding="utf-8")


@router.get("/client/uninstall.ps1", response_class=PlainTextResponse)
def get_uninstall_ps1() -> str:
    return (CLIENT_DIR / "uninstall.ps1").read_text(encoding="utf-8")


@router.get("/client/examples/search-payload.example.json", response_class=PlainTextResponse)
def get_search_example() -> str:
    return (CLIENT_DIR / "examples" / "search-payload.example.json").read_text(encoding="utf-8")


@router.get("/client/examples/ingest-payload.example.json", response_class=PlainTextResponse)
def get_ingest_example() -> str:
    return (CLIENT_DIR / "examples" / "ingest-payload.example.json").read_text(encoding="utf-8")

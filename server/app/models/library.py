from typing import Optional

from pydantic import BaseModel, field_validator


class LibraryCreate(BaseModel):
    name: str
    description: str = ""
    is_public: bool = False
    organization_id: Optional[str] = None
    parent_library_id: Optional[str] = None
    is_personal: bool = False


class Library(LibraryCreate):
    library_id: str
    created_at: str


_VALID_ROLES = frozenset({"reader", "writer", "admin"})


class TokenCreate(BaseModel):
    label: str
    role: str = "writer"  # "reader" | "writer" | "admin"

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(_VALID_ROLES))}")
        return v


class TokenInfo(BaseModel):
    token_id: str
    library_id: str
    label: str
    role: str
    created_at: str


class TokenCreated(TokenInfo):
    """Returned once when a token is first created. The raw token is never stored."""
    token: str


class InviteCode(BaseModel):
    code_id: str
    created_at: str
    used_at: Optional[str] = None
    used_by_library_id: Optional[str] = None


class InviteCodeCreated(InviteCode):
    """Returned once when an invite code is created. The raw code is never stored."""
    code: str


class UseInviteRequest(BaseModel):
    code: str
    name: str
    description: str = ""


class UseInviteResponse(BaseModel):
    library: Library
    token_id: str
    token: str  # raw admin token — show to user once

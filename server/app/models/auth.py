from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PrincipalKind = Literal["user", "service", "legacy", "admin", "anonymous"]
PrincipalStoredKind = Literal["user", "service", "legacy"]
AuthVia = Literal["api_key", "sso_cookie", "admin_key", "anonymous"]
LibraryRole = Literal["reader", "writer", "admin"]

ROLE_ORDER: dict[str, int] = {"reader": 1, "writer": 2, "admin": 3}


@dataclass(frozen=True, slots=True)
class ResolvedPrincipal:
    principal_id: str
    kind: str
    display_name: str
    via: str
    is_admin_bypass: bool
    api_key_id: str | None = None
    api_key_scope: frozenset[str] | None = None
    token_id: str | None = None
    library_id: str | None = None
    label: str | None = None
    role: str | None = None

    @property
    def is_anonymous(self) -> bool:
        return self.kind == "anonymous"


class Principal(BaseModel):
    principal_id: str
    kind: PrincipalStoredKind
    display_name: str
    sso_user: str | None = None
    created_at: str
    is_admin: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PrincipalSummary(BaseModel):
    principal_id: str
    kind: str
    display_name: str


class ApiKeyInfo(BaseModel):
    key_id: str
    principal_id: str
    label: str
    scope_libraries: list[str] | None = None
    created_at: str
    created_by: str
    last_used_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None


class ApiKeyIssued(BaseModel):
    raw: str
    info: ApiKeyInfo


class AclEntry(BaseModel):
    library_id: str
    principal_id: str
    role: LibraryRole
    granted_at: str
    granted_by: str
    principal: PrincipalSummary | None = None


class AuthAuditEntry(BaseModel):
    audit_id: str
    actor_principal_id: str
    action: str
    target_principal_id: str | None = None
    library_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class EffectiveLibrary(BaseModel):
    library_id: str
    role: LibraryRole
    source: str = "acl"
    name: str | None = None
    is_public: bool | None = None


class PrincipalBlock(BaseModel):
    principal_id: str
    kind: str
    display_name: str


class WhoamiResponse(BaseModel):
    principal: PrincipalBlock
    via: str
    libraries: list[EffectiveLibrary]
    api_key: ApiKeyInfo | None = None
    admin_bypass: bool = False


class IssueApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    scope_libraries: list[str] | None = None
    expires_at: str | None = None


class ServicePrincipalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str


class AclGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: LibraryRole

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, value: str) -> str:
        if value not in ROLE_ORDER:
            raise ValueError("role must be one of reader, writer, admin")
        return value


class LibraryCreateV3Response(BaseModel):
    library: Any
    grant: AclEntry | None = None

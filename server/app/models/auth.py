from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PrincipalKind = Literal["user", "service", "legacy", "admin", "anonymous"]
PrincipalStoredKind = Literal["user", "service", "legacy"]
AuthVia = Literal["api_key", "sso_cookie", "admin_key", "anonymous"]
LibraryRole = Literal["reader", "writer", "admin"]


class Permission(str, Enum):
    RECORD_READ = "record:read"
    RECORD_WRITE = "record:write"
    RECORD_DELETE = "record:delete"
    CASE_READ = "case:read"
    CASE_WRITE = "case:write"
    RELATION_READ = "relation:read"
    RELATION_WRITE = "relation:write"
    FEEDBACK_READ = "feedback:read"
    FEEDBACK_WRITE = "feedback:write"
    LIBRARY_MANAGE_ACL = "library:manage_acl"
    LIBRARY_DELETE = "library:delete"
    KEY_SCOPE_TO_LIBRARY = "key:scope_to_library"
    SYSTEM_ADMIN = "system:admin"


BUILTIN_ROLES_LIBRARY_READER = [
    Permission.RECORD_READ.value,
    Permission.CASE_READ.value,
    Permission.RELATION_READ.value,
    Permission.FEEDBACK_READ.value,
]
BUILTIN_ROLES_LIBRARY_WRITER = [
    Permission.RECORD_READ.value,
    Permission.RECORD_WRITE.value,
    Permission.CASE_READ.value,
    Permission.CASE_WRITE.value,
    Permission.RELATION_READ.value,
    Permission.RELATION_WRITE.value,
    Permission.FEEDBACK_READ.value,
    Permission.FEEDBACK_WRITE.value,
]
BUILTIN_ROLES: dict[str, list[str]] = {
    "library_reader": BUILTIN_ROLES_LIBRARY_READER,
    "library_writer": BUILTIN_ROLES_LIBRARY_WRITER,
    "library_admin": [
        *BUILTIN_ROLES_LIBRARY_WRITER,
        Permission.LIBRARY_MANAGE_ACL.value,
        Permission.LIBRARY_DELETE.value,
        Permission.KEY_SCOPE_TO_LIBRARY.value,
    ],
    "system_admin": ["*"],
}
ROLE_SCOPE_TYPES: dict[str, str] = {
    "library_reader": "library",
    "library_writer": "library",
    "library_admin": "library",
    "system_admin": "system",
}
ROLE_TO_LIBRARY_ROLE: dict[str, str] = {
    "library_reader": "reader",
    "library_writer": "writer",
    "library_admin": "admin",
}
LIBRARY_ROLE_TO_ROLE: dict[str, str] = {v: k for k, v in ROLE_TO_LIBRARY_ROLE.items()}

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


class Role(BaseModel):
    role_name: str
    scope_type: str
    permissions: list[str] = Field(default_factory=list)
    description: str = ""
    created_at: str


class RoleAssignment(BaseModel):
    scope_type: str
    scope_id: str | None = None
    principal_id: str
    role_name: str
    granted_at: str
    granted_by: str
    principal: PrincipalSummary | None = None


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
    roles: list[RoleAssignment] = Field(default_factory=list)


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

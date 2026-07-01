from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrgRole = Literal["owner", "admin", "member"]
PlanTier = Literal["free", "paid", "enterprise"]
LibraryRole = Literal["reader", "writer", "admin"]
KeyGrantRole = Literal["reader", "writer", "admin"]

ROLE_ORDER: dict[str, int] = {"reader": 1, "writer": 2, "admin": 3}
ORG_ROLE_ORDER: dict[str, int] = {"member": 1, "admin": 2, "owner": 3}


class Organization(BaseModel):
    org_id: str
    slug: str
    name: str
    description: str = ""
    plan_tier: PlanTier = "free"
    member_seat_limit: int = 1
    created_at: str
    created_by: str
    deleted_at: str | None = None


class OrganizationMember(BaseModel):
    org_id: str
    principal_id: str
    org_role: OrgRole
    joined_at: str
    invited_by: str


class LibraryAccessEntry(BaseModel):
    library_id: str
    principal_id: str
    role: LibraryRole
    granted_at: str
    granted_by: str


class ApiKeyGrant(BaseModel):
    key_id: str
    library_id: str
    role: KeyGrantRole


class LibraryGrantSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_id: str
    role: KeyGrantRole

    @field_validator("role")
    @classmethod
    def role_valid(cls, value: str) -> str:
        if value not in ROLE_ORDER:
            raise ValueError("role must be reader, writer, or admin")
        return value


class OrgCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    description: str = ""


class OrgMemberAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_id: str | None = None
    login_name: str | None = None
    org_role: OrgRole = "member"


class LibraryAccessGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: LibraryRole


class IssueV4ApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    expires_at: str | None = None
    library_grants: list[LibraryGrantSpec]
    acknowledge_admin_risk: bool = False


class SessionRecord(BaseModel):
    session_id: str
    principal_id: str
    expires_at: str
    created_at: str
    idp_region: str = "dev"

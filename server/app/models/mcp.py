from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class McpJsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class McpToolDescriptor(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class McpToolResult(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    structuredContent: dict[str, Any] | None = None
    isError: bool = False

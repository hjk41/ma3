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


class McpToolValidationError(Exception):
    """Raised when a tool's arguments fail Pydantic validation.

    Carries the original ValidationError.errors() list so the JSON-RPC layer
    can surface structured field paths in error.data.validation_errors instead
    of flattening the message into a single string.
    """

    def __init__(self, tool_name: str, errors: list[dict[str, Any]], *, message: str | None = None) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(message or f"validation failed for {tool_name}: {errors}")

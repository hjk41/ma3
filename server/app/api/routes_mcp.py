from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.security import _extract_raw
from app.models.mcp import McpJsonRpcRequest, McpToolValidationError
from app.services.mcp_tool_service import (
    call_mcp_tool,
    list_mcp_tools,
    mcp_initialize_result,
    resolve_mcp_auth,
)


router = APIRouter(prefix="/mcp", tags=["remote-mcp"])


def _jsonrpc_result(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: str | int | None, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _http_to_jsonrpc_code(status_code: int) -> int:
    if status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        return -32001
    if status_code == status.HTTP_404_NOT_FOUND:
        return -32601
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return -32029
    return -32000


def _handle_rpc(req: McpJsonRpcRequest, raw_auth: str | None) -> dict[str, Any] | None:
    # JSON-RPC notifications intentionally receive no response.
    if req.id is None:
        return None

    try:
        if req.method == "initialize":
            return _jsonrpc_result(req.id, mcp_initialize_result())
        if req.method == "ping":
            return _jsonrpc_result(req.id, {})
        if req.method == "tools/list":
            return _jsonrpc_result(req.id, {"tools": [t.model_dump(mode="json") for t in list_mcp_tools()]})
        if req.method == "tools/call":
            name = req.params.get("name")
            if not isinstance(name, str) or not name:
                return _jsonrpc_error(req.id, -32602, "Invalid params", {"detail": "tools/call requires params.name"})
            arguments = req.params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return _jsonrpc_error(req.id, -32602, "Invalid params", {"detail": "params.arguments must be an object"})
            auth = resolve_mcp_auth(raw_auth)
            result = call_mcp_tool(name, arguments, auth)
            return _jsonrpc_result(req.id, result.model_dump(mode="json", exclude_none=True))
        return _jsonrpc_error(req.id, -32601, "Method not found", {"method": req.method})
    except McpToolValidationError as exc:
        return _jsonrpc_error(
            req.id,
            -32602,
            "Invalid params",
            {
                "tool_name": exc.tool_name,
                "validation_errors": exc.errors,
                "schema_hint": (
                    f"See tools/list inputSchema for {exc.tool_name}; "
                    "fix each entry in validation_errors[*].loc and retry. "
                    "ma3_validate offers a dry-run check."
                ),
            },
        )
    except HTTPException as exc:
        return _jsonrpc_error(req.id, _http_to_jsonrpc_code(exc.status_code), str(exc.detail), {"status_code": exc.status_code})
    except ValueError as exc:
        return _jsonrpc_error(req.id, -32602, "Invalid params", {"detail": str(exc)})


@router.get("")
def mcp_get() -> Response:
    """MCP Streamable HTTP GET endpoint.

    ma3 does not currently offer an SSE stream, so the MCP transport requires
    HTTP 405 for GET at the MCP endpoint. Use POST /mcp for JSON-RPC and
    GET /mcp/info for human-readable capability discovery.
    """
    return JSONResponse({"detail": "SSE stream is not supported; use POST /mcp"}, status_code=405)


@router.get("/info")
def mcp_info() -> dict[str, Any]:
    return {
        "status": "ok",
        "endpoint": "/mcp",
        "transport": "streamable-http-jsonrpc",
        "methods": ["initialize", "tools/list", "tools/call", "ping"],
        "tools": [t.name for t in list_mcp_tools()],
    }


@router.post("")
async def mcp_post(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> Response:
    raw_auth = _extract_raw(x_api_key, authorization)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_jsonrpc_error(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        responses = []
        for item in body:
            try:
                req = McpJsonRpcRequest.model_validate(item)
            except ValidationError as exc:
                responses.append(_jsonrpc_error(None, -32600, "Invalid Request", exc.errors()))
                continue
            response = _handle_rpc(req, raw_auth)
            if response is not None:
                responses.append(response)
        if not responses:
            return Response(status_code=202)
        return JSONResponse(responses)

    try:
        req = McpJsonRpcRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(_jsonrpc_error(None, -32600, "Invalid Request", exc.errors()), status_code=400)
    response = _handle_rpc(req, raw_auth)
    if response is None:
        return Response(status_code=202)
    return JSONResponse(response)

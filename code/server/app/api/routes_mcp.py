from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.security import (
    RawCredential,
    extract_credential,
    mcp_www_authenticate_header,
    resolve_mcp_auth,
)
from app.models.mcp import McpJsonRpcRequest, McpToolValidationError
from app.services.mcp_tool_service import call_mcp_tool, list_mcp_tools, mcp_initialize_result


router = APIRouter(prefix="/mcp", tags=["remote-mcp"])

# Discovery-only tools permitted without credentials. Knowledge read/write requires a key.
_ANONYMOUS_ALLOWED_TOOLS = frozenset({"ma3_whoami"})


def _jsonrpc_result(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: str | int | None, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _loc_str(loc: Any) -> str:
    if isinstance(loc, (list, tuple)):
        return ".".join(str(p) for p in loc) or "<root>"
    return str(loc)


def _summarize_validation_errors(tool_name: str | None, errors: list[dict[str, Any]]) -> str:
    """Fold pydantic validation errors into a single actionable message.

    MCP hosts only surface ``error.message`` to the model (``error.data`` is
    often dropped), so the message itself must tell the agent exactly which
    fields to fix and how — otherwise it retries the same bad payload blindly.
    """
    missing: list[str] = []
    extra: list[str] = []
    other: list[str] = []
    for err in errors:
        etype = str(err.get("type", ""))
        loc = _loc_str(err.get("loc"))
        if etype in {"missing", "value_error.missing"}:
            missing.append(loc)
        elif etype in {"extra_forbidden", "value_error.extra"}:
            extra.append(loc)
        else:
            other.append(f"{loc}: {err.get('msg', etype)}")

    parts: list[str] = []
    prefix = f"Invalid params for {tool_name}" if tool_name else "Invalid params"
    if missing:
        parts.append(f"missing required field(s): {', '.join(missing)}")
    if extra:
        parts.append(f"unexpected field(s): {', '.join(extra)}")
    if other:
        parts.append("; ".join(other))

    msg = f"{prefix}: " + ("; ".join(parts) if parts else "payload failed schema validation")

    # Very common agent mistake: wrapping a tool payload under `arguments`
    # (the ma3_validate envelope) when the target tool expects a FLAT payload.
    if tool_name and tool_name != "ma3_validate" and "arguments" in extra:
        msg += (
            f". Hint: {tool_name} takes a FLAT payload (the fields directly), "
            "NOT {tool_name, arguments} like ma3_validate. Move the inner fields "
            "up to the top level and retry."
        )
    else:
        msg += ". Fix these fields and retry; ma3_validate offers a dry-run check."
    return msg


def _http_to_jsonrpc_code(status_code: int) -> int:
    if status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        return -32001
    if status_code == status.HTTP_404_NOT_FOUND:
        return -32601
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return -32029
    return -32000


def _http_exception_payload(exc: HTTPException) -> tuple[str, dict[str, Any]]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("error") or "request failed")
        if exc.headers and exc.headers.get("Retry-After"):
            detail = {**detail, "retry_after": exc.headers["Retry-After"]}
        return message, {"status_code": exc.status_code, "detail": detail}
    return str(detail), {"status_code": exc.status_code}


def _response_status(
    response: dict[str, Any] | None,
    *,
    request: Request | None = None,
) -> tuple[int, dict[str, str]]:
    if not response or "error" not in response:
        return 200, {}
    data = response["error"].get("data") or {}
    status_code = int(data.get("status_code") or 200)
    detail = data.get("detail") or {}
    headers: dict[str, str] = {}
    if status_code == 429:
        headers["Retry-After"] = str(detail.get("retry_after") or "60")
        return status_code, headers
    if status_code == 401:
        headers["WWW-Authenticate"] = mcp_www_authenticate_header(request)
        return 401, headers
    # MCP tool errors remain JSON-RPC result envelopes for client compatibility;
    # quota/rate-limit admission is the one P1 case requiring an HTTP 429.
    return 200, headers


def _handle_rpc(
    req: McpJsonRpcRequest,
    raw_auth: RawCredential | None,
    *,
    request: Request | None = None,
) -> dict[str, Any] | None:
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
                return _jsonrpc_error(
                    req.id,
                    -32602,
                    "Invalid params: tools/call requires a string params.name (the tool to call)",
                    {"detail": "tools/call requires params.name"},
                )
            arguments = req.params["arguments"] if "arguments" in req.params else {}
            if not isinstance(arguments, dict):
                return _jsonrpc_error(
                    req.id,
                    -32602,
                    "Invalid params: params.arguments must be a JSON object mapping field names to values",
                    {"detail": "params.arguments must be an object"},
                )
            auth = resolve_mcp_auth(raw_auth, request=request)
            if auth.invalid_credentials:
                return _jsonrpc_error(
                    req.id,
                    -32001,
                    "Invalid credentials: the X-API-Key or MCP OAuth token is unknown, revoked, or expired. "
                    "Check your MCP server API key or complete OAuth login.",
                    {"status_code": 401},
                )
            if auth.principal.kind == "anonymous" and name not in _ANONYMOUS_ALLOWED_TOOLS:
                return _jsonrpc_error(
                    req.id,
                    -32001,
                    "authentication required: set X-API-Key (from /ui/keys/ or self-host bootstrap) "
                    "or complete MCP OAuth to use ma3 tools",
                    {"status_code": 401, "tool_name": name},
                )
            result = call_mcp_tool(name, arguments, auth)
            return _jsonrpc_result(req.id, result.model_dump(mode="json", exclude_none=True))
        return _jsonrpc_error(
            req.id,
            -32601,
            f"Method not found: {req.method!r}. Supported: initialize, tools/list, tools/call, ping",
            {"method": req.method},
        )
    except McpToolValidationError as exc:
        return _jsonrpc_error(
            req.id,
            -32602,
            _summarize_validation_errors(exc.tool_name, exc.errors),
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
        message, data = _http_exception_payload(exc)
        return _jsonrpc_error(req.id, _http_to_jsonrpc_code(exc.status_code), message, data)
    except ValueError as exc:
        return _jsonrpc_error(req.id, -32602, f"Invalid params: {exc}", {"detail": str(exc)})


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
        "connect_url": "/client/connect.md",
        "onboarding_url": "/client/agent-onboarding.md",
    }


@router.post("")
async def mcp_post(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> Response:
    raw_auth = extract_credential(x_api_key, authorization)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            _jsonrpc_error(None, -32700, "Parse error: request body is not valid JSON", None),
            status_code=400,
        )

    if isinstance(body, list):
        responses = []
        for item in body:
            try:
                req = McpJsonRpcRequest.model_validate(item)
            except ValidationError as exc:
                responses.append(
                    _jsonrpc_error(None, -32600, _summarize_validation_errors(None, exc.errors()).replace("Invalid params", "Invalid Request"), exc.errors())
                )
                continue
            response = _handle_rpc(req, raw_auth, request=request)
            if response is not None:
                responses.append(response)
        if not responses:
            return Response(status_code=202)
        return JSONResponse(responses)

    try:
        req = McpJsonRpcRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(
            _jsonrpc_error(None, -32600, _summarize_validation_errors(None, exc.errors()).replace("Invalid params", "Invalid Request"), exc.errors()),
            status_code=400,
        )
    response = _handle_rpc(req, raw_auth, request=request)
    if response is None:
        return Response(status_code=202)
    status_code, headers = _response_status(response, request=request)
    return JSONResponse(response, status_code=status_code, headers=headers)

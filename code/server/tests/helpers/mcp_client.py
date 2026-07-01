from __future__ import annotations

from typing import Any, Protocol


class HttpLike(Protocol):
    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None) -> Any: ...
    def get(self, url: str, *, headers: dict[str, str] | None = None) -> Any: ...


class McpClient:
    """Thin JSON-RPC helper for local TestClient or remote httpx clients."""

    def __init__(
        self,
        client: HttpLike,
        *,
        endpoint: str = "/mcp",
        api_key: str | None = None,
    ) -> None:
        self.client = client
        self.endpoint = endpoint
        self.api_key = api_key
        self._id = 0

    def _headers(self, api_key: str | None) -> dict[str, str]:
        key = self.api_key if api_key is None else api_key
        return {"X-API-Key": key} if key else {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def post_raw(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        rid = self._next_id() if request_id is None else request_id
        response = self.client.post(
            self.endpoint,
            json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}},
            headers=self._headers(api_key),
        )
        body: Any
        try:
            body = response.json()
        except Exception:
            body = {"_raw": response.text}
        return {"status_code": response.status_code, "body": body}

    def rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        expect_error: bool = False,
    ) -> dict[str, Any]:
        payload = self.post_raw(method, params, api_key=api_key)
        assert payload["status_code"] == 200, payload
        body = payload["body"]
        if expect_error:
            assert "error" in body, body
            return body["error"]
        assert "error" not in body, body
        return body["result"]

    def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        expect_error: bool = False,
    ) -> dict[str, Any]:
        return self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            api_key=api_key,
            expect_error=expect_error,
        )

    def structured(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        return self.call(name, arguments, api_key=api_key)["structuredContent"]

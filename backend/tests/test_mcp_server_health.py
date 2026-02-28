"""
Smoke tests for MCP HTTP health and auth behavior.
"""
import os
import sys

from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mcp_server import app  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name == "fastmcp":
        app = None  # type: ignore[assignment]
    else:
        raise


def _require_app() -> None:
    if app is None:
        raise RuntimeError("fastmcp is not installed in this Python environment.")


def _resolve_mcp_route_path() -> str:
    _require_app()
    candidates: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if "mcp" in path:
            candidates.append(path)

    if not candidates:
        raise AssertionError("No MCP transport route found on the MCP app.")

    if "/mcp" in candidates:
        return "/mcp"
    return sorted(candidates, key=len)[0]


def test_health_endpoint_is_public() -> None:
    _require_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "mcp"}
    print("✓ MCP health endpoint is public")


def test_mcp_transport_rejects_unauthenticated_requests() -> None:
    _require_app()
    client = TestClient(app)
    mcp_path = _resolve_mcp_route_path()
    response = client.get(mcp_path)

    assert response.status_code != 200
    assert response.status_code != 404
    print("✓ MCP transport rejects unauthenticated requests")


if __name__ == "__main__":
    if app is None:
        print("Skipping MCP health/auth tests because fastmcp is not installed.")
        raise SystemExit(0)

    test_health_endpoint_is_public()
    test_mcp_transport_rejects_unauthenticated_requests()
    print("All MCP health/auth tests passed.")

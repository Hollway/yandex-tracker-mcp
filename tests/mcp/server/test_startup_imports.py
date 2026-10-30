"""Guard: a server start loads neither aiocache nor redis unless it uses them.

Only `TOOLS_CACHE_ENABLED` and the Redis OAuth store need them, and with them
every start imported about 80 more modules - some 0.4 s of a start that has to
fit Claude Code's connection timeout while a dozen other MCP servers start too.
They are imported where they are used, so these tests also run those two paths,
which nothing else here exercises.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.oauth.provider import YandexOAuthAuthorizationServerProvider
from mcp_tracker.mcp.oauth.stores.redis import RedisOAuthStore
from mcp_tracker.mcp.server import create_mcp_server, make_tracker_lifespan
from mcp_tracker.tracker.custom.client import TrackerClient
from tests.mcp.conftest import create_test_settings

LAZY_MODULES = ["aiocache", "redis"]

# Imports the server the way `python -m mcp_tracker` does and prints which of
# the modules given as its argument got loaded.
_PROBE = (
    "import json, sys; import mcp_tracker.__main__; "
    "print(json.dumps(sorted(set(sys.modules) & set(json.loads(sys.argv[1])))))"
)


def test_server_start_loads_neither_aiocache_nor_redis(tmp_path: Path) -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("TRACKER_", "TOOLS_CACHE_", "OAUTH_"))
    }
    env |= {"TRACKER_TOKEN": "test-token", "TRACKER_ORG_ID": "test-org"}

    # A fresh interpreter, from a directory without a `.env`: the test process
    # has long imported both modules itself.
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(LAZY_MODULES)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    assert json.loads(result.stdout) == []


async def test_tools_cache_wraps_the_protocols() -> None:
    settings = create_test_settings().model_copy(update={"tools_cache_enabled": True})

    lifespan = make_tracker_lifespan(settings)
    async with lifespan(Mock(spec=MCPServer)) as context:
        assert isinstance(context, AppContext)
        assert not isinstance(context.issues, TrackerClient)


def test_redis_oauth_store_is_built() -> None:
    settings = create_test_settings().model_copy(
        update={
            "oauth_enabled": True,
            "oauth_store": "redis",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "mcp_server_public_url": AnyHttpUrl("https://mcp.example.com"),
            "oauth_encryption_keys": base64.b64encode(bytes(32)).decode(),
        }
    )

    server = create_mcp_server(settings)

    provider = server._auth_server_provider
    assert isinstance(provider, YandexOAuthAuthorizationServerProvider)
    assert isinstance(provider._store, RedisOAuthStore)

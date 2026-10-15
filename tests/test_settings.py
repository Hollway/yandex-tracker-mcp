"""`Settings` refuses a configuration that would expose the host's files.

`issue_add_attachment` uploads any file the server process can read, by a path the
client picks. That is the user's own machine over stdio, and anyone who can reach
the server - or a prompt injected into issue text - on a networked one.
`issue_download_attachment` writes to the server's disk and returns a path only a
local client can open, so it is held to the same rule.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mcp_tracker.settings import Settings

ENV_PREFIXES = ("TRACKER_", "OAUTH_", "MCP_", "TRANSPORT", "TOOLS_CACHE_")

# What OAuth mode needs to load at all, so that the file upload check is what fails.
OAUTH_SETTINGS: dict[str, Any] = {
    "oauth_enabled": True,
    "oauth_client_id": "client-id",
    "oauth_client_secret": "client-secret",
    "mcp_server_public_url": "https://mcp.example.com",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own environment and `.env` out of what these tests load."""
    monkeypatch.chdir(tmp_path)
    for name in [name for name in os.environ if name.startswith(ENV_PREFIXES)]:
        monkeypatch.delenv(name)


def load_settings(**overrides: Any) -> Settings:
    return Settings(
        tracker_token="test-token",
        tracker_org_id="test-org",
        **overrides,
    )


# The flags that let a tool touch the server's disk: (environment variable, field).
LOCAL_FILE_FLAGS = [
    pytest.param(
        "TRACKER_FILE_UPLOAD_ENABLED", "tracker_file_upload_enabled", id="upload"
    ),
    pytest.param(
        "TRACKER_ATTACHMENT_DOWNLOAD_ENABLED",
        "tracker_attachment_download_enabled",
        id="download",
    ),
]


class TestAttachmentDefaults:
    @pytest.mark.parametrize(("env_name", "field"), LOCAL_FILE_FLAGS)
    def test_flag_is_off_by_default(self, env_name: str, field: str) -> None:
        assert getattr(load_settings(), field) is False

    def test_attachment_timeout_has_its_own_default(self) -> None:
        settings = load_settings()

        assert settings.tracker_attachment_timeout == 300
        assert settings.tracker_attachment_timeout > settings.tracker_api_timeout

    def test_download_size_limit_defaults_to_50_mib(self) -> None:
        assert load_settings().tracker_max_attachment_bytes == 50 * 1024 * 1024

    def test_downloads_go_to_the_system_temp_directory_by_default(self) -> None:
        assert load_settings().attachments_dir == (
            Path(tempfile.gettempdir()) / "yandex-tracker-mcp" / "attachments"
        )

    def test_downloads_directory_can_be_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("TRACKER_ATTACHMENTS_DIR", str(tmp_path / "files"))

        assert load_settings().attachments_dir == (tmp_path / "files").resolve()


class TestLocalFileTransportGuard:
    @pytest.mark.parametrize(("env_name", "field"), LOCAL_FILE_FLAGS)
    def test_accepted_on_stdio(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str, field: str
    ) -> None:
        monkeypatch.setenv(env_name, "true")

        settings = load_settings()

        assert settings.transport == "stdio"
        assert getattr(settings, field) is True

    @pytest.mark.parametrize(("env_name", "field"), LOCAL_FILE_FLAGS)
    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    def test_rejected_on_a_network_transport(
        self,
        monkeypatch: pytest.MonkeyPatch,
        transport: str,
        env_name: str,
        field: str,
    ) -> None:
        monkeypatch.setenv(env_name, "true")
        monkeypatch.setenv("TRANSPORT", transport)

        with pytest.raises(ValidationError) as exc_info:
            load_settings()

        message = str(exc_info.value)
        assert env_name in message
        assert f"TRANSPORT={transport}" in message

    @pytest.mark.parametrize(("env_name", "field"), LOCAL_FILE_FLAGS)
    def test_rejected_in_oauth_mode(self, env_name: str, field: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            load_settings(**{field: True}, **OAUTH_SETTINGS)

        message = str(exc_info.value)
        assert env_name in message
        assert "OAUTH_ENABLED=true" in message

    def test_both_flags_are_named_when_both_are_on(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            load_settings(
                transport="sse",
                tracker_file_upload_enabled=True,
                tracker_attachment_download_enabled=True,
            )

        message = str(exc_info.value)
        assert "TRACKER_FILE_UPLOAD_ENABLED=true and " in message
        assert "TRACKER_ATTACHMENT_DOWNLOAD_ENABLED=true are only allowed" in message

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"transport": "streamable-http"}, id="network-transport"),
            pytest.param(OAUTH_SETTINGS, id="oauth"),
        ],
    )
    def test_remote_servers_load_without_the_flags(
        self, overrides: dict[str, Any]
    ) -> None:
        settings = load_settings(**overrides)

        assert settings.tracker_file_upload_enabled is False
        assert settings.tracker_attachment_download_enabled is False

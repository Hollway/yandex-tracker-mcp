from unittest.mock import AsyncMock

from mcp.client.session import ClientSession

from mcp_tracker.tracker.proto.types.issues import ExternalApplication
from tests.mcp.conftest import get_tool_result_content


class TestApplicationsGetAll:
    async def test_returns_applications(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        mock_issues_protocol.applications_list.return_value = [
            ExternalApplication(id="ru.yandex.bitbucket", name="Bitbucket")
        ]

        result = await client_session.call_tool("applications_get_all", {})

        assert not result.isError
        assert get_tool_result_content(result)[0]["id"] == "ru.yandex.bitbucket"

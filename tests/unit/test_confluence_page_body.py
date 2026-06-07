"""Unit tests for Confluence page body fetch (storage format)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from confluence_sync.confluence_sync import ConfluenceSync


@pytest.fixture
def client() -> ConfluenceSync:
    return ConfluenceSync(
        "https://example.atlassian.net",
        "user@example.com",
        "token",
        "TEST",
        space_id="space-1",
    )


def test_get_page_with_body_uses_storage_format(client: ConfluenceSync) -> None:
    response = MagicMock()
    response.json.return_value = {
        "id": "42",
        "body": {"storage": {"value": "<p>Hello</p>"}},
    }
    with patch.object(client, "_make_request", return_value=response) as mock_request:
        data = client._get_page("42", include_body=True)

    mock_request.assert_called_once_with("GET", "/pages/42", params={"body-format": "storage"})
    assert ConfluenceSync._page_storage_body(data) == "<p>Hello</p>"


def test_get_page_without_body_omits_params(client: ConfluenceSync) -> None:
    response = MagicMock()
    response.json.return_value = {"id": "42", "title": "Page"}
    with patch.object(client, "_make_request", return_value=response) as mock_request:
        client._get_page("42", include_body=False)

    mock_request.assert_called_once_with("GET", "/pages/42", params=None)


def test_page_storage_body_fallback_value(client: ConfluenceSync) -> None:
    data = {"body": {"value": "<p>legacy</p>"}}
    assert ConfluenceSync._page_storage_body(data) == "<p>legacy</p>"

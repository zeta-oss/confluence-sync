"""Unit tests for XML escaping and heading anchor generation — ported from legacy tests."""

from __future__ import annotations

import pytest

from confluence_sync.content_preparer import ContentPreparer, escape_title_for_confluence, escape_xml

# ---------------------------------------------------------------------------
# escape_xml
# ---------------------------------------------------------------------------


def test_escape_ampersand():
    assert escape_xml("A & B") == "A &amp; B"


def test_escape_angle_brackets():
    assert escape_xml("<code>test</code>") == "&lt;code&gt;test&lt;/code&gt;"


def test_escape_quotes():
    result = escape_xml('He said "Hello"')
    assert "&quot;" in result


def test_escape_already_escaped():
    assert escape_xml("&amp;") == "&amp;amp;"


# ---------------------------------------------------------------------------
# escape_title_for_confluence
# ---------------------------------------------------------------------------


def test_escape_title_escapes_angle_brackets():
    """escape_title_for_confluence escapes XML special chars."""
    result = escape_title_for_confluence("Title > < &")
    assert "&gt;" in result or ">" not in result
    assert "&lt;" in result or "<" not in result


# ---------------------------------------------------------------------------
# Anchor generation
# ---------------------------------------------------------------------------


@pytest.fixture()
def preparer(tmp_path):
    return ContentPreparer(repo_root=tmp_path)


def test_anchor_from_simple_heading(preparer):
    html = "<h1>Introduction</h1>"
    result = preparer._add_anchors_to_headings(html)
    # Uses HTML id= attribute (Fabric-safe, not ac:structured-macro)
    assert 'id="introduction"' in result


def test_anchor_converts_spaces_to_dashes(preparer):
    html = "<h2>Getting Started</h2>"
    result = preparer._add_anchors_to_headings(html)
    assert "getting-started" in result.lower()


def test_anchor_strips_special_chars(preparer):
    html = "<h1>Test &amp; More!</h1>"
    result = preparer._add_anchors_to_headings(html)
    # Special chars stripped from id= slug
    import re
    id_match = re.search(r'id="([^"]*)"', result)
    assert id_match is not None
    assert "!" not in id_match.group(1)


def test_anchor_preserves_heading_content(preparer):
    html = "<h1>Title Case Heading</h1>"
    result = preparer._add_anchors_to_headings(html)
    assert "Title Case Heading" in result

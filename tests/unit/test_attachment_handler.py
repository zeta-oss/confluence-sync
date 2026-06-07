"""
Unit tests for attachment_handler.py — ported from test_attachment_handler.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from confluence_sync.attachment_handler import AttachmentHandler


class TestFindImagesInMarkdown:
    def setup_method(self):
        self.mock_confluence = Mock()
        self.handler = AttachmentHandler(self.mock_confluence)

    def test_ignore_remote_images(self):
        content = "![Remote](https://example.com/img.jpg)"
        images = self.handler.find_images_in_markdown(content, Path("/tmp/test.md"))
        assert len(images) == 0

    def test_ignore_data_urls(self):
        content = "![Data](data:image/png;base64,iVBORw0KGgo=)"
        images = self.handler.find_images_in_markdown(content, Path("/tmp/test.md"))
        assert len(images) == 0

    def test_local_image_resolved(self, tmp_path):
        img = tmp_path / "image.png"
        img.write_bytes(b"\x89PNG")
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        images = self.handler.find_images_in_markdown(content, md_file)
        assert len(images) == 1
        assert images[0] == img


class TestConvertImageReferences:
    def setup_method(self):
        self.mock_confluence = Mock()
        self.handler = AttachmentHandler(self.mock_confluence)

    def test_converts_img_to_confluence_macro(self):
        html = '<img src="test.png" alt="Test Image">'
        page_id = "123"
        self.handler.page_attachments[page_id] = ["test.png"]
        result = self.handler.convert_image_references(html, page_id)
        assert "ac:image" in result
        assert "ri:attachment" in result
        assert "test.png" in result

    def test_remote_img_not_converted(self):
        html = '<img src="https://example.com/img.png" alt="Remote">'
        result = self.handler.convert_image_references(html, "123")
        assert "https://example.com/img.png" in result
        assert "ac:image" not in result

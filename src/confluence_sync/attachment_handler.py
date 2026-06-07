"""
Attachment Handler Module - Handles image uploads and reference conversion.

This module detects local image references in Markdown, uploads them as
Confluence attachments, and converts image references to Confluence image macros.
"""

import io
import re
from pathlib import Path
from typing import Dict, List, Optional

from confluence_sync.confluence_sync import ConfluenceSync


def _guess_mime_type(filename: str) -> str:
    """Best-effort MIME type for multipart upload (Confluence may validate PNG/JPEG)."""
    lower = filename.lower()
    if lower.endswith('.png'):
        return 'image/png'
    if lower.endswith(('.jpg', '.jpeg')):
        return 'image/jpeg'
    if lower.endswith('.gif'):
        return 'image/gif'
    if lower.endswith('.webp'):
        return 'image/webp'
    if lower.endswith('.svg'):
        return 'image/svg+xml'
    return 'application/octet-stream'


def _log_attachment_error(response, filename: str, page_id: str) -> None:
    """Print response body to help debug 4xx attachment failures."""
    body = ''
    try:
        body = (response.text or '')[:2000]
    except Exception:
        pass
    print(f"  ⚠ Attachment API {response.status_code} for {filename!r} (page {page_id}): {body or '(no body)'}")


class AttachmentHandler:
    """Handles attachment uploads and image reference conversion."""

    def __init__(self, confluence_sync: ConfluenceSync):
        """
        Initialize attachment handler.

        Args:
            confluence_sync: ConfluenceSync instance for API calls
        """
        self.confluence = confluence_sync
        self.uploaded: Dict[str, str] = {}  # local_path -> attachment_name
        self.page_attachments: Dict[str, List[str]] = {}  # page_id -> list of attachment names

    def find_images_in_markdown(self, content: str, base_path: Path) -> List[Path]:
        """
        Find all local image references in Markdown content.

        Args:
            content: Markdown content
            base_path: Base path for resolving relative image paths

        Returns:
            List of absolute paths to image files
        """
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = []

        for match in re.finditer(pattern, content):
            img_path = match.group(2)

            # Skip remote URLs and data URLs
            if img_path.startswith(('http://', 'https://', 'data:')):
                continue

            # Resolve relative path
            if img_path.startswith('/'):
                full_path = base_path.parent / img_path.lstrip('/')
            elif img_path.startswith('./'):
                full_path = base_path.parent / img_path[2:]
            elif img_path.startswith('../'):
                full_path = base_path.parent / img_path
            else:
                full_path = base_path.parent / img_path

            try:
                full_path = full_path.resolve()
                if full_path.exists() and full_path.is_file():
                    images.append(full_path)
            except (ValueError, OSError):
                # Path resolution failed or file doesn't exist
                pass

        return images

    def upload_attachment(self, page_id: str, file_path: Path) -> Optional[str]:
        """
        Upload file as attachment to page.

        Args:
            page_id: Confluence page ID
            file_path: Path to file to upload

        Returns:
            Attachment name if successful, None otherwise
        """
        if not file_path.exists():
            return None

        attachment_name = file_path.name

        # Check if already uploaded to this page
        if page_id in self.page_attachments and attachment_name in self.page_attachments[page_id]:
            return attachment_name

        try:
            # Legacy REST: use PUT (create-or-update). POST only creates; duplicate filename → 400.
            # See https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content---attachments/
            import requests
            url = f"{self.confluence.base_url}/rest/api/content/{page_id}/child/attachment"
            headers = {
                'X-Atlassian-Token': 'no-check'  # Required for file uploads
            }
            mime = _guess_mime_type(attachment_name)

            with open(file_path, 'rb') as f:
                files = {
                    'file': (attachment_name, f, mime)
                }
                data = {
                    'comment': 'Uploaded by Confluence Sync'
                }

                response = requests.request(
                    'PUT',
                    url,
                    auth=self.confluence.auth,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60
                )
                if not response.ok:
                    _log_attachment_error(response, attachment_name, page_id)
                response.raise_for_status()

                # Track uploaded attachment
                if page_id not in self.page_attachments:
                    self.page_attachments[page_id] = []
                self.page_attachments[page_id].append(attachment_name)
                self.uploaded[str(file_path)] = attachment_name

                return attachment_name
        except Exception as e:
            print(f"  ⚠ Warning: Could not upload attachment {file_path.name}: {e}")
            return None

    def upload_attachment_from_bytes(
        self, page_id: str, filename: str, data: bytes
    ) -> Optional[str]:
        """
        Upload bytes as attachment to page (e.g. Mermaid-rendered PNG).

        Args:
            page_id: Confluence page ID
            filename: Attachment filename (e.g. mermaid-0.png)
            data: Raw file bytes

        Returns:
            Attachment name if successful, None otherwise
        """
        if page_id in self.page_attachments and filename in self.page_attachments[page_id]:
            return filename
        try:
            import requests
            url = f"{self.confluence.base_url}/rest/api/content/{page_id}/child/attachment"
            headers = {'X-Atlassian-Token': 'no-check'}
            mime = _guess_mime_type(filename)
            files = {'file': (filename, io.BytesIO(data), mime)}
            data_payload = {'comment': 'Uploaded by Confluence Sync (Mermaid diagram)'}
            response = requests.request(
                'PUT', url, auth=self.confluence.auth, headers=headers,
                files=files, data=data_payload, timeout=60
            )
            if not response.ok:
                _log_attachment_error(response, filename, page_id)
            response.raise_for_status()
            if page_id not in self.page_attachments:
                self.page_attachments[page_id] = []
            self.page_attachments[page_id].append(filename)
            return filename
        except Exception as e:
            print(f"  ⚠ Warning: Could not upload attachment {filename}: {e}")
            return None

    def convert_image_references(self, html: str, page_id: str) -> str:
        """
        Convert image tags to Confluence attachment references.

        Args:
            html: HTML content with image tags
            page_id: Confluence page ID (for attachment reference)

        Returns:
            HTML with image tags converted to Confluence image macros
        """
        def replace_image(match):
            img_tag = match.group(0)
            src = match.group(1)
            alt = match.group(2) if match.group(2) else ''

            # Skip remote URLs and data URLs
            if src.startswith(('http://', 'https://', 'data:')):
                return img_tag

            # Extract filename from path
            filename = Path(src).name

            # Check if this attachment was uploaded to this page
            if page_id in self.page_attachments and filename in self.page_attachments[page_id]:
                # Convert to Confluence image macro
                escaped_alt = escape_xml(alt) if alt else ''
                return f'<ac:image ac:align="left" ac:border="false" ac:title="{escaped_alt}"><ri:attachment ri:filename="{escape_xml(filename)}"/></ac:image>'

            # Not uploaded or not found - return original
            return img_tag

        # Match <img src="..." alt="..."> tags
        pattern = r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>'
        return re.sub(pattern, replace_image, html, flags=re.IGNORECASE)


def escape_xml(text: str) -> str:
    """Escape special characters for XML (helper function)."""
    replacements = [
        ('&', '&amp;'),
        ('<', '&lt;'),
        ('>', '&gt;'),
        ('"', '&quot;'),
        ("'", '&apos;'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text

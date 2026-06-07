#!/usr/bin/env python3
"""
Content Preparer Module - Phase 1 of Confluence Sync

This module handles preparing all Markdown content for Confluence sync.
It performs all local file processing, content conversion, and metadata
extraction WITHOUT making any API calls to Confluence.

Clear boundaries:
- Input: Markdown files, sync state, configuration
- Output: List of PreparedContent objects ready for syncing
- No dependencies on Confluence API
- Fully testable without network access
"""

import hashlib
import re
import struct
import subprocess
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from typing import Any, Dict, List, Optional, Tuple

try:
    import markdown
except ImportError:
    raise ImportError("'markdown' library not found. Install with: pip install markdown")

from html import escape as html_escape

from confluence_sync.git_utils import get_file_commit_date, get_file_commit_hash, get_file_github_url
from confluence_sync.ignore_handler import IgnoreHandler
from confluence_sync.sync_state import compute_content_hash, compute_content_signature
from confluence_sync.title_mapping import get_title_mapping_loader

# Optional: Python mmdc package for Mermaid → PNG (pip install mmdc)
try:
    from mmdc import MermaidConverter as _MermaidConverter
except ImportError:
    _MermaidConverter = None

# Printed once per process when pip mmdc yields an effectively blank PNG (PhantomJS stack).
_MERMAID_PHANTOM_BLANK_HINT_PRINTED = False


def escape_xml(text: str) -> str:
    """Escape special characters for XML/HTML."""
    if text is None:
        return ''
    return html_escape(str(text), quote=True)


def escape_title_for_confluence(title: str) -> str:
    """Escape a page title for use in Confluence storage format."""
    if title is None:
        return ''
    # Escape XML special characters
    escaped = escape_xml(title)
    return escaped


def _numeric_prefix_and_rest(stem: str) -> Optional[Tuple[str, str]]:
    """If stem matches NN-separator-rest (e.g. 00-prologue, 01_intro), return (prefix, rest). Else None."""
    m = re.match(r'^(\d+)[-_\s]+(.*)$', stem)
    if m and m.group(2).strip():
        return (m.group(1), m.group(2).strip())
    return None


def _natural_sort_key_for_md(path: Path) -> Tuple[int, str]:
    """Sort key for markdown files: numeric prefix first (0,1,2,...,10), then rest. Non-prefixed files last."""
    stem = path.stem
    parsed = _numeric_prefix_and_rest(stem)
    if parsed:
        return (int(parsed[0]), parsed[1].lower())
    return (999999, stem.lower())


@dataclass
class PreparedContent:
    """Represents content prepared for syncing to Confluence."""
    file_path: str
    rel_path: str
    source_folder: Optional[str]
    title: str
    content: str  # Markdown content
    storage_format: str  # Confluence storage format
    content_hash: str
    content_signature: str  # For rename detection
    parent_id: Optional[str]
    commit_hash: Optional[str]
    commit_date: Optional[str]
    github_url: Optional[str]
    file_key: str
    prev_history: Optional[Dict[str, Any]]
    force_sync: bool
    existing_page_id: Optional[str] = None
    status: str = 'pending'  # 'pending', 'syncing', 'synced', 'failed', 'skipped'
    page_id: Optional[str] = None
    sync_status: Optional[str] = None  # 'created', 'updated', 'skipped'
    version: Optional[int] = None
    sync_result: Optional[Any] = None  # Will be SyncResult
    error: Optional[str] = None
    renamed_from: Optional[str] = None  # Old path if this is a renamed file
    image_paths: List[Path] = field(default_factory=list)  # List of image file paths to upload as attachments
    mermaid_attachments: List[Tuple[str, bytes]] = field(default_factory=list)  # (filename, png_bytes) for Mermaid diagrams
    legacy_title: Optional[str] = None  # Previous title (without numeric prefix) for cleanup of old-format pages


class ContentPreparer:
    """
    Prepares Markdown content for Confluence sync.

    This class handles all local file processing and content conversion:
    - Scans directory structure and finds Markdown files
    - Converts Markdown to Confluence Storage Format
    - Converts ```mermaid code blocks to PNG images only (Fabric-safe; no mermaid macro)
    - Builds link resolution cache for cross-references
    - Applies title mappings from .confluence-mapping.yaml files
    - Extracts Git metadata (commit hash, GitHub URLs)

    It does NOT make any API calls to Confluence.
    All API interactions are handled by ConfluenceSync class.
    """

    def __init__(
        self,
        repo_root: Path,
        github_repo_url: Optional[str] = None,
        add_git_metadata: bool = False,
        file_to_title: Optional[Dict[str, str]] = None,
        file_to_page_id: Optional[Dict[str, str]] = None,
        attachment_handler: Optional[Any] = None,
        confluence_base_url: Optional[str] = None,
        mermaid_cache_dir: Optional[Path] = None,
    ):
        """
        Initialize content preparer.

        Args:
            repo_root: Repository root directory
            github_repo_url: GitHub repository URL for metadata
            add_git_metadata: Whether to add Git metadata
            file_to_title: Cache of file paths to page titles (for link conversion)
            file_to_page_id: Cache of file paths to page IDs (for link conversion - more reliable than titles)
            attachment_handler: Optional AttachmentHandler instance for image uploads
            confluence_base_url: Optional Confluence wiki base URL (e.g. https://site.atlassian.net/wiki).
                When set, internal links use plain <a href="..."> for Fabric compatibility instead of ac:link.
            mermaid_cache_dir: If set, rendered Mermaid PNGs are read/written here (SHA-256 of diagram
                source → ``<hex>.png``). Speeds re-sync and keeps binaries on disk for inspection.
        """
        self.repo_root = repo_root
        self.github_repo_url = github_repo_url
        self.add_git_metadata = add_git_metadata
        self.file_to_title = file_to_title or {}
        self.file_to_page_id = file_to_page_id or {}
        self.ignore_handler: Optional[IgnoreHandler] = None
        self.attachment_handler = attachment_handler
        self.confluence_base_url = (confluence_base_url or "").rstrip("/")
        self.mermaid_cache_dir = Path(mermaid_cache_dir).resolve() if mermaid_cache_dir else None

    def markdown_to_storage_format(
        self,
        markdown_content: str,
        current_file_path: Path,
        root_path: Path,
        commit_hash: Optional[str] = None
    ) -> str:
        """
        Convert Markdown to Confluence Storage Format.

        Args:
            markdown_content: Markdown content to convert
            current_file_path: Path to current file (for link conversion)
            root_path: Root path (for link conversion)
            commit_hash: Optional commit hash for Git metadata

        Returns:
            Tuple of (storage_format, mermaid_attachments). When PNG is rendered,
            bodies reference attachments (``mermaid-N.png``); bytes are listed in
            ``mermaid_attachments`` for upload. When PNG is unavailable, a placeholder paragraph is emitted.
        """
        # Extract Mermaid blocks before conversion (codehilite strips language and wraps in spans,
        # so post-processing would not see language-mermaid on <code>)
        markdown_content, mermaid_blocks = self._extract_mermaid_blocks(markdown_content)

        # Convert Markdown to HTML first
        md = markdown.Markdown(
            extensions=[
                'codehilite',
                'tables',
                'fenced_code',
                'nl2br',
                'sane_lists'
            ]
        )
        html = md.convert(markdown_content)

        # Replace Mermaid placeholders (image macro + attachments when PNG available)
        html, mermaid_attachments = self._replace_mermaid_placeholders(
            html, mermaid_blocks, source_file=current_file_path
        )

        # Add anchor macros to headings for deep linking
        html = self._add_anchors_to_headings(html)

        # Convert HTML links to Confluence page links
        if current_file_path and root_path:
            html = self.convert_html_links_to_confluence(html, current_file_path, root_path)

        # Add Git metadata if enabled
        if self.add_git_metadata:
            html = self._add_git_metadata(html, current_file_path, commit_hash)

        # Convert HTML to Confluence Storage Format
        storage_format = self._html_to_storage_format(html)

        return storage_format, mermaid_attachments

    def _add_anchors_to_headings(self, html: str) -> str:
        """
        Add heading IDs for deep linking. Uses HTML id on the heading element
        (Fabric-editor safe); avoids ac:structured-macro "anchor" which Fabric
        does not support.
        """
        def add_anchor(match):
            tag = match.group(1)
            content = match.group(2)
            import html as html_module
            text_content = html_module.unescape(re.sub(r'<[^>]+>', '', content))
            slug = re.sub(r'[^\w\s-]', '', text_content.lower())
            slug = re.sub(r'[\s_]+', '-', slug).strip('-')
            if len(slug) > 50:
                slug = slug[:50].rstrip('-')
            if not slug:
                slug = 'heading'
            return f'<{tag} id="{escape_xml(slug)}">{content}</{tag}>'

        return re.sub(r'<(h[1-6])>([^<]+)</\1>', add_anchor, html)

    def _extract_mermaid_blocks(self, markdown_content: str) -> tuple:
        """
        Extract ```mermaid ... ``` blocks from markdown and replace with placeholders.
        Returns (modified_markdown, list_of_mermaid_sources).
        Needed because codehilite wraps code in spans and drops the language class,
        so we cannot reliably detect mermaid blocks in the HTML after conversion.
        """
        mermaid_blocks: List[str] = []
        placeholder = '<!-- MERMAID_PLACEHOLDER_{} -->'

        def replace(match):
            body = match.group(1).strip()
            idx = len(mermaid_blocks)
            mermaid_blocks.append(body)
            return '\n\n' + placeholder.format(idx) + '\n\n'

        # Match ```mermaid (optional space/newline) then content until ```
        pattern = re.compile(r'(?ms)^```mermaid\s*\n(.*?)```\s*$')
        modified = pattern.sub(replace, markdown_content)
        return modified, mermaid_blocks

    _PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

    @staticmethod
    def _paeth_predictor(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    @classmethod
    def _png_visible_ink_metrics(cls, png_bytes: bytes) -> Optional[Tuple[int, int]]:
        """
        Count pixels that are likely diagram ink (not white/near-white background).
        Returns (ink_pixel_count, total_pixels) or None if PNG is unsupported (e.g. interlaced).
        Used to reject blank outputs from the legacy pip ``mmdc`` (PhantomJS) renderer.
        """
        if not png_bytes or len(png_bytes) < 32 or not png_bytes.startswith(cls._PNG_MAGIC):
            return None
        pos = 8
        width = height = 0
        bit_depth = 0
        color_type = 0
        interlace = 0
        idat_parts: List[bytes] = []
        try:
            while pos + 8 <= len(png_bytes):
                length = struct.unpack('>I', png_bytes[pos : pos + 4])[0]
                ctype = png_bytes[pos + 4 : pos + 8]
                chunk = png_bytes[pos + 8 : pos + 8 + length]
                pos += 12 + length
                if ctype == b'IHDR':
                    width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                        '>IIBBBBB', chunk
                    )
                elif ctype == b'IDAT':
                    idat_parts.append(chunk)
                elif ctype == b'IEND':
                    break
        except (struct.error, IndexError):
            return None
        if interlace != 0 or bit_depth != 8 or width <= 0 or height <= 0:
            return None
        if color_type == 6:
            bpp = 4
        elif color_type == 2:
            bpp = 3
        else:
            return None
        try:
            raw = zlib.decompress(b''.join(idat_parts))
        except zlib.error:
            return None
        stride = width * bpp
        expected_len = height * (1 + stride)
        if len(raw) < expected_len:
            return None
        ink = 0
        total = width * height
        i = 0
        prev = bytearray(stride)
        for _y in range(height):
            if i >= len(raw):
                return None
            filt = raw[i]
            i += 1
            row = bytearray(raw[i : i + stride])
            i += stride
            if len(row) != stride:
                return None
            if filt == 1:  # Sub
                for x in range(stride):
                    left = row[x - bpp] if x >= bpp else 0
                    row[x] = (row[x] + left) & 0xFF
            elif filt == 2:  # Up
                for x in range(stride):
                    row[x] = (row[x] + prev[x]) & 0xFF
            elif filt == 3:  # Average
                for x in range(stride):
                    left = row[x - bpp] if x >= bpp else 0
                    row[x] = (row[x] + ((left + prev[x]) // 2)) & 0xFF
            elif filt == 4:  # Paeth
                for x in range(stride):
                    a = row[x - bpp] if x >= bpp else 0
                    b = prev[x]
                    c = prev[x - bpp] if x >= bpp else 0
                    row[x] = (row[x] + cls._paeth_predictor(a, b, c)) & 0xFF
            elif filt != 0:
                return None
            prev = row
            if color_type == 6:
                for x in range(0, stride, 4):
                    r, g, b, a = row[x], row[x + 1], row[x + 2], row[x + 3]
                    if a < 200:
                        continue
                    if max(abs(r - 255), abs(g - 255), abs(b - 255)) > 18:
                        ink += 1
            else:
                for x in range(0, stride, 3):
                    r, g, b = row[x], row[x + 1], row[x + 2]
                    if max(abs(r - 255), abs(g - 255), abs(b - 255)) > 18:
                        ink += 1
        return ink, total

    @classmethod
    def _mermaid_png_has_visible_diagram(cls, png_bytes: bytes) -> bool:
        m = cls._png_visible_ink_metrics(png_bytes)
        if m is None:
            return True
        ink, total = m
        need = max(45, total // 2500)
        return ink >= need

    def _mermaid_cache_file(self, diagram_code: str) -> Optional[Path]:
        """Content-addressed cache path for a diagram, or None if caching disabled."""
        if not self.mermaid_cache_dir:
            return None
        digest = hashlib.sha256(diagram_code.encode('utf-8')).hexdigest()
        return self.mermaid_cache_dir / f'{digest}.png'

    @staticmethod
    def _write_png_cache_atomic(cache_file: Path, png_bytes: bytes) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix('.png.tmp')
        tmp.write_bytes(png_bytes)
        tmp.replace(cache_file)

    def _mermaid_cli_invocations(self) -> List[List[str]]:
        """Return argv prefixes to try: global ``mmdc``, then ``npx @mermaid-js/mermaid-cli``."""
        invocations: List[List[str]] = []
        mmdc_cmd = which('mmdc')
        if mmdc_cmd:
            invocations.append([mmdc_cmd])
        npx_cmd = which('npx')
        if npx_cmd:
            invocations.append([npx_cmd, '-y', '@mermaid-js/mermaid-cli'])
        return invocations

    def _render_mermaid_via_cli(self, diagram_code: str) -> Optional[bytes]:
        """@mermaid-js/mermaid-cli: modern Mermaid (global ``mmdc`` or ``npx -y``)."""
        prefixes = self._mermaid_cli_invocations()
        if not prefixes:
            return None
        try:
            with tempfile.TemporaryDirectory(prefix='mermaid_sync_') as tmpdir:
                tmp = Path(tmpdir)
                mmd_file = tmp / 'diagram.mmd'
                png_file = tmp / 'diagram.png'
                mmd_file.write_text(diagram_code, encoding='utf-8')
                # Larger viewport + scale → sharper PNGs in Confluence (default CLI is 800×600 @1×).
                args_tail = [
                    '-i',
                    str(mmd_file),
                    '-o',
                    str(png_file),
                    '-b',
                    'white',
                    '-w',
                    '2400',
                    '-H',
                    '1800',
                    '-s',
                    '2',
                ]
                for prefix in prefixes:
                    result = subprocess.run(
                        prefix + args_tail,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(tmp),
                    )
                    if result.returncode == 0 and png_file.exists():
                        data = png_file.read_bytes()
                        if data:
                            return data
        except (subprocess.TimeoutExpired, OSError, Exception):
            return None
        return None

    def _render_mermaid_via_python_package(self, diagram_code: str) -> Optional[bytes]:
        """pip ``mmdc`` (PhantomJS). Often emits empty/white PNGs for modern Mermaid syntax."""
        if _MermaidConverter is None:
            return None
        try:
            converter = _MermaidConverter()
            png_bytes = converter.to_png(diagram_code)
            return png_bytes if png_bytes else None
        except Exception:
            return None

    def _render_mermaid_to_png(self, diagram_code: str) -> Optional[bytes]:
        """
        Render Mermaid diagram to PNG.

        Order: (1) Node ``mmdc`` (@mermaid-js/mermaid-cli) on PATH — recommended.
        (2) pip ``mmdc`` (PhantomJS) — legacy; often produces blank PNGs; rejected if no visible ink.

        When ``mermaid_cache_dir`` is set, caches only plausible PNGs.
        """
        global _MERMAID_PHANTOM_BLANK_HINT_PRINTED

        if not diagram_code.strip():
            return None
        cache_file = self._mermaid_cache_file(diagram_code)
        if cache_file is not None and cache_file.exists():
            try:
                cached = cache_file.read_bytes()
                if (
                    len(cached) >= 8
                    and cached.startswith(self._PNG_MAGIC)
                    and self._mermaid_png_has_visible_diagram(cached)
                ):
                    return cached
                if len(cached) >= 8 and cached.startswith(self._PNG_MAGIC):
                    cache_file.unlink(missing_ok=True)
            except OSError:
                pass

        png_bytes: Optional[bytes] = None

        # 1) Prefer official mermaid-cli (Puppeteer / current Mermaid)
        candidate = self._render_mermaid_via_cli(diagram_code)
        if candidate and self._mermaid_png_has_visible_diagram(candidate):
            png_bytes = candidate

        # 2) pip mmdc — keep only if pixels suggest real diagram (not all-white canvas)
        if png_bytes is None and _MermaidConverter is not None:
            candidate = self._render_mermaid_via_python_package(diagram_code)
            if candidate and self._mermaid_png_has_visible_diagram(candidate):
                png_bytes = candidate
            elif candidate and not self._mermaid_png_has_visible_diagram(candidate):
                if not _MERMAID_PHANTOM_BLANK_HINT_PRINTED:
                    print(
                        "  ⚠ pip package `mmdc` (PhantomJS) produced a blank PNG for at least one diagram. "
                        "Install Node.js `@mermaid-js/mermaid-cli` and ensure `mmdc` is on PATH "
                        "(npm i -g @mermaid-js/mermaid-cli) for reliable Mermaid rendering."
                    )
                    _MERMAID_PHANTOM_BLANK_HINT_PRINTED = True

        if png_bytes and cache_file is not None:
            try:
                self._write_png_cache_atomic(cache_file, png_bytes)
            except OSError:
                pass
        return png_bytes

    def _mermaid_source_display_path(self, source_file: Optional[Path]) -> str:
        if not source_file:
            return '(unknown file)'
        try:
            return str(source_file.resolve().relative_to(self.repo_root.resolve()))
        except ValueError:
            return str(source_file)

    def _replace_mermaid_placeholders(
        self,
        html: str,
        mermaid_blocks: List[str],
        source_file: Optional[Path] = None,
    ) -> Tuple[str, List[Tuple[str, bytes]]]:
        """
        Replace MERMAID_PLACEHOLDER_N with PNG images only (Fabric-editor safe).
        The mermaid structured macro is not supported in Fabric; we always render
        to PNG via mmdc. When PNG is unavailable, emit a placeholder paragraph.
        """
        mermaid_attachments: List[Tuple[str, bytes]] = []
        disp = self._mermaid_source_display_path(source_file)
        for idx, diagram_code in enumerate(mermaid_blocks):
            placeholder = f'<!-- MERMAID_PLACEHOLDER_{idx} -->'
            if not diagram_code:
                macro_html = '<p></p>'
            else:
                png_bytes = self._render_mermaid_to_png(diagram_code)
                if png_bytes:
                    # Fabric-safe: use attachment reference instead of data URL (ri:url data:... not supported in Fabric)
                    filename = f'mermaid-{idx}.png'
                    mermaid_attachments.append((filename, png_bytes))
                    macro_html = (
                        '<p><ac:image ac:align="center" ac:border="false">'
                        '<ri:attachment ri:filename="' + escape_xml(filename) + '"/>'
                        '</ac:image></p>'
                    )
                else:
                    print(
                        f"  ⚠ Mermaid PNG not generated: {disp} — "
                        f"diagram block #{idx} (attachment would be mermaid-{idx}.png). "
                        f"Install `mmdc` (pip install mmdc) and/or mermaid-cli (`mmdc` on PATH); "
                        f"if tools are installed, check diagram syntax."
                    )
                    macro_html = (
                        '<p><em>[Mermaid diagram: render with mmdc (npm install -g @mermaid-js/mermaid-cli) to see diagram here.]</em></p>'
                    )
            html = html.replace(placeholder, macro_html)
        return html, mermaid_attachments

    def convert_html_links_to_confluence(self, html: str, current_file_path: Path, root_path: Path) -> str:
        """
        Convert HTML links to .md files to Confluence page links.

        For existing pages (found in file_to_page_id), uses page ID-based linking.
        For new pages (not yet synced), falls back to title-based linking.

        Args:
            html: HTML content
            current_file_path: Path to the current file
            root_path: Root path of the sync operation

        Returns:
            HTML with links converted to Confluence format
        """
        # Match links to .md files
        link_pattern_md = r'<a\s+[^>]*href=["\']([^"\']+\.md[^"\']*)["\'][^>]*>([^<]+)</a>'
        # Match relative directory links (e.g. ../the-hub-way/) — resolve to README.md for lookup
        link_pattern_dir = r'<a\s+[^>]*href=["\'](\.\.?/[^"\']*/)["\'][^>]*>([^<]+)</a>'

        def replace_link(match):
            link_path = match.group(1)
            link_text = match.group(2).strip()
            # Remove anchor/fragment if present
            if '#' in link_path:
                link_path, anchor = link_path.split('#', 1)
            else:
                anchor = None
            # Resolve relative path
            if link_path.startswith('/'):
                target_path = root_path / link_path.lstrip('/')
            elif link_path.startswith('./'):
                target_path = current_file_path.parent / link_path[2:]
            elif link_path.startswith('../'):
                target_path = current_file_path.parent / link_path
            else:
                target_path = current_file_path.parent / link_path
            try:
                abs_target = target_path.resolve()
                abs_root = root_path.resolve()
                try:
                    target_str = str(abs_target.relative_to(abs_root))
                except ValueError:
                    return match.group(0)
                target_str = target_str.replace('\\', '/')
                # Look up page ID / title: try exact path and path without leading ./
                possible_paths = [
                    target_str,
                    target_str.lstrip('./'),
                ]
                # Directory links (path ending in / or without .md): also try README.md in that folder
                if not target_str.rstrip('/').endswith('.md'):
                    dir_path = target_str.rstrip('/')
                    possible_paths.append(f"{dir_path}/README.md")
                page_id = None
                page_title = None

                # Try to find page ID first (most reliable)
                for path_variant in possible_paths:
                    if path_variant in self.file_to_page_id:
                        page_id = self.file_to_page_id[path_variant]
                        break

                # If no page ID, try to find page title
                if not page_id:
                    for path_variant in possible_paths:
                        if path_variant in self.file_to_title:
                            page_title = self.file_to_title[path_variant]
                            break

                # Note: Confluence Cloud does NOT support ri:page-id or ri:content-id
                # in storage format - it strips these attributes. Must use ri:content-title.
                # We still look up page_id first to verify the page exists, but use title for linking.

                # Get title - prefer from cache, or use page_id lookup result if available
                resolved_title = page_title
                if page_id and not resolved_title:
                    # We have page_id but no title - look up the title from cache
                    for path_variant in possible_paths:
                        if path_variant in self.file_to_title:
                            resolved_title = self.file_to_title[path_variant]
                            break
                # Reverse lookup: if we have title but no page_id, try any path with this title (for Fabric plain links)
                if not page_id and resolved_title and self.confluence_base_url:
                    for path_key, title in self.file_to_title.items():
                        if title == resolved_title and path_key in self.file_to_page_id:
                            page_id = self.file_to_page_id[path_key]
                            break

                if resolved_title or page_id:
                    # Fabric-safe: when confluence_base_url is set, never use ac:link (Fabric does not support it)
                    if self.confluence_base_url:
                        if page_id:
                            view_url = f"{self.confluence_base_url}/pages/viewpage.action?pageId={page_id}"
                            if anchor:
                                view_url += f"#{escape_xml(anchor)}"
                            return f'<a href="{escape_xml(view_url)}">{link_text}</a>'
                        # No page_id (e.g. target not synced yet): use placeholder so page still syncs
                        return f'<a href="#">{link_text}</a>'
                    # Legacy: title-based ac:link (when not using Fabric-safe mode)
                    if resolved_title:
                        escaped_title = escape_title_for_confluence(resolved_title)
                        if anchor:
                            return f'<ac:link ac:anchor="{escape_xml(anchor)}"><ri:page ri:content-title="{escaped_title}"/><ac:plain-text-link-body><![CDATA[{link_text}]]></ac:plain-text-link-body></ac:link>'
                        return f'<ac:link><ri:page ri:content-title="{escaped_title}"/><ac:plain-text-link-body><![CDATA[{link_text}]]></ac:plain-text-link-body></ac:link>'
                else:
                    # No page found - return as regular link
                    return f'<a href="{link_path}">{link_text}</a>'
            except Exception:
                return match.group(0)

        # Apply .md links first, then directory links (e.g. ../the-hub-way/)
        html = re.sub(link_pattern_md, replace_link, html)
        html = re.sub(link_pattern_dir, replace_link, html)
        return html

    def _html_to_storage_format(self, html: str) -> str:
        """Convert HTML to Confluence Storage Format."""
        # Remove DOCTYPE, html, head, body tags if present
        html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<html[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'</html>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<body[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'</body>', '', html, flags=re.IGNORECASE)

        result = html.strip()

        # Ensure we have at least some content (Confluence requires non-empty body)
        if not result or len(result) < 10:
            result = '<p></p>'  # Minimal valid Confluence storage format

        return result

    def _add_git_metadata(self, content: str, file_path: Optional[Path] = None, commit_hash: Optional[str] = None) -> str:
        """Add Git metadata to content using Confluence info macro."""
        if not self.add_git_metadata:
            return content

        metadata_parts = []

        if commit_hash:
            metadata_parts.append(f"Commit: {commit_hash}")

        if file_path and self.github_repo_url and self.repo_root:
            github_url = get_file_github_url(
                file_path,
                self.repo_root,
                self.github_repo_url,
                commit_hash
            )
            if github_url:
                metadata_parts.append(f'<a href="{github_url}">View on GitHub</a>')

        if metadata_parts:
            # Plain HTML; avoid ac:structured-macro "info" which Fabric does not support
            metadata_html = '<p><strong>Source:</strong> ' + ' | '.join(metadata_parts) + '</p>'
            content = content + '\n\n' + metadata_html

        return content

    def prepare_directory_content(
        self,
        directory: Path,
        parent_id: Optional[str] = None,
        root_path: Optional[Path] = None,
        source_folder: Optional[str] = None,
        commit_hash: Optional[str] = None,
        destination_id: Optional[str] = None,
        sync_state: Optional[Dict[str, Any]] = None,
        files_processed_count: Optional[List[int]] = None,
        prepared_contents: Optional[List[PreparedContent]] = None,
        parent_id_map: Optional[Dict[str, str]] = None,
        progress_callback: Optional[callable] = None,
        directory_pages: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[PreparedContent], Dict[str, str], List[Dict[str, Any]]]:
        """
        Phase 1: Prepare all content locally (no API calls).
        Recursively processes directory and prepares all content for syncing.

        Args:
            directory: Directory to process
            parent_id: Parent page ID (for hierarchy)
            root_path: Root path for relative path calculation
            source_folder: Source folder identifier
            commit_hash: Fallback commit hash
            destination_id: Destination ID for state lookup
            sync_state: Cached sync state
            files_processed_count: Mutable counter for progress
            prepared_contents: List to accumulate prepared content
            parent_id_map: Map of directory paths to parent IDs
            progress_callback: Optional callback for progress updates
            directory_pages: List to accumulate directory page info

        Returns:
            Tuple of (prepared_contents list, parent_id_map dict, directory_pages list)
        """
        if prepared_contents is None:
            prepared_contents = []
        if parent_id_map is None:
            parent_id_map = {}
        if directory_pages is None:
            directory_pages = []
        if files_processed_count is None:
            files_processed_count = [0]
        if root_path is None:
            root_path = directory

        # Initialize ignore handler if not already done
        if self.ignore_handler is None:
            self.ignore_handler = IgnoreHandler(root_path)

        # Check if this directory should have a page (not root, has content, not ignored)
        is_root = (directory == root_path)
        dir_rel_path = str(directory.relative_to(root_path)) if not is_root else directory.name

        # Prepare folder entry if needed (not root, and has subdirectories or files)
        if not is_root:
            # Check if directory has content (subdirs or files)
            has_content = False
            for item in directory.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    if not (self.ignore_handler and self.ignore_handler.should_ignore_directory(item)):
                        has_content = True
                        break
                elif item.is_file() and item.suffix == '.md' and not item.name.startswith('.'):
                    if not (self.ignore_handler and self.ignore_handler.should_ignore(item)):
                        has_content = True
                        break

            if has_content:
                # Generate default folder title from directory name
                # DESIGN NOTE (ADR 0012): Do NOT auto-generate unique titles.
                # If a title conflict occurs, use .confluence-mapping.yaml to specify a unique title.
                default_folder_title = directory.name.replace('_', ' ').replace('-', ' ').title()
                # Remove leading numbers and clean up
                import re
                default_folder_title = re.sub(r'^\d+[-_\s]*', '', default_folder_title).strip()
                if not default_folder_title:
                    default_folder_title = directory.name

                # Check for README in this directory (for title, but README stays as separate page)
                readme_path = directory / 'README.md'
                if readme_path.exists() and not (self.ignore_handler and self.ignore_handler.should_ignore(readme_path)):
                    try:
                        with open(readme_path, 'r', encoding='utf-8') as f:
                            readme_content = f.read()
                        # Extract title from README (optional - can use for folder title)
                        for line in readme_content.split('\n'):
                            line = line.strip()
                            if line.startswith('# '):
                                readme_title = line[2:].strip()
                                if readme_title:
                                    default_folder_title = readme_title  # Use README title for folder
                                break
                    except Exception:
                        pass

                # Apply title mapping from .confluence-mapping.yaml if present
                # The mapping file in the PARENT directory controls this folder's title
                parent_dir = directory.parent
                title_mapper = get_title_mapping_loader()
                folder_title = title_mapper.get_folder_title(
                    parent_directory=parent_dir,
                    folder_name=directory.name,
                    default_title=default_folder_title
                )

                # Get previous history for folder
                folder_prev_history = None
                if sync_state and destination_id:
                    folder_key = f"{source_folder}/{dir_rel_path}" if source_folder else dir_rel_path
                    # Check for folder history (separate from page history)
                    folders = sync_state.get('folders', {})
                    if folder_key in folders:
                        folder_prev_history = folders[folder_key]

                # Add to folder pages list (folders, not directory pages)
                directory_pages.append({
                    'dir_path': directory,
                    'dir_rel_path': dir_rel_path,
                    'folder_title': folder_title,  # From directory name or README title
                    'parent_id': parent_id,  # Parent folder or page ID
                    'source_folder': source_folder,
                    'folder_key': f"{source_folder}/{dir_rel_path}" if source_folder else dir_rel_path,
                    'prev_history': folder_prev_history,
                    'readme_path': readme_path if readme_path.exists() else None  # Track README for title
                })

        # Process Markdown files in this directory (natural sort: 00, 01, 02, ..., 10 so order is retained)
        md_file_list = [p for p in directory.glob('*.md') if not p.name.startswith('.')]
        md_files = sorted(md_file_list, key=_natural_sort_key_for_md)
        # Detect if this folder uses numeric prefixes (so we retain order via prefix-in-title)
        has_numbered_files = any(_numeric_prefix_and_rest(p.stem) for p in md_files)

        for md_file in md_files:
            if self.ignore_handler and self.ignore_handler.should_ignore(md_file):
                continue

            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract title from first heading
                title = None
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
                    elif line.startswith('#'):
                        title = line[1:].strip()
                        break

                # Generate default title from file content or filename
                # DESIGN NOTE (ADR 0012): Do NOT auto-generate unique titles.
                # If a title conflict occurs, use .confluence-mapping.yaml to specify a unique title.
                if not title:
                    title = md_file.stem.replace('_', ' ').replace('-', ' ').title()

                legacy_title = None
                # When folder has numeric-prefixed files, include prefix in page title to retain order in Confluence
                if has_numbered_files:
                    parsed = _numeric_prefix_and_rest(md_file.stem)
                    if parsed:
                        prefix_str, rest_stem = parsed
                        stem_as_title = md_file.stem.replace('_', ' ').replace('-', ' ').title()
                        # Suffix: from # heading if title came from content, else from rest of stem
                        if title == stem_as_title:
                            suffix = rest_stem.replace('_', ' ').replace('-', ' ').title()
                        else:
                            suffix = title  # from # heading
                        title = f"{prefix_str} - {suffix}"
                        legacy_title = suffix  # for cleanup of old-format pages

                # Apply title mapping from .confluence-mapping.yaml if present
                # The mapping file in the same directory controls this page's title
                title_mapper = get_title_mapping_loader()
                title = title_mapper.get_page_title(
                    directory=directory,
                    filename=md_file.name,
                    default_title=title
                )

                rel_path = str(md_file.relative_to(root_path))
                file_key = f"{source_folder}/{rel_path}" if source_folder else rel_path

                # Get file-specific commit hash and date
                file_commit_hash = None
                file_commit_date = None
                if self.add_git_metadata:
                    file_commit_hash = get_file_commit_hash(md_file, self.repo_root)
                    file_commit_date = get_file_commit_date(md_file, self.repo_root)

                commit_hash_to_use = file_commit_hash or commit_hash

                # Get previous history from cached sync_state
                prev_history = None
                if sync_state and destination_id:
                    if source_folder:
                        prefixed_path = f"{source_folder}/{rel_path}"
                        if prefixed_path in sync_state.get('sync_history', {}):
                            prev_history = sync_state['sync_history'][prefixed_path]
                    if not prev_history and rel_path in sync_state.get('sync_history', {}):
                        prev_history = sync_state['sync_history'][rel_path]

                # Check force sync
                force_sync = False
                if sync_state and destination_id:
                    force_sync_paths = sync_state.get('force_sync_paths', [])
                    for force_path in force_sync_paths:
                        if file_key.startswith(force_path) or rel_path.startswith(force_path):
                            force_sync = True
                            break

                # Convert to storage format
                storage_format, mermaid_attachments = self.markdown_to_storage_format(content, md_file, root_path, commit_hash_to_use)
                content_hash = compute_content_hash(storage_format)
                # Compute content signature for rename detection
                content_sig = compute_content_signature(content)

                # Get directory relative path for this file
                file_dir_rel_path = str(directory.relative_to(root_path)) if directory != root_path else directory.name

                # Get parent ID (will be resolved during sync phase when folders are created)
                # For now, use the directory's relative path - parent ID will be resolved in Phase 2a
                dir_parent_id = parent_id_map.get(file_dir_rel_path, parent_id)

                # Get GitHub URL
                github_url = None
                if self.add_git_metadata:
                    github_url = get_file_github_url(md_file, self.repo_root, self.github_repo_url, commit_hash_to_use)

                # Get existing page ID from state (if available)
                existing_page_id = None
                if prev_history and prev_history.get('page_id'):
                    existing_page_id = prev_history['page_id']

                # Find images in this file for later upload
                image_paths = []
                if self.attachment_handler:
                    image_paths = self.attachment_handler.find_images_in_markdown(content, md_file)

                prepared = PreparedContent(
                    file_path=str(md_file),
                    rel_path=rel_path,
                    source_folder=source_folder,
                    title=title,
                    content=content,
                    storage_format=storage_format,
                    content_hash=content_hash,
                    content_signature=content_sig,
                    parent_id=dir_parent_id,  # Will be updated when directory page is created
                    commit_hash=commit_hash_to_use,
                    commit_date=file_commit_date,
                    github_url=github_url,
                    file_key=file_key,
                    prev_history=prev_history,
                    force_sync=force_sync,
                    existing_page_id=existing_page_id,
                    renamed_from=None,  # Will be set if rename detected
                    image_paths=image_paths,
                    mermaid_attachments=mermaid_attachments,
                    legacy_title=legacy_title
                )
                # Store directory relative path for later parent ID update
                prepared._dir_rel_path = file_dir_rel_path  # Store for parent ID update
                prepared_contents.append(prepared)

                files_processed_count[0] += 1
                if progress_callback:
                    file_display = rel_path if len(rel_path) <= 60 else "..." + rel_path[-57:]
                    progress_callback(files_processed_count[0], file_display)

            except Exception as e:
                print(f"  ✗ Error preparing {md_file}: {e}")
                continue

        # Recursively process subdirectories
        for subdir in sorted(directory.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith('.'):
                if self.ignore_handler and self.ignore_handler.should_ignore_directory(subdir):
                    continue
                # Get parent ID for subdirectory (will be set when folder is created)
                subdir_parent_id = parent_id_map.get(dir_rel_path, parent_id) if not is_root else parent_id

                # Recursively prepare subdirectory
                self.prepare_directory_content(
                    subdir,
                    subdir_parent_id,
                    root_path,
                    source_folder=source_folder,
                    commit_hash=commit_hash,
                    destination_id=destination_id,
                    sync_state=sync_state,
                    files_processed_count=files_processed_count,
                    prepared_contents=prepared_contents,
                    parent_id_map=parent_id_map,
                    progress_callback=progress_callback,
                    directory_pages=directory_pages
                )

        return prepared_contents, parent_id_map, directory_pages

#!/usr/bin/env python3
"""
Generate detailed sync reports for Confluence sync operations.

Reports include sync status, actions taken, commit hashes, page IDs, and URLs.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from tabulate import tabulate


class SyncResult:
    """Represents the result of syncing a single file."""
    
    def __init__(
        self,
        file_path: str,
        source_folder: Optional[str],
        status: str,  # 'created', 'updated', 'skipped', 'error'
        page_id: Optional[str] = None,
        page_title: Optional[str] = None,
        confluence_url: Optional[str] = None,
        github_url: Optional[str] = None,
        old_commit: Optional[str] = None,
        old_date: Optional[str] = None,
        new_commit: Optional[str] = None,
        new_date: Optional[str] = None,
        content_hash: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        self.file_path = file_path
        self.source_folder = source_folder
        self.status = status
        self.page_id = page_id
        self.page_title = page_title
        self.confluence_url = confluence_url
        self.github_url = github_url
        self.old_commit = old_commit
        self.old_date = old_date
        self.new_commit = new_commit
        self.new_date = new_date
        self.content_hash = content_hash
        self.error_message = error_message


def format_report_table_markdown(results: List[SyncResult], destination_id: str) -> str:
    """
    Format sync results as a Markdown table with full paths (no truncation).
    
    Args:
        results: List of SyncResult objects
        destination_id: Destination ID for header
        
    Returns:
        Formatted Markdown table string
    """
    if not results:
        return f"\nNo files synced for destination '{destination_id}'.\n"
    
    # Prepare table data
    table_rows = []
    for result in results:
        # Format file path (with source folder prefix if applicable) - FULL PATH, NO TRUNCATION
        file_display = result.file_path
        if result.source_folder:
            file_display = f"{result.source_folder}/{file_display}"
        
        # Format status
        status_display = {
            'created': '✓ Created',
            'updated': '↻ Updated',
            'skipped': '⊘ Skipped',
            'error': '✗ Error'
        }.get(result.status, result.status)
        
        # Format commit info - FULL COMMIT HASHES
        commit_info = ""
        if result.old_commit and result.new_commit:
            if result.old_commit != result.new_commit:
                commit_info = f"{result.old_commit} → {result.new_commit}"
            else:
                commit_info = result.new_commit
        elif result.new_commit:
            commit_info = result.new_commit
        
        # Format date info - FULL DATES
        date_info = ""
        if result.old_date and result.new_date:
            if result.old_date != result.new_date:
                date_info = f"{result.old_date} → {result.new_date}"
            else:
                date_info = result.new_date
        elif result.new_date:
            date_info = result.new_date
        
        # FULL URLs - NO TRUNCATION
        confluence_url_display = result.confluence_url or ''
        github_url_display = result.github_url or ''
        
        # Escape pipe characters in Markdown table cells
        def escape_md_cell(text):
            if not text:
                return ''
            return str(text).replace('|', '\\|').replace('\n', ' ')
        
        table_rows.append([
            escape_md_cell(file_display),
            escape_md_cell(status_display),
            escape_md_cell(result.page_id or ''),
            escape_md_cell(result.page_title or ''),
            escape_md_cell(commit_info),
            escape_md_cell(date_info),
            escape_md_cell(confluence_url_display),
            escape_md_cell(github_url_display),
            escape_md_cell(result.error_message or '')
        ])
    
    # Create Markdown table
    headers = [
        'File Path',
        'Status',
        'Page ID',
        'Page Title',
        'Commit',
        'Date',
        'Confluence URL',
        'GitHub URL',
        'Error'
    ]
    
    # Build Markdown table
    md_lines = []
    # Header row
    md_lines.append('| ' + ' | '.join(headers) + ' |')
    # Separator row
    md_lines.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
    # Data rows
    for row in table_rows:
        md_lines.append('| ' + ' | '.join(row) + ' |')
    
    return '\n'.join(md_lines)


def generate_sync_report(
    destination_id: str,
    destination_name: str,
    sync_state: Dict[str, Any],
    current_commit: Optional[str],
    results: List[SyncResult],
    confluence_base_url: str,
    space_key: str
) -> str:
    """
    Generate a comprehensive sync report in Markdown format with full paths.
    
    Args:
        destination_id: Destination ID
        destination_name: Destination name
        sync_state: Current sync state
        current_commit: Current commit hash
        results: List of SyncResult objects
        confluence_base_url: Confluence base URL
        space_key: Confluence space key
        
    Returns:
        Formatted Markdown report text
    """
    report_lines = []
    
    # Header
    report_lines.append(f"# Confluence Sync Report: {destination_name}")
    report_lines.append("")
    report_lines.append(f"**Destination ID:** `{destination_id}`")
    report_lines.append("")
    
    # Sync metadata
    report_lines.append("## Sync Metadata")
    report_lines.append("")
    report_lines.append(f"- **Timestamp:** {sync_state.get('last_sync_timestamp', 'N/A')}")
    report_lines.append(f"- **Commit:** `{current_commit or 'N/A'}`")
    report_lines.append(f"- **Space:** `{space_key}`")
    if sync_state.get('root_page_id'):
        root_url = f"{confluence_base_url}/pages/viewpage.action?pageId={sync_state['root_page_id']}"
        report_lines.append(f"- **Root Page ID:** `{sync_state['root_page_id']}`")
        report_lines.append(f"- **Root Page URL:** [{root_url}]({root_url})")
    report_lines.append("")
    
    # Summary statistics
    created = sum(1 for r in results if r.status == 'created')
    updated = sum(1 for r in results if r.status == 'updated')
    skipped = sum(1 for r in results if r.status == 'skipped')
    errors = sum(1 for r in results if r.status == 'error')
    total = len(results)
    
    # Folder statistics (Phase 20)
    folders = sync_state.get('folders', {})
    folder_created = sum(1 for f in folders.values() if f.get('status') == 'created')
    folder_found = sum(1 for f in folders.values() if f.get('status') == 'found')
    folder_deleted = sum(1 for f in folders.values() if f.get('status') == 'deleted')
    total_folders = len([f for f in folders.values() if f.get('folder_id')])
    
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"- **Total files:** {total}")
    report_lines.append(f"- **Created:** {created}")
    report_lines.append(f"- **Updated:** {updated}")
    report_lines.append(f"- **Skipped:** {skipped}")
    if errors > 0:
        report_lines.append(f"- **Errors:** {errors}")
    report_lines.append("")
    report_lines.append("### Folders")
    report_lines.append("")
    report_lines.append(f"- **Total folders:** {total_folders}")
    if folder_created > 0:
        report_lines.append(f"- **Created:** {folder_created}")
    if folder_found > 0:
        report_lines.append(f"- **Found (existing):** {folder_found}")
    if folder_deleted > 0:
        report_lines.append(f"- **Deleted:** {folder_deleted}")
    report_lines.append("")
    
    # Changes section (created and updated files)
    changed_results = [r for r in results if r.status in ['created', 'updated']]
    if changed_results:
        report_lines.append("## CHANGES (Created/Updated Files)")
        report_lines.append("")
        report_lines.append(format_report_table_markdown(changed_results, destination_id))
        report_lines.append("")
    
    # Skipped section
    skipped_results = [r for r in results if r.status == 'skipped']
    if skipped_results:
        report_lines.append("## SKIPPED (No Changes Detected)")
        report_lines.append("")
        report_lines.append(f"**Total skipped:** {len(skipped_results)}")
        report_lines.append("")
        
        # Show skipped files in Markdown table format - FULL PATHS
        skipped_table_rows = []
        for result in skipped_results:
            file_display = result.file_path
            if result.source_folder:
                file_display = f"{result.source_folder}/{file_display}"
            
            # FULL commit hash, date, and content hash - NO TRUNCATION
            commit_info = result.new_commit or 'N/A'
            date_info = result.new_date or 'N/A'
            hash_info = result.content_hash or 'N/A'
            
            # Escape pipe characters
            def escape_md_cell(text):
                if not text:
                    return ''
                return str(text).replace('|', '\\|').replace('\n', ' ')
            
            skipped_table_rows.append([
                escape_md_cell(file_display),
                escape_md_cell(result.page_title or ''),
                escape_md_cell(commit_info),
                escape_md_cell(date_info),
                escape_md_cell(hash_info)
            ])
        
        if skipped_table_rows:
            skipped_headers = ['File Path', 'Page Title', 'Commit', 'Date', 'Content Hash']
            md_lines = []
            md_lines.append('| ' + ' | '.join(skipped_headers) + ' |')
            md_lines.append('| ' + ' | '.join(['---'] * len(skipped_headers)) + ' |')
            for row in skipped_table_rows:
                md_lines.append('| ' + ' | '.join(row) + ' |')
            report_lines.append('\n'.join(md_lines))
            report_lines.append("")
    
    # Folder details section (Phase 20-3) - FULL PATHS
    if folders:
        report_lines.append("## FOLDERS")
        report_lines.append("")
        
        folder_table_rows = []
        for folder_path, folder_entry in sorted(folders.items()):
            folder_id = folder_entry.get('folder_id', 'N/A')
            folder_title = folder_entry.get('folder_title', 'N/A')
            folder_status = folder_entry.get('status', 'unknown')
            parent_id = folder_entry.get('parent_id', 'N/A')
            
            status_display = {
                'created': '✓ Created',
                'found': '⊘ Found',
                'deleted': '✗ Deleted',
                'migrated': '↻ Migrated'
            }.get(folder_status, folder_status)
            
            # Escape pipe characters
            def escape_md_cell(text):
                if not text:
                    return ''
                return str(text).replace('|', '\\|').replace('\n', ' ')
            
            # FULL PATHS - NO TRUNCATION
            folder_table_rows.append([
                escape_md_cell(folder_path),
                escape_md_cell(folder_title),
                escape_md_cell(folder_id),
                escape_md_cell(parent_id),
                escape_md_cell(status_display)
            ])
        
        if folder_table_rows:
            folder_headers = ['Folder Path', 'Folder Title', 'Folder ID', 'Parent ID', 'Status']
            md_lines = []
            md_lines.append('| ' + ' | '.join(folder_headers) + ' |')
            md_lines.append('| ' + ' | '.join(['---'] * len(folder_headers)) + ' |')
            for row in folder_table_rows:
                md_lines.append('| ' + ' | '.join(row) + ' |')
            report_lines.append('\n'.join(md_lines))
            report_lines.append("")
    
    # Errors section (if any) - FULL PATHS
    error_results = [r for r in results if r.status == 'error']
    if error_results:
        report_lines.append("## ERRORS")
        report_lines.append("")
        for result in error_results:
            file_display = result.file_path
            if result.source_folder:
                file_display = f"{result.source_folder}/{file_display}"
            report_lines.append(f"- **{file_display}:** {result.error_message}")
        report_lines.append("")
    
    # Footer
    report_lines.append("---")
    report_lines.append(f"*Report generated: {datetime.utcnow().isoformat()}Z*")
    
    return "\n".join(report_lines)


def save_report_to_file(
    destination_id: str,
    report_text: str,
    data_dir: Optional[Path] = None,
    timestamp: Optional[datetime] = None
) -> Path:
    """
    Save report to file in Markdown format.
    
    Args:
        destination_id: Destination ID
        report_text: Report text
        data_dir: Optional explicit data directory path
        timestamp: Timestamp for filename (defaults to now)
        
    Returns:
        Path to saved report file
    """
    if timestamp is None:
        timestamp = datetime.utcnow()
    
    # Use destination-specific data directory
    from confluence_sync.sync_state import get_destination_data_dir
    state_dir = data_dir if data_dir else (Path.home() / ".local" / "confluence-sync" / "destinations")
    dest_dir = get_destination_data_dir(destination_id, state_dir)
    timestamp_str = timestamp.strftime('%Y%m%d-%H%M%S')
    report_file = dest_dir / f'sync-report-{timestamp_str}.md'
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        return report_file
    except Exception as e:
        print(f"  ⚠ Warning: Could not save report file: {e}")
        return report_file

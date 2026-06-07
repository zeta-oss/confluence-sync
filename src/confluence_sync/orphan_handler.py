"""
Orphan Handler Module - Detects and handles orphaned Confluence pages.

Orphaned pages are pages in Confluence that no longer have corresponding
source files in the Git repository (files were deleted or moved).
"""

from typing import Dict, List, Set, Any, Optional, Tuple
from confluence_sync.confluence_sync import ConfluenceSync


class OrphanHandler:
    """
    Handles detection and deletion of orphaned Confluence pages and folders.
    
    Orphaned items are pages/folders in Confluence that no longer have corresponding
    source files in the Git repository (files were deleted or moved).
    
    Important: Only items tracked in sync state are deleted. Manually created
    content in Confluence is not affected by orphan detection.
    """
    
    def __init__(self, confluence_sync: ConfluenceSync):
        """
        Initialize orphan handler.
        
        Args:
            confluence_sync: ConfluenceSync instance for API calls
        """
        self.confluence_sync = confluence_sync
    
    def find_orphans(
        self,
        sync_state: Dict[str, Any],
        discovered_files: Set[str],
        renamed_files: Set[str],
        discovered_folders: Optional[Set[str]] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Find state entries that no longer have corresponding files or folders.
        
        Args:
            sync_state: Loaded sync state dictionary
            discovered_files: Set of file keys discovered in current sync
            renamed_files: Set of old file paths that were renamed (not deleted)
            discovered_folders: Set of folder keys discovered in current sync
            
        Returns:
            Tuple of (orphan_pages, orphan_folders) - lists of orphan entries
        """
        orphan_pages = []
        orphan_folders = []
        sync_history = sync_state.get('sync_history', {})
        folders = sync_state.get('folders', {})
        discovered_folders = discovered_folders or set()
        
        # Find orphaned pages
        for path, entry in sync_history.items():
            # Skip if file still exists
            if path in discovered_files:
                continue
            
            # Skip if this was a rename (old path of renamed file)
            if path in renamed_files:
                continue
            
            # This is an orphan - file was deleted
            orphan_pages.append({
                'path': path,
                'page_id': entry.get('page_id'),
                'page_title': entry.get('page_title', 'Unknown'),
                'type': 'page',
                **entry
            })
        
        # Find orphaned folders
        for folder_path, entry in folders.items():
            # Skip if folder still exists
            if folder_path in discovered_folders:
                continue
            
            # This is an orphan folder - directory was deleted
            orphan_folders.append({
                'path': folder_path,
                'folder_id': entry.get('folder_id'),
                'folder_title': entry.get('folder_title', 'Unknown'),
                'type': 'folder',
                'parent_id': entry.get('parent_id'),
                **entry
            })
        
        return orphan_pages, orphan_folders
    
    def delete_orphans(self, orphan_pages: List[Dict[str, Any]], orphan_folders: List[Dict[str, Any]]) -> List[str]:
        """
        Delete orphaned pages and folders from Confluence using REST API v2.
        
        Deletes pages first, then folders (child folders before parent folders).
        
        Args:
            orphan_pages: List of orphan page entries to delete
            orphan_folders: List of orphan folder entries to delete
            
        Returns:
            List of deleted paths (pages and folders)
        """
        deleted = []
        
        # Delete orphaned pages first using v2
        for orphan in orphan_pages:
            page_id = orphan.get('page_id')
            page_title = orphan.get('page_title', 'Unknown')
            path = orphan.get('path', 'Unknown')
            
            if not page_id:
                print(f"  ⚠ Warning: Orphan page '{path}' has no page_id, skipping")
                continue
            
            try:
                if self.confluence_sync.delete_page_v2(page_id):
                    deleted.append(path)
                    print(f"  ✓ Deleted orphaned page: {page_title} (ID: {page_id})")
                else:
                    print(f"  ⚠ Warning: Could not delete orphan page '{path}' (ID: {page_id})")
            except Exception as e:
                print(f"  ✗ Error deleting orphan page '{path}': {e}")
        
        # Delete orphaned folders (child folders before parent folders)
        # Sort by depth (deepest first) to ensure children are deleted before parents
        def get_folder_depth(folder_info):
            path = folder_info.get('path', '')
            return path.count('/')
        
        orphan_folders_sorted = sorted(orphan_folders, key=get_folder_depth, reverse=True)
        
        for orphan in orphan_folders_sorted:
            folder_id = orphan.get('folder_id')
            folder_title = orphan.get('folder_title', 'Unknown')
            path = orphan.get('path', 'Unknown')
            
            if not folder_id:
                print(f"  ⚠ Warning: Orphan folder '{path}' has no folder_id, skipping")
                continue
            
            try:
                if self.confluence_sync.delete_folder(folder_id):
                    deleted.append(path)
                    print(f"  ✓ Deleted orphaned folder: {folder_title} (ID: {folder_id})")
                else:
                    print(f"  ⚠ Warning: Could not delete orphan folder '{path}' (ID: {folder_id})")
            except Exception as e:
                print(f"  ✗ Error deleting orphan folder '{path}': {e}")
        
        return deleted

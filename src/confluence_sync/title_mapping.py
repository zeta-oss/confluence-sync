"""
Title Mapping Module for Confluence Sync

This module handles loading and applying .confluence-mapping.yaml files
that explicitly map local folder/page names to Confluence titles.

IMPORTANT DESIGN DECISION (ADR 0012):
-------------------------------------
This module provides EXPLICIT title mappings only. The sync system MUST NOT
auto-generate unique folder or page titles. If a title conflict cannot be
resolved via a mapping file, the sync MUST fail with a clear error message.

DO NOT add any automatic disambiguation logic such as:
- Appending parent folder names
- Adding numeric suffixes
- Using path-based hashes
- Any form of automatic title generation

If you're tempted to add such logic, re-read ADR 0012 first.
"""

import os
from pathlib import Path
from typing import Dict, Optional, Any
import yaml


class TitleMappingLoader:
    """
    Loads and manages .confluence-mapping.yaml files from source directories.
    
    The mapping file format:
    ```yaml
    folders:
      local-folder-name: "Confluence Folder Title"
    pages:
      local-file.md: "Confluence Page Title"
    ```
    
    DESIGN CONSTRAINT: This class only provides explicit mappings.
    It does NOT generate unique titles automatically. See ADR 0012.
    """
    
    MAPPING_FILENAME = '.confluence-mapping.yaml'
    
    def __init__(self):
        # Cache: directory_path -> mapping dict
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def load_mapping(self, directory: Path) -> Dict[str, Any]:
        """
        Load the mapping file from a directory.
        
        Args:
            directory: Path to the directory containing the mapping file
            
        Returns:
            Dictionary with 'folder_title', 'folders' and 'pages' mappings
            
        The mapping file can contain:
        - folder_title: Title for THIS folder (the one containing the mapping file)
        - folders: Dict mapping subfolder names to titles
        - pages: Dict mapping page filenames to titles
        """
        dir_str = str(directory)
        
        if dir_str in self._cache:
            return self._cache[dir_str]
        
        mapping_file = directory / self.MAPPING_FILENAME
        
        if not mapping_file.exists():
            # No mapping file - return empty mappings
            result = {'folder_title': None, 'folders': {}, 'pages': {}}
            self._cache[dir_str] = result
            return result
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f) or {}
            
            result = {
                'folder_title': content.get('folder_title'),  # Title for this folder
                'folders': content.get('folders', {}),  # Subfolder mappings
                'pages': content.get('pages', {})
            }
            self._cache[dir_str] = result
            return result
        except Exception as e:
            print(f"  ⚠ Warning: Failed to load {mapping_file}: {e}")
            result = {'folder_title': None, 'folders': {}, 'pages': {}}
            self._cache[dir_str] = result
            return result
    
    def get_folder_title(
        self, 
        parent_directory: Path, 
        folder_name: str,
        default_title: str
    ) -> str:
        """
        Get the Confluence title for a folder.
        
        Checks two locations for mappings:
        1. The folder's own mapping file for 'folder_title' (preferred)
        2. The parent's mapping file for 'folders[folder_name]'
        
        Args:
            parent_directory: Path to the parent directory
            folder_name: The local folder name (e.g., 'examples')
            default_title: The default title to use if no mapping exists
            
        Returns:
            The Confluence title (either from mapping or default)
            
        Note: This method does NOT auto-generate unique titles.
              If the returned title conflicts in Confluence, the sync should fail.
              See ADR 0012.
        """
        # First, check the folder's own mapping file for folder_title
        folder_path = parent_directory / folder_name
        if folder_path.exists():
            folder_mapping = self.load_mapping(folder_path)
            if folder_mapping.get('folder_title'):
                return folder_mapping['folder_title']
        
        # Second, check parent's mapping file for folders[folder_name]
        parent_mapping = self.load_mapping(parent_directory)
        folders = parent_mapping.get('folders', {})
        
        if folder_name in folders:
            mapped_title = folders[folder_name]
            return mapped_title
        
        return default_title
    
    def get_page_title(
        self,
        directory: Path,
        filename: str,
        default_title: str
    ) -> str:
        """
        Get the Confluence title for a page.
        
        Args:
            directory: Path to the directory containing the page and mapping file
            filename: The local filename (e.g., 'README.md')
            default_title: The default title to use if no mapping exists
            
        Returns:
            The Confluence title (either from mapping or default)
            
        Note: This method does NOT auto-generate unique titles.
              If the returned title conflicts in Confluence, the sync should fail.
              See ADR 0012.
        """
        mapping = self.load_mapping(directory)
        pages = mapping.get('pages', {})
        
        if filename in pages:
            mapped_title = pages[filename]
            return mapped_title
        
        return default_title
    
    def has_folder_mapping(self, parent_directory: Path, folder_name: str) -> bool:
        """Check if a folder has an explicit mapping."""
        # Check folder's own mapping file
        folder_path = parent_directory / folder_name
        if folder_path.exists():
            folder_mapping = self.load_mapping(folder_path)
            if folder_mapping.get('folder_title'):
                return True
        # Check parent's mapping file
        mapping = self.load_mapping(parent_directory)
        return folder_name in mapping.get('folders', {})
    
    def get_own_folder_title(self, folder_directory: Path, default_title: str) -> str:
        """
        Get the Confluence title for a folder from its own mapping file.
        
        This is used when the caller already has the full folder path.
        
        Args:
            folder_directory: Path to the folder
            default_title: The default title to use if no mapping exists
            
        Returns:
            The Confluence title (either from mapping or default)
        """
        mapping = self.load_mapping(folder_directory)
        if mapping.get('folder_title'):
            return mapping['folder_title']
        return default_title
    
    def has_page_mapping(self, directory: Path, filename: str) -> bool:
        """Check if a page has an explicit mapping."""
        mapping = self.load_mapping(directory)
        return filename in mapping.get('pages', {})
    
    def clear_cache(self):
        """Clear the mapping cache."""
        self._cache.clear()


# Global instance for convenience
_global_loader: Optional[TitleMappingLoader] = None


def get_title_mapping_loader() -> TitleMappingLoader:
    """Get the global TitleMappingLoader instance."""
    global _global_loader
    if _global_loader is None:
        _global_loader = TitleMappingLoader()
    return _global_loader


def reset_title_mapping_loader():
    """Reset the global loader (useful for testing)."""
    global _global_loader
    if _global_loader:
        _global_loader.clear_cache()
    _global_loader = None

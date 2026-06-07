#!/usr/bin/env python3
"""
Handle .confluence-ignore files for syncing.

Supports gitignore-style patterns:
- Simple filenames: "file.md"
- Patterns: "*.md", "**/temp/"
- Directory patterns: "folder/"
- Negation: "!important.md"
- Wildcard: "*" (ignores everything)
"""

import re
from pathlib import Path
from typing import List, Set, Optional


class IgnoreHandler:
    """Handle .confluence-ignore patterns."""
    
    def __init__(self, root_path: Path):
        """
        Initialize ignore handler.
        
        Args:
            root_path: Root directory path for resolving ignore files
        """
        self.root_path = root_path.resolve()
        self.ignore_patterns: List[tuple] = []  # List of (pattern, is_negation, path) tuples
        self._load_ignore_files()
    
    def _load_ignore_files(self) -> None:
        """Load all .confluence-ignore files recursively."""
        self.ignore_patterns = []
        
        # Find all .confluence-ignore files
        for ignore_file in self.root_path.rglob('.confluence-ignore'):
            self._load_ignore_file(ignore_file)
    
    def _load_ignore_file(self, ignore_file: Path) -> None:
        """
        Load patterns from a .confluence-ignore file.
        
        Args:
            ignore_file: Path to .confluence-ignore file
        """
        try:
            with open(ignore_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Check for wildcard "*" - ignore everything
                    if line == '*':
                        # Mark this directory and all subdirectories as ignored
                        ignore_dir = ignore_file.parent
                        rel_dir = ignore_dir.relative_to(self.root_path)
                        self.ignore_patterns.append(('*', False, str(rel_dir)))
                        continue
                    
                    # Check for negation
                    is_negation = line.startswith('!')
                    if is_negation:
                        pattern = line[1:].strip()
                    else:
                        pattern = line
                    
                    if not pattern:
                        continue
                    
                    # Get relative path from root for context
                    ignore_dir = ignore_file.parent
                    rel_dir = ignore_dir.relative_to(self.root_path)
                    
                    # Store pattern with context
                    self.ignore_patterns.append((pattern, is_negation, str(rel_dir)))
        
        except Exception as e:
            print(f"  ⚠ Warning: Could not read {ignore_file}: {e}")
    
    def _pattern_to_regex(self, pattern: str) -> re.Pattern:
        """
        Convert gitignore-style pattern to regex.
        
        Args:
            pattern: Gitignore-style pattern
            
        Returns:
            Compiled regex pattern
        """
        # Escape special regex characters except *, ?, [, ]
        pattern = re.escape(pattern)
        
        # Replace escaped patterns with regex equivalents
        pattern = pattern.replace(r'\*\*', 'STARSTAR')
        pattern = pattern.replace(r'\*', '[^/]*')
        pattern = pattern.replace('STARSTAR', '.*')
        pattern = pattern.replace(r'\?', '[^/]')
        pattern = pattern.replace(r'\[', '[')
        pattern = pattern.replace(r'\]', ']')
        
        # Handle directory patterns (ending with /)
        if pattern.endswith('/'):
            pattern = pattern[:-1] + r'(/.*)?'
        
        # Anchor to start of path
        pattern = '^' + pattern
        
        # Allow matching at any directory level for ** patterns
        if '.*' in pattern:
            pattern = pattern.replace('^', '^.*')
        
        return re.compile(pattern)
    
    def _matches_pattern(self, path: Path, pattern: str, pattern_context: str) -> bool:
        """
        Check if a path matches a pattern.
        
        Args:
            path: Path to check (absolute)
            pattern: Pattern to match against
            pattern_context: Directory where the pattern was defined (relative to root)
            
        Returns:
            True if path matches pattern
        """
        # Get relative path from root
        try:
            rel_path = path.relative_to(self.root_path)
        except ValueError:
            # Path is outside root
            return False
        
        rel_path_str = str(rel_path).replace('\\', '/')
        
        # If pattern context is specified, we need to match relative to that context
        if pattern_context and pattern_context != '.':
            # Check if path is within the pattern context
            try:
                context_path = (self.root_path / pattern_context).resolve()
                path.relative_to(context_path)
                # Path is within context, get path relative to context
                rel_to_context = path.relative_to(context_path)
                match_path = str(rel_to_context).replace('\\', '/')
            except ValueError:
                # Path is outside context, pattern doesn't apply
                return False
        else:
            # No context, match against full relative path
            match_path = rel_path_str
        
        # Convert pattern to regex
        try:
            regex = self._pattern_to_regex(pattern)
            return bool(regex.search(match_path))
        except Exception:
            # If pattern conversion fails, do simple string matching
            return pattern in match_path
    
    def should_ignore(self, path: Path) -> bool:
        """
        Check if a file or directory should be ignored.
        
        Args:
            path: Path to check (can be absolute or relative)
            
        Returns:
            True if path should be ignored
        """
        # Resolve to absolute path
        if not path.is_absolute():
            path = self.root_path / path
        path = path.resolve()
        
        # Check for wildcard "*" patterns first
        for pattern, is_negation, pattern_context in self.ignore_patterns:
            if pattern == '*':
                # Check if path is within the ignored directory
                if pattern_context == '.':
                    ignore_dir = self.root_path
                else:
                    ignore_dir = (self.root_path / pattern_context).resolve()
                
                try:
                    path.relative_to(ignore_dir)
                    # Path is within ignored directory
                    if not is_negation:
                        return True
                except ValueError:
                    # Path is outside ignored directory, continue
                    pass
        
        # Check all patterns (negations last)
        matches = []
        negations = []
        
        for pattern, is_negation, pattern_context in self.ignore_patterns:
            if pattern == '*':
                continue  # Already handled
            
            if self._matches_pattern(path, pattern, pattern_context):
                if is_negation:
                    negations.append(pattern)
                else:
                    matches.append(pattern)
        
        # If there are negations, they override matches
        if negations:
            return False
        
        # If there are matches, ignore
        return len(matches) > 0
    
    def should_ignore_directory(self, directory: Path) -> bool:
        """
        Check if a directory should be ignored.
        
        Args:
            directory: Directory path to check
            
        Returns:
            True if directory should be ignored
        """
        return self.should_ignore(directory)
    
    def should_ignore_file(self, file_path: Path) -> bool:
        """
        Check if a file should be ignored.
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file should be ignored
        """
        return self.should_ignore(file_path)

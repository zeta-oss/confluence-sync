#!/usr/bin/env python3
"""
Confluence Sync Module - Phase 2 of Confluence Sync

This module handles syncing prepared content to Confluence via REST API.
It performs all API calls to Confluence in parallel threads.

Clear boundaries:
- Input: List of PreparedContent objects
- Output: List of SyncResult objects
- Dependencies: Confluence REST API
- Thread-safe parallel execution
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    raise ImportError("'requests' library not found. Install with: pip install requests")

from confluence_sync.content_preparer import PreparedContent
from confluence_sync.report_generator import SyncResult


class ParentPageNotFoundError(Exception):
    """Raised when a parent page does not exist or is archived."""
    pass


class PageNotFoundError(Exception):
    """Page not found in sync state or Confluence."""
    pass


class DuplicateTitleError(Exception):
    """Multiple pages with same title found - cannot resolve automatically."""
    pass


class TitleConflictError(Exception):
    """
    Raised when a page or folder title conflict cannot be resolved.

    This exception is raised when attempting to create or update a page/folder
    with a title that already exists in the space, and the existing item cannot
    be found or reused. Unlike the old behavior (which would append suffixes),
    this error requires manual resolution.

    Attributes:
        message: Error message describing the conflict
    """
    pass


class HierarchyValidationError(Exception):
    """
    Raised when page or folder hierarchy validation fails.

    This exception is raised when a page or folder is found to be in an
    incorrect location in the Confluence hierarchy (e.g., wrong parent,
    outside destination root, etc.).

    Attributes:
        message: Error message describing the hierarchy issue
    """
    pass


class ConfluenceSync:
    """
    Syncs prepared content to Confluence via REST API.

    This class handles all Confluence API interactions.
    It operates on PreparedContent objects from the content preparer.
    """

    def __init__(self, base_url: str, username: str, token: str, space_key: str, space_id: Optional[str] = None):
        """
        Initialize Confluence sync client.

        Args:
            base_url: Confluence base URL (e.g., https://yourcompany.atlassian.net)
            username: Confluence username/email
            token: Confluence API token
            space_key: Confluence space key
            space_id: Optional Confluence space ID (will be resolved from space_key if not provided)
        """
        # Ensure base_url has /wiki if it's a Cloud instance
        base_url = base_url.rstrip('/')
        if '/wiki' not in base_url:
            self.base_url = f"{base_url}/wiki"
        else:
            self.base_url = base_url

        # API URL should be base_url/wiki/api/v2 (REST API v2)
        self.api_url = f"{self.base_url}/api/v2"
        self.username = username
        self.token = token
        self.space_key = space_key
        self.auth = HTTPBasicAuth(username, token)

        # Increase timeout for large content
        # Use tuple format: (connect_timeout, read_timeout)
        # Connect timeout: 10s (connection establishment)
        # Read timeout: 60s (waiting for response data)
        self.timeout = (10, 60)  # (connect, read) timeouts in seconds

        # Cache for page lookups (title -> page_id)
        self.page_cache: Dict[str, str] = {}

        # Resolve space_id if not provided (after timeout is set)
        if space_id:
            self.space_id = space_id
        else:
            self.space_id = self._get_space_id(space_key)

    def _paginate_v2(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Handle cursor-based pagination for REST API v2.

        v2 uses cursor-based pagination with 'cursor' parameter
        instead of offset-based pagination.

        Args:
            endpoint: API endpoint to call
            params: Additional query parameters
            max_results: Maximum total results to fetch

        Returns:
            List of all results across pages
        """
        all_results = []
        cursor = None
        params = params or {}

        while len(all_results) < max_results:
            if cursor:
                params['cursor'] = cursor

            response = self._make_request('GET', endpoint, params=params)
            data = response.json()

            results = data.get('results', [])
            all_results.extend(results)

            # Check for next page
            links = data.get('_links', {})
            next_link = links.get('next')
            if not next_link:
                break

            # Extract cursor from next link
            # Format: /wiki/api/v2/...?cursor=xxx
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed.query)
            cursor = query_params.get('cursor', [None])[0]

            if not cursor:
                break

        return all_results

    def _get_space_id(self, space_key: str) -> str:
        """
        Get space ID from space key using REST API v2.

        Args:
            space_key: Confluence space key

        Returns:
            Space ID as string

        Raises:
            Exception: If space not found
        """
        try:
            response = self._make_request('GET', '/spaces', params={'keys': space_key})
            data = response.json()
            spaces = data.get('results', [])
            if spaces:
                return str(spaces[0]['id'])
            raise Exception(f"Space '{space_key}' not found")
        except Exception as e:
            raise Exception(f"Could not resolve space_id for space_key '{space_key}': {e}")

    @staticmethod
    def _page_storage_body(page_data: Dict[str, Any]) -> str:
        """Extract storage-format HTML from a v2 page JSON payload."""
        body = page_data.get("body") or {}
        storage = body.get("storage")
        if isinstance(storage, dict) and storage.get("value"):
            return storage["value"]
        return body.get("value", "") or ""

    def _get_page(self, page_id: str, *, include_body: bool = False) -> Dict[str, Any]:
        """Fetch a page by ID; request storage body when content comparison is needed."""
        params = {"body-format": "storage"} if include_body else None
        response = self._make_request("GET", f"/pages/{page_id}", params=params)
        return response.json()

    def _make_request_internal(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Internal method to make API request (without retry logic)."""
        endpoint = endpoint.lstrip('/')
        url = f"{self.api_url}/{endpoint}"
        headers = kwargs.pop('headers', {})
        headers.setdefault('Content-Type', 'application/json')
        headers.setdefault('Accept', 'application/json')

        response = requests.request(
            method,
            url,
            auth=self.auth,
            headers=headers,
            timeout=self.timeout,
            **kwargs
        )
        response.raise_for_status()
        return response

    def _make_request(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs
    ) -> requests.Response:
        """
        Make API request with retry and exponential backoff.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            requests.exceptions.HTTPError: If request fails after all retries
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response = self._make_request_internal(method, endpoint, **kwargs)
                return response
            except ParentPageNotFoundError:
                # Don't retry parent page not found errors - they're permanent
                raise
            except requests.exceptions.HTTPError as e:
                last_exception = e
                if e.response is not None:
                    status_code = e.response.status_code

                    # Rate limited - retry with Retry-After header
                    if status_code == 429:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = base_delay * (2 ** attempt)
                        else:
                            delay = base_delay * (2 ** attempt)
                        if attempt < max_retries:
                            print(f"  Rate limited (429). Waiting {delay:.1f}s before retry...")
                            time.sleep(delay)
                            continue

                    # Server error (5xx) - retry
                    if status_code >= 500:
                        delay = base_delay * (2 ** attempt)
                        if attempt < max_retries:
                            print(f"  Server error {status_code}. Retrying in {delay:.1f}s...")
                            time.sleep(delay)
                            continue

                    # Client error (4xx) - don't retry, but show details
                    # Store error_detail and status_code on response BEFORE consuming it
                    # (status_code may become None after response is consumed)
                    e.response._status_code = status_code  # Preserve status code
                    if attempt == 0:  # Only show error details on first attempt
                        try:
                            # Store error detail BEFORE printing (so it's available for caller)
                            error_detail = e.response.json()
                            # Store it on the response object for later use
                            e.response._error_detail = error_detail
                            print(f"ERROR: API request failed: {e}")
                            print(f"  Details: {json.dumps(error_detail, indent=2)}")
                            print(f"  DEBUG: Stored _error_detail on response, type={type(error_detail)}, has_message={'message' in error_detail if isinstance(error_detail, dict) else False}")
                        except Exception as json_err:
                            print(f"ERROR: API request failed: {e}")
                            print(f"  DEBUG: Failed to parse JSON: {json_err}")
                            try:
                                # Try to store text if JSON fails
                                if hasattr(e.response, 'text'):
                                    e.response._error_detail = {'message': e.response.text[:500]}
                                    print("  DEBUG: Stored text as _error_detail")
                                print(f"  Response: {e.response.text[:500]}")
                            except Exception:
                                pass
                raise
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                delay = base_delay * (2 ** attempt)
                if attempt < max_retries:
                    print(f"  Connection error. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
                last_exception = e
                delay = base_delay * (2 ** attempt)
                if attempt < max_retries:
                    print(f"  Timeout error ({type(e).__name__}). Retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(delay)
                    continue
                else:
                    print(f"  Timeout error after {max_retries + 1} attempts. Giving up.")
            except Exception:
                # Other unexpected errors - don't retry
                raise
            raise

        # If we get here, all retries exhausted
        if last_exception:
            raise last_exception
        raise Exception("Request failed after retries")

    def get_space_homepage_id(self) -> Optional[str]:
        """Get the homepage ID for the space using REST API v2."""
        try:
            # Use v2 spaces endpoint
            response = self._make_request(
                'GET',
                f'/spaces/{self.space_id}'
            )
            data = response.json()
            # v2 API structure may differ - check for homepage
            homepage_id = data.get('homepageId')
            if homepage_id:
                return str(homepage_id)
            # Fallback: try to get homepage from space metadata
            homepage = data.get('homepage')
            if homepage:
                return str(homepage.get('id'))
            return None
        except Exception as e:
            print(f"WARNING: Could not get space homepage: {e}")
            return None

    # ========== Folder Operations (REST API v2) ==========

    def create_folder(
        self,
        title: str,
        space_id: str,
        parent_id: Optional[str] = None,
        root_page_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Create a folder using REST API v2.

        Args:
            title: Folder title
            space_id: Confluence space ID
            parent_id: Optional parent folder or page ID

        Returns:
            Tuple of (folder_id, status)
        """
        folder_data = {
            "spaceId": space_id,
            "title": title
        }

        if parent_id:
            folder_data["parentId"] = str(parent_id)

        try:
            response = self._make_request('POST', '/folders', json=folder_data)
            folder = response.json()
            folder_id = str(folder['id'])
            return folder_id, 'created'
        except requests.exceptions.HTTPError as e:
            # Get status code from preserved _status_code (original status_code may be None after body consumption)
            status_code = getattr(e.response, '_status_code', None) or (e.response.status_code if e.response else None)
            # Note: Use "is not None" because bool(e.response) is False for 4xx/5xx responses
            if e.response is not None and status_code == 400:
                # Check if it's a "already exists" error (v2 API format)
                error_detail = getattr(e.response, '_error_detail', None)
                if not error_detail:
                    # Try to parse error_detail from response if not already stored
                    try:
                        error_detail = e.response.json()
                    except Exception:
                        error_detail = None

                if error_detail and isinstance(error_detail, dict):
                    # v2 API error format: {"errors": [{"title": "...", "code": "...", ...}]}
                    errors = error_detail.get('errors', [])
                    is_already_exists = False
                    for error in errors:
                        error_title = error.get('title', '')
                        error.get('code', '')
                        # Check if error indicates folder already exists
                        if ('already exists' in error_title.lower() or
                            'duplicate' in error_title.lower() or
                            'same title' in error_title.lower()):
                            is_already_exists = True
                            break

                    if is_already_exists:
                        # Check for title conflict: folder with same title under DIFFERENT parent
                        print(f"  ℹ Folder '{title}' already exists, checking for conflicts...")

                        # Find ALL folders with this title
                        all_folders = self.find_folders_by_title_space_wide(title, root_page_id=root_page_id)

                        # Check if any exist under the expected parent (update candidate)
                        folder_under_expected_parent = None
                        folder_under_different_parent = None

                        for folder_id, actual_parent_id in all_folders:
                            if parent_id and str(actual_parent_id) == str(parent_id):
                                # Found under expected parent = update candidate
                                folder_under_expected_parent = (folder_id, actual_parent_id)
                            elif not parent_id and not actual_parent_id:
                                # Both root-level = update candidate
                                folder_under_expected_parent = (folder_id, actual_parent_id)
                            else:
                                # Found under different parent = conflict
                                folder_under_different_parent = (folder_id, actual_parent_id)

                        if folder_under_expected_parent:
                            # Update candidate - return existing folder
                            folder_id, _ = folder_under_expected_parent
                            print(f"  ✓ Found existing folder '{title}' under expected parent (ID: {folder_id})")
                            return folder_id, 'found'
                        elif folder_under_different_parent:
                            # Title conflict - folder exists under different parent
                            conflicting_id, conflicting_parent = folder_under_different_parent
                            print(f"  ✗ Title conflict: Folder '{title}' exists under different parent")
                            print(f"     Expected parent: {parent_id}, Found parent: {conflicting_parent}")
                            raise TitleConflictError(
                                f"Folder '{title}' already exists under a different parent. "
                                f"Expected parent: {parent_id}, Found parent: {conflicting_parent}. "
                                f"Add a .confluence-mapping.yaml file to resolve this conflict."
                            )
                        else:
                            # Folder exists but couldn't determine parent relationship
                            print(f"  ⚠ Folder '{title}' exists but parent relationship unclear")
                            return None, 'title_conflict'
            raise

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        """Get folder by ID using REST API v2."""
        try:
            response = self._make_request('GET', f'/folders/{folder_id}')
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise

    def delete_folder(self, folder_id: str) -> bool:
        """Delete folder using REST API v2."""
        try:
            self._make_request('DELETE', f'/folders/{folder_id}')
            return True
        except Exception as e:
            print(f"  ✗ Error deleting folder {folder_id}: {e}")
            return False

    def find_folder_by_title(
        self,
        title: str,
        space_id: str,
        parent_id: Optional[str] = None
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Find folder by title in space.

        Tries v2 API first, falls back to CQL search (v1) if v2 fails.

        Args:
            title: Folder title to search for
            space_id: Confluence space ID
            parent_id: Optional parent folder or page ID to limit search

        Returns:
            Tuple of (folder_id, parent_id) or None if not found
        """
        # NOTE: v2 `/folders` search endpoint returns 500 errors in Confluence Cloud (as of Jan 2026)
        # Skip v2 and go directly to CQL search which works reliably

        # Use CQL search (v1 API) - more reliable
        try:
            # Escape special characters in title for CQL
            escaped_title = title.replace('"', '\\"')
            cql = f'space = {self.space_key} AND type = folder AND title = "{escaped_title}"'

            url = f"{self.base_url}/rest/api/content/search"
            params = {'cql': cql, 'limit': 10, 'expand': 'ancestors'}

            response = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
            response.raise_for_status()
            results = response.json().get('results', [])

            for folder in results:
                folder_id = str(folder['id'])

                # Get parent from ancestors (last ancestor is direct parent)
                ancestors = folder.get('ancestors', [])
                folder_parent_id = None
                if ancestors:
                    # The last ancestor is the direct parent
                    folder_parent_id = str(ancestors[-1]['id'])

                parent_id_str = str(parent_id) if parent_id else None

                if parent_id:
                    # Check if this folder is under the specified parent
                    # Check all ancestors (folder could be nested deeper)
                    ancestor_ids = [str(a['id']) for a in ancestors]
                    if parent_id_str in ancestor_ids:
                        return (folder_id, folder_parent_id)
                else:
                    return (folder_id, folder_parent_id)

            # If parent_id specified but no exact match, return first result as fallback
            if parent_id and results:
                folder = results[0]
                ancestors = folder.get('ancestors', [])
                folder_parent_id = str(ancestors[-1]['id']) if ancestors else None
                return (str(folder['id']), folder_parent_id)

            return None
        except Exception as e:
            print(f"WARNING: Error searching for folder '{title}' via CQL: {e}")
            return None

    def find_folders_by_title_space_wide(
        self,
        title: str,
        root_page_id: Optional[str] = None
    ) -> List[Tuple[str, Optional[str]]]:
        """
        Find ALL folders with a given title in the space.

        Used for title conflict detection - checks if folders with same title
        exist under different parents.

        Args:
            title: Folder title to search for
            root_page_id: Optional root page ID - only return folders under this root

        Returns:
            List of tuples (folder_id, parent_id) for all matching folders
        """
        try:
            escaped_title = title.replace('"', '\\"')
            cql = f'space = {self.space_key} AND type = folder AND title = "{escaped_title}"'

            url = f"{self.base_url}/rest/api/content/search"
            params = {'cql': cql, 'limit': 100, 'expand': 'ancestors'}

            response = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
            response.raise_for_status()
            results = response.json().get('results', [])

            folders = []
            for folder in results:
                folder_id = str(folder['id'])

                # Get parent from ancestors
                ancestors = folder.get('ancestors', [])
                folder_parent_id = None
                if ancestors:
                    folder_parent_id = str(ancestors[-1]['id'])

                # Filter by root if specified
                if root_page_id:
                    ancestor_ids = [str(a['id']) for a in ancestors]
                    if str(root_page_id) not in ancestor_ids and str(folder_id) != str(root_page_id):
                        continue  # Not under root, skip

                folders.append((folder_id, folder_parent_id))

            return folders
        except Exception as e:
            print(f"WARNING: Error searching for folders '{title}' space-wide: {e}")
            return []

    def find_pages_by_title_space_wide(
        self,
        title: str,
        root_page_id: Optional[str] = None
    ) -> List[Tuple[str, Optional[str]]]:
        """
        Find ALL pages with a given title in the space.

        Used for title conflict detection - checks if pages with same title
        exist under different parents.

        Args:
            title: Page title to search for
            root_page_id: Optional root page ID - only return pages under this root

        Returns:
            List of tuples (page_id, parent_id) for all matching pages
        """
        try:
            escaped_title = title.replace('"', '\\"')
            cql = f'space = {self.space_key} AND type = page AND title = "{escaped_title}"'

            url = f"{self.base_url}/rest/api/content/search"
            params = {'cql': cql, 'limit': 100, 'expand': 'ancestors'}

            response = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
            response.raise_for_status()
            results = response.json().get('results', [])

            pages = []
            for page in results:
                page_id = str(page['id'])

                # Get parent from ancestors
                ancestors = page.get('ancestors', [])
                page_parent_id = None
                if ancestors:
                    page_parent_id = str(ancestors[-1]['id'])

                # Filter by root if specified
                if root_page_id:
                    ancestor_ids = [str(a['id']) for a in ancestors]
                    if str(root_page_id) not in ancestor_ids and str(page_id) != str(root_page_id):
                        continue  # Not under root, skip

                pages.append((page_id, page_parent_id))

            return pages
        except Exception as e:
            print(f"WARNING: Error searching for pages '{title}' space-wide: {e}")
            return []

    def update_folder(
        self,
        folder_id: str,
        title: Optional[str] = None,
        parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update a folder's title or parent using REST API v2.

        Args:
            folder_id: ID of folder to update
            title: New title (optional)
            parent_id: New parent ID (optional)

        Returns:
            Updated folder data
        """
        update_data = {}
        if title:
            update_data["title"] = title
        if parent_id:
            update_data["parentId"] = str(parent_id)

        response = self._make_request('PUT', f'/folders/{folder_id}', json=update_data)
        return response.json()

    def list_folder_children(
        self,
        folder_id: str,
        include_folders: bool = True,
        include_pages: bool = True
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        List children of a folder (folders and/or pages).

        Args:
            folder_id: Folder ID to list children for
            include_folders: Whether to include child folders
            include_pages: Whether to include child pages

        Returns:
            Tuple of (child_folders, child_pages)
        """
        child_folders = []
        child_pages = []

        # Get child folders using v2 API
        if include_folders:
            try:
                response = self._make_request('GET', f'/folders/{folder_id}/children/folders')
                data = response.json()
                child_folders = data.get('results', [])
            except Exception as e:
                print(f"WARNING: Could not list child folders for {folder_id}: {e}")

        # Get child pages using v2 API
        if include_pages:
            try:
                response = self._make_request('GET', f'/folders/{folder_id}/children/pages')
                data = response.json()
                child_pages = data.get('results', [])
            except Exception as e:
                print(f"WARNING: Could not list child pages for {folder_id}: {e}")

        return child_folders, child_pages

    def list_child_pages_under_parent(self, parent_id: str) -> List[Dict]:
        """
        List child pages under a parent (folder or page). Tries folder API first, then page API.

        Returns list of page dicts with at least 'id' and 'title'.
        """
        # Try folder children first
        try:
            response = self._make_request('GET', f'/folders/{parent_id}/children/pages')
            data = response.json()
            return data.get('results', [])
        except Exception:
            pass
        # Fall back to page children (e.g. root page)
        try:
            response = self._make_request('GET', f'/pages/{parent_id}/children')
            data = response.json()
            return data.get('results', [])
        except Exception:
            return []

    # ========== Page Operations (REST API v2) ==========

    def create_page_v2(
        self,
        title: str,
        body: str,  # Storage format content
        space_id: str,
        parent_id: Optional[str] = None  # Can be folder_id or page_id
    ) -> Tuple[str, int]:
        """
        Create a page using REST API v2.

        Args:
            title: Page title
            body: Storage format content
            space_id: Confluence space ID
            parent_id: Optional parent folder or page ID

        Returns:
            Tuple of (page_id, version)
        """
        page_data = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body
            }
        }

        if parent_id:
            page_data["parentId"] = str(parent_id)

        response = self._make_request('POST', '/pages', json=page_data)
        page = response.json()
        return str(page['id']), page['version']['number']

    def delete_page_v2(self, page_id: str) -> bool:
        """
        Delete a page using REST API v2.

        Args:
            page_id: ID of page to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self._make_request('DELETE', f'/pages/{page_id}')
            return True
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                # Page already deleted
                return True
            print(f"  ✗ Error deleting page {page_id}: {e}")
            return False

    # ========== Hierarchy Validation (REST API v2) ==========

    def _is_descendant_of_root(
        self,
        item_id: str,
        root_id: str,
        item_type: str = 'page'  # 'page' or 'folder'
    ) -> bool:
        """
        Check if a page or folder is a descendant of the root by walking up the parent chain.

        Args:
            item_id: ID of page or folder to check
            root_id: Root page/folder ID
            item_type: Type of item ('page' or 'folder')

        Returns:
            True if item is a descendant of root, False otherwise
        """
        if str(item_id) == str(root_id):
            return True

        visited = set()  # Prevent infinite loops
        current_id = item_id

        while current_id and current_id not in visited:
            visited.add(current_id)

            try:
                # Try to get parent ID - check both folder and page APIs
                parent_id = None

                # Try folder first (faster check)
                try:
                    folder_data = self.get_folder(current_id)
                    if folder_data:
                        parent_id = folder_data.get('parentId')
                except Exception:
                    pass

                # If not a folder, try page
                if parent_id is None:
                    try:
                        response = self._make_request('GET', f'/pages/{current_id}')
                        page_data = response.json()
                        parent_id = page_data.get('parentId')
                    except Exception:
                        pass

                if parent_id is None:
                    # No parent - reached root level, but not our root
                    return False

                if str(parent_id) == str(root_id):
                    return True

                # Move up the chain
                current_id = str(parent_id)

            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 404:
                    return False
                # For other errors, assume not a descendant
                return False
            except Exception:
                return False

        return False

    def validate_folder_hierarchy(
        self,
        folder_id: str,
        expected_parent_id: Optional[str],
        root_page_id: Optional[str],
        folder_path: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a folder is in the correct hierarchy location using REST API v2.

        Args:
            folder_id: Folder ID to validate
            expected_parent_id: Expected parent folder or page ID
            root_page_id: Root page ID for the destination
            folder_path: Folder path for error messages

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        try:
            folder_data = self.get_folder(folder_id)  # Uses v2
            if not folder_data:
                issues.append(f"Folder '{folder_path}' (ID: {folder_id}) not found")
                return False, issues

            current_parent_id = folder_data.get('parentId')

            # Check if parent matches expected
            if expected_parent_id:
                if current_parent_id != str(expected_parent_id):
                    issues.append(
                        f"Folder '{folder_path}' (ID: {folder_id}) has wrong parent: "
                        f"expected {expected_parent_id}, found {current_parent_id}"
                    )
            elif current_parent_id:
                issues.append(
                    f"Folder '{folder_path}' (ID: {folder_id}) should be root-level but has parent {current_parent_id}"
                )
        except Exception as e:
            issues.append(f"Could not validate hierarchy for folder '{folder_path}': {e}")

        return len(issues) == 0, issues

    def validate_page_hierarchy(
        self,
        page_id: str,
        expected_parent_id: Optional[str],  # Can be folder_id or page_id
        root_page_id: Optional[str],
        file_path: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a page is in the correct hierarchy location using REST API v2.
        Pages should be under folders (not under other pages, except root-level).

        Args:
            page_id: Page ID to validate
            expected_parent_id: Expected parent folder or page ID
            root_page_id: Root page ID for the destination
            file_path: File path for error messages

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        try:
            # Get page data using v2
            response = self._make_request('GET', f'/pages/{page_id}')
            page_data = response.json()
            current_parent_id = page_data.get('parentId')

            # Check if parent matches expected (can be folder or page)
            if expected_parent_id:
                if current_parent_id != str(expected_parent_id):
                    issues.append(
                        f"Page '{file_path}' (ID: {page_id}) has wrong parent: "
                        f"expected {expected_parent_id}, found {current_parent_id}"
                    )
            elif current_parent_id:
                issues.append(
                    f"Page '{file_path}' (ID: {page_id}) should be root-level but has parent {current_parent_id}"
                )
        except Exception as e:
            issues.append(f"Could not validate hierarchy for page '{file_path}': {e}")

        return len(issues) == 0, issues

    def find_page_by_title(self, title: str, parent_id: Optional[str] = None) -> Optional[str]:
        """
        Find a page by title under a specific parent using REST API v2.

        IMPORTANT: parent_id is required for safe lookup. Page titles are only unique
        within a parent, not across the entire space. Searching without a parent
        can return the wrong page if multiple pages share the same title.

        Args:
            title: Page title to search for
            parent_id: REQUIRED parent page ID to limit search (cannot safely search space-wide)

        Returns:
            Page ID if found under the specified parent, None otherwise
        """
        # REQUIRE parent_id - never search space-wide to avoid returning wrong page
        if not parent_id:
            return None

        cache_key = f"{parent_id}:{title}"
        if cache_key in self.page_cache:
            return self.page_cache[cache_key]

        try:
            # Use v2 pages endpoint with spaceId and title filter
            params = {
                'spaceId': self.space_id,
                'title': title,
                'limit': 100
            }

            # Use pagination helper for large result sets
            results = self._paginate_v2('/pages', params=params, max_results=1000)

            # Filter to pages under the specific parent
            for page in results:
                page_parent_id = page.get('parentId')
                if page_parent_id and str(page_parent_id) == str(parent_id):
                    page_id = str(page['id'])
                    self.page_cache[cache_key] = page_id
                    return page_id

            # Not found under this parent
            return None

        except Exception as e:
            print(f"WARNING: Error searching for page '{title}' under parent {parent_id}: {e}")
            print("  This may indicate a connectivity issue or the parent page may not exist.")

        return None

    def find_page_by_title_space_wide(
        self,
        title: str,
        expected_parent_id: Optional[str] = None,
        root_page_id: Optional[str] = None
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Search for a page by title across entire space using CQL (v1 API) - fallback only.

        WARNING: This method should only be used as a last resort when:
        - Page exists in Confluence but not in sync state
        - Parent-scoped search failed
        - "Already exists" error occurred during creation

        IMPORTANT: Only returns pages that are descendants of root_page_id (if provided).
        Pages outside the destination root hierarchy are ignored.

        Uses CQL search (v1 API) because v2 /pages endpoint has a bug where spaceId
        filter doesn't work correctly with title filter (returns pages from other spaces).

        Args:
            title: Page title to search for
            expected_parent_id: Optional expected parent ID for comparison
            root_page_id: Optional root page ID - only return pages under this root

        Returns:
            Tuple of (page_id, actual_parent_id) or None if not found
            actual_parent_id is None if page is root-level
        """
        print(f"  ⚠ WARNING: Performing space-wide search for page '{title}' (fallback only)")
        if root_page_id:
            print(f"    Only searching under destination root (ID: {root_page_id})")

        try:
            # Use CQL search (v1 API) - correctly filters by space, unlike v2 /pages
            escaped_title = title.replace('"', '\\"')
            cql = f'space = {self.space_key} AND type = page AND title = "{escaped_title}"'

            url = f"{self.base_url}/rest/api/content/search"
            params = {'cql': cql, 'limit': 25, 'expand': 'ancestors'}

            response = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
            response.raise_for_status()
            results = response.json().get('results', [])

            if not results:
                return None

            # Filter results to only include pages under root_page_id (if provided)
            valid_results = []
            for page in results:
                page_id = str(page.get('id'))

                # Get ancestors from expand (v1 API provides full ancestor list)
                ancestors = page.get('ancestors', [])
                ancestor_ids = [str(a['id']) for a in ancestors]

                # Get parent ID (last ancestor is direct parent)
                page_parent_id = str(ancestors[-1]['id']) if ancestors else None

                # If root_page_id is provided, page must be a descendant of it
                if root_page_id:
                    # Check if root_page_id is in the ancestor chain
                    # (v1 API expand=ancestors gives us full chain, no need to walk up)
                    if page_id == root_page_id:
                        valid_results.append((page_id, page_parent_id))
                    elif root_page_id in ancestor_ids:
                        valid_results.append((page_id, page_parent_id))
                    else:
                        # Page is outside destination root hierarchy - ignore it
                        print(f"    ✗ Page with title '{title}' exists in space but not under destination root {root_page_id}")
                        continue
                else:
                    # No root_page_id - accept all results (backward compatibility)
                    valid_results.append((page_id, page_parent_id))

            if not valid_results:
                return None

            if len(valid_results) > 1:
                print(f"  ⚠ WARNING: Multiple pages found with title '{title}' under root ({len(valid_results)} pages)")
                print("    Using first result. This may not be the correct page.")

            # Use first valid result
            page_id, actual_parent_id = valid_results[0]

            # Compare with expected parent if provided
            if expected_parent_id and actual_parent_id != expected_parent_id:
                print(f"  ⚠ WARNING: Page '{title}' found under different parent")
                print(f"    Expected: {expected_parent_id}, Found: {actual_parent_id}")
                print("    Page will be moved to correct parent during update")

            print(f"  ✓ Found page '{title}' (ID: {page_id}, parent: {actual_parent_id})")
            return (page_id, actual_parent_id)

        except Exception as e:
            print(f"  ⚠ ERROR: Could not perform space-wide search for page '{title}': {e}")
            return None

    def find_or_create_page(
        self,
        file_path: str,
        title: str,
        title_original: str,
        storage_format: str,
        content_hash: str,
        parent_id: Optional[str],
        sync_state_entry: Optional[Dict[str, Any]],
        previous_content_hash: Optional[str] = None,
        previous_parent_id: Optional[str] = None,
        previous_title: Optional[str] = None,
        previous_version: Optional[int] = None,
        root_page_id: Optional[str] = None
    ) -> Tuple[str, str, Optional[int], str]:
        """
        Unified method to find or create a page using file_path-only lookup.

        Lookup hierarchy:
        1. Check sync state (by file_path) - use stored page_id if found
        2. If not in sync state, attempt creation with title suffix sequence if needed

        Args:
            file_path: File path (used for sync state lookup and error messages)
            title: Page title to use (may be modified from original)
            title_original: Original page title from Markdown (for tracking)
            storage_format: Pre-computed Confluence storage format
            content_hash: Content hash for change detection
            parent_id: Optional parent page ID
            sync_state_entry: Optional sync state entry (from get_page_history)
            previous_content_hash: Previous content hash for quick drift detection
            previous_parent_id: Previous parent page ID (to detect parent changes)
            previous_title: Previous page title (to detect title changes)
            previous_version: Previous page version number (to detect version conflicts)
            root_page_id: Optional root page ID for hierarchy validation

        Returns:
            Tuple of (page_id, status, version, actual_title_used)
            status: 'found', 'created', 'updated', 'skipped'
            actual_title_used: The title that was actually used in Confluence (may have suffix)
            Never returns None for page_id - always returns a valid page_id
        """
        existing_id = None
        status = 'unknown'
        version = None
        actual_title_used = title  # Default to provided title

        # Step 1: Check sync state first (path-based lookup) - PRIMARY METHOD
        if sync_state_entry and sync_state_entry.get('page_id'):
            existing_id = sync_state_entry['page_id']
            status = 'found'
            # Get actual title from sync state (what's currently in Confluence)
            actual_title_used = sync_state_entry.get('page_title', title)
            # Verify the page still exists and get current version
            try:
                response = self._make_request('GET', f'/pages/{existing_id}')
                current_data = response.json()
                version = current_data['version']['number']
            except requests.exceptions.HTTPError as e:
                # Check if it's a 404 (page deleted) or other error
                # Note: e.response might be consumed/falsy, so check status_code directly
                status_code = None
                if e.response is not None:
                    try:
                        status_code = e.response.status_code
                    except Exception:
                        pass
                # Also check the exception string for 404
                if status_code == 404 or (status_code is None and '404' in str(e)):
                    # Page was deleted - clear existing_id and create new page
                    print(f"  ⚠ Page ID {existing_id} from sync state no longer exists (404), will create new page")
                    existing_id = None
                    status = 'unknown'
                    actual_title_used = title  # Reset to provided title
                else:
                    # Other HTTP error - re-raise
                    raise
            except Exception as e:
                # Other exception - log and clear existing_id to be safe
                print(f"  ⚠ Error verifying page ID {existing_id} from sync state: {e}, will create new page")
                existing_id = None
                status = 'unknown'
                actual_title_used = title  # Reset to provided title

        # Step 2: If we have an existing_id, check if update is needed
        if existing_id:
            # Check if content, parent, or title changed
            needs_update = False

            # First, try quick hash-based comparison if we have previous_content_hash
            if previous_content_hash and content_hash == previous_content_hash:
                # Content hash matches - check only parent and title
                try:
                    response = self._make_request('GET', f'/pages/{existing_id}')
                    current_data = response.json()
                    version = current_data['version']['number']
                    current_title = current_data.get('title', '')
                    current_parent_id = current_data.get('parentId')
                    current_parent_id = current_parent_id if current_parent_id else None
                    new_parent_id = str(parent_id) if parent_id else None

                    # Check if parent changed
                    parent_changed = current_parent_id != new_parent_id

                    # Check if title changed
                    title_changed = current_title != title

                    if parent_changed or title_changed:
                        needs_update = True
                        if title_changed:
                            print(f"  ℹ Title changed: '{current_title}' → '{title}'")
                        if parent_changed:
                            print(f"  ℹ Parent changed: {current_parent_id} → {new_parent_id}")
                    else:
                        # Nothing changed - skip
                        status = 'skipped'
                        return existing_id, status, version, actual_title_used
                except requests.exceptions.HTTPError as e:
                    # Check if it's a 404 (page deleted)
                    status_code = None
                    if e.response is not None:
                        try:
                            status_code = e.response.status_code
                        except Exception:
                            pass
                    # Also check the exception string for 404
                    if status_code == 404 or (status_code is None and '404' in str(e)):
                        # Page was deleted - clear existing_id and create new page instead
                        print(f"  ⚠ Page ID {existing_id} no longer exists (404), will create new page")
                        existing_id = None
                        status = 'unknown'
                        actual_title_used = title
                        # Break out of the if existing_id block - fall through to creation step
                    else:
                        # Other HTTP error - try to update anyway
                        print(f"  ⚠ Could not check current page state: {e}")
                        needs_update = True  # Assume update needed if we can't check
                except Exception as e:
                    # If we can't check, fall through to full comparison
                    print(f"  ⚠ Could not check page state for hash comparison: {e}")
                    needs_update = True
            else:
                # No previous hash or hash mismatch - do full comparison
                try:
                    current_data = self._get_page(existing_id, include_body=True)
                    version = current_data['version']['number']
                    current_content = self._page_storage_body(current_data)
                    current_title = current_data.get('title', '')

                    # Get current parent ID
                    current_parent_id = current_data.get('parentId')
                    current_parent_id = current_parent_id if current_parent_id else None
                    new_parent_id = str(parent_id) if parent_id else None

                    # Compute hash of current content for comparison
                    from confluence_sync.sync_state import compute_content_hash
                    current_content_hash = compute_content_hash(current_content)

                    # Check if content changed (using hash comparison)
                    content_changed = current_content_hash != content_hash

                    # Check if parent changed
                    parent_changed = current_parent_id != new_parent_id

                    # Check if title changed
                    title_changed = current_title != title

                    if content_changed or parent_changed or title_changed:
                        needs_update = True
                        if content_changed:
                            print(f"  ℹ Content changed (hash: {current_content_hash[:8]} → {content_hash[:8]})")
                        if title_changed:
                            print(f"  ℹ Title changed: '{current_title}' → '{title}'")
                        if parent_changed:
                            print(f"  ℹ Parent changed: {current_parent_id} → {new_parent_id}")
                    else:
                        # Nothing changed - skip
                        status = 'skipped'
                        return existing_id, status, version, actual_title_used
                except requests.exceptions.HTTPError as e:
                    # Check if it's a 404 (page deleted)
                    status_code = None
                    if e.response is not None:
                        try:
                            status_code = e.response.status_code
                        except Exception:
                            pass
                    # Also check the exception string for 404
                    if status_code == 404 or (status_code is None and '404' in str(e)):
                        # Page was deleted - clear existing_id and create new page instead
                        print(f"  ⚠ Page ID {existing_id} no longer exists (404), will create new page")
                        existing_id = None
                        status = 'unknown'
                        actual_title_used = title
                        # Break out of the if existing_id block - fall through to creation step
                    else:
                        # Other HTTP error - try to update anyway
                        print(f"  ⚠ Could not check current page state: {e}")
                        needs_update = True  # Assume update needed if we can't check
                except Exception as e:
                    print(f"  ⚠ Could not check current page state: {e}")
                    needs_update = True  # Assume update needed if we can't check

            # Perform update if needed (only if existing_id is still set)
            if existing_id and needs_update:
                try:
                    status = 'updated'
                    page_id, update_status, new_version, updated_title = self._update_page(
                        existing_id, title, title_original, storage_format, content_hash, parent_id,
                        previous_content_hash, previous_parent_id, previous_title, previous_version,
                        sync_state_entry
                    )
                    return page_id, status, new_version, updated_title
                except Exception as update_error:
                    # Check if update failed because page was deleted (404)
                    error_str = str(update_error)
                    if '404' in error_str or 'no longer exists' in error_str.lower():
                        # Page was deleted - clear existing_id and create new page
                        print(f"  ⚠ Page ID {existing_id} was deleted during update (404), will create new page")
                        existing_id = None
                        status = 'unknown'
                        actual_title_used = title
                        # Fall through to creation step
                    else:
                        # Other error - re-raise
                        raise
            elif existing_id:
                status = 'skipped'
                return existing_id, status, version, actual_title_used
            # If existing_id is None (page was deleted), fall through to creation step

        # Step 3: No existing page found - attempt creation (single attempt, no suffixing)
        if not existing_id:
            print(f"  ℹ No existing page found for '{file_path}', creating new page with title '{title}'")

            try:
                # Create page with original title using REST API v2
                page_id, version = self.create_page_v2(
                    title=title,
                    body=storage_format,
                    space_id=self.space_id,
                    parent_id=parent_id  # Can be folder_id or page_id
                )

                # Validate page hierarchy after creation (Phase 7)
                if root_page_id:
                    is_valid, issues = self.validate_page_hierarchy(
                        page_id=page_id,
                        expected_parent_id=parent_id,
                        root_page_id=root_page_id,
                        file_path=file_path
                    )
                    if not is_valid:
                        print(f"  ⚠ Hierarchy validation issues for page '{title}': {issues}")
                        # Don't fail - just warn

                return page_id, 'created', version, title
            except requests.exceptions.HTTPError as create_error:
                # Check if "already exists" error
                status_code = None
                error_message = ''
                error_data = None

                if create_error.response is not None:
                    try:
                        status_code = create_error.response.status_code
                    except Exception:
                        status_code = None

                    # Get error detail stored by _make_request
                    if hasattr(create_error.response, '_error_detail'):
                        error_data = getattr(create_error.response, '_error_detail', None)
                    else:
                        try:
                            error_data = create_error.response.json()
                        except Exception:
                            error_data = {}

                    # Extract error message from v2 API error structure
                    if isinstance(error_data, dict):
                        # v2 API uses 'errors' array with 'title' and optional 'detail'
                        errors_list = error_data.get('errors', [])
                        if errors_list and isinstance(errors_list[0], dict):
                            first = errors_list[0]
                            error_message = first.get('title', '') or ''
                            if first.get('detail'):
                                error_message = f"{error_message} — {first.get('detail')}"
                        elif errors_list:
                            error_message = str(errors_list[0])
                        else:
                            error_message = error_data.get('message', '') or error_data.get('data', {}).get('message', '')
                    else:
                        error_message = ''

                if not error_message:
                    error_message = str(create_error)

                # Check if "already exists" error
                error_lower = error_message.lower()
                is_already_exists = (
                    status_code == 400 and (
                        'already exists' in error_lower or
                        'same title' in error_lower or
                        'page already exists' in error_lower
                    )
                )

                if is_already_exists:
                    # Check for title conflict: page with same title under DIFFERENT parent
                    print(f"  ℹ Page '{title}' already exists, checking for conflicts...")

                    # Find ALL pages with this title
                    all_pages = self.find_pages_by_title_space_wide(title, root_page_id=root_page_id)

                    # Check if any exist under the expected parent (update candidate)
                    page_under_expected_parent = None
                    page_under_different_parent = None

                    for page_id, actual_parent_id in all_pages:
                        if parent_id and str(actual_parent_id) == str(parent_id):
                            # Found under expected parent = update candidate
                            page_under_expected_parent = (page_id, actual_parent_id)
                        elif not parent_id and not actual_parent_id:
                            # Both root-level = update candidate
                            page_under_expected_parent = (page_id, actual_parent_id)
                        else:
                            # Found under different parent = conflict
                            page_under_different_parent = (page_id, actual_parent_id)

                    if page_under_expected_parent:
                        # Update candidate - return existing page
                        existing_page_id, _ = page_under_expected_parent
                        print(f"  ✓ Found existing page '{title}' under expected parent (ID: {existing_page_id})")
                        try:
                            response = self._make_request('GET', f'/pages/{existing_page_id}')
                            current_data = response.json()
                            version = current_data['version']['number']
                            return existing_page_id, 'found', version, title
                        except Exception as e:
                            print(f"  ⚠ Could not get version for existing page: {e}")
                            return existing_page_id, 'found', None, title
                    elif page_under_different_parent:
                        # Title conflict - page exists under different parent
                        conflicting_id, conflicting_parent = page_under_different_parent
                        print(f"  ✗ Title conflict: Page '{title}' exists under different parent")
                        print(f"     Expected parent: {parent_id}, Found parent: {conflicting_parent}")
                        raise TitleConflictError(
                            f"Page '{title}' already exists under a different parent. "
                            f"Expected parent: {parent_id}, Found parent: {conflicting_parent}. "
                            f"Add a .confluence-mapping.yaml file to resolve this conflict. "
                            f"File: '{file_path}'"
                        ) from create_error
                    else:
                        # No page found under expected parent - check if a FOLDER has this title
                        # (Confluence may disallow page and folder with same title)
                        all_folders = self.find_folders_by_title_space_wide(title, root_page_id=root_page_id)
                        if all_folders:
                            folder_id, folder_parent = all_folders[0]
                            print(f"  ✗ A folder with title '{title}' already exists (ID: {folder_id}, parent: {folder_parent})")
                            raise TitleConflictError(
                                f"A folder with title '{title}' already exists. "
                                f"Confluence does not allow a page to have the same title as a folder in this context. "
                                f"Use a .confluence-mapping.yaml file to give this page a different title. File: '{file_path}'"
                            ) from create_error
                        print(f"  ✗ Page with title '{title}' exists in space but could not be found under the expected parent hierarchy")
                        raise TitleConflictError(
                            f"Title conflict: A page with title '{title}' already exists in the space, "
                            f"but could not be found under the expected parent hierarchy. "
                            f"This may indicate a page exists outside the destination root. "
                            f"File: '{file_path}'"
                        ) from create_error
                else:
                    # Other 400 (or non-400) - re-raise with API detail so report shows real reason
                    if status_code == 400 and error_message and error_message != str(create_error):
                        raise Exception(
                            f"400 Bad Request: {error_message}"
                        ) from create_error
                    raise

    def _update_page(
        self,
        page_id: str,
        title: str,
        title_original: str,
        storage_format: str,
        content_hash: str,
        parent_id: Optional[str],
        previous_content_hash: Optional[str] = None,
        previous_parent_id: Optional[str] = None,
        previous_title: Optional[str] = None,
        previous_version: Optional[int] = None,
        sync_state_entry: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, Optional[int], str]:
        """
        Update an existing page in Confluence using REST API v2.

        Returns:
            Tuple of (page_id, status, version, actual_title_used)
            status: 'updated' or 'skipped'
            actual_title_used: The title that was actually used in Confluence
        """
        # Determine which title to use for update
        # If we have sync state, use the actual title currently in Confluence
        # If local title changed, try new title
        title_to_use = title
        if sync_state_entry:
            current_title_in_confluence = sync_state_entry.get('page_title', title)
            # If local title changed from what's in Confluence, try new title
            if title != current_title_in_confluence:
                title_to_use = title  # Try new title
            else:
                title_to_use = current_title_in_confluence  # Use existing title

        try:
            # Get current page data using v2
            response = self._make_request('GET', f'/pages/{page_id}')
            page_data = response.json()
            version = page_data['version']['number']

            # Check for version conflict
            if previous_version is not None and version != previous_version:
                print(f"  ⚠ Warning: Version conflict detected for page ID {page_id}")
                print(f"    Expected version {previous_version}, found {version}")
                print("    Page was modified in Confluence since last sync. Proceeding with update (last-write-wins).")

            # Prepare update with title_to_use
            update_data = {
                "id": page_id,
                "status": "current",
                "title": title_to_use,
                "version": {"number": version + 1},
                "body": {
                    "representation": "storage",
                    "value": storage_format
                }
            }

            if parent_id:
                update_data["parentId"] = str(parent_id)

            # Perform update using PUT /pages/{id}
            response = self._make_request('PUT', f'/pages/{page_id}', json=update_data)
            updated_page = response.json()

            # Validate page hierarchy after update if parent changed (Phase 7)
            # Note: We don't have root_page_id in this method, so skip validation here
            # Hierarchy validation should be done at the sync level if needed

            return page_id, 'updated', updated_page['version']['number'], title_to_use

        except requests.exceptions.HTTPError as e:
            # Check if it's a 404 (page deleted)
            if e.response and e.response.status_code == 404:
                # Page was deleted - cannot update, raise exception to trigger creation
                raise PageNotFoundError(
                    f"Page ID {page_id} no longer exists (404). Cannot update deleted page."
                ) from e

            # Check if it's a 403 (permission denied)
            if e.response and e.response.status_code == 403:
                try:
                    error_detail = e.response.json()
                    error_msg = error_detail.get('message', 'Forbidden')
                except Exception:
                    error_msg = 'Forbidden'
                raise Exception(
                    f"Cannot update page ID {page_id} (title: '{title_to_use}'): {error_msg}. "
                    f"Page may be archived or you may not have permission."
                ) from e

            # Check if it's a title conflict (400)
            if e.response and e.response.status_code == 400:
                error_data = getattr(e.response, '_error_detail', None)
                if not error_data:
                    try:
                        error_data = e.response.json()
                    except Exception:
                        error_data = {}

                # Extract error message from v2 API error structure
                if isinstance(error_data, dict):
                    # v2 API uses 'errors' array with 'title' field
                    errors_list = error_data.get('errors', [])
                    if errors_list and isinstance(errors_list, list):
                        error_msg = errors_list[0].get('title', '') if isinstance(errors_list[0], dict) else ''
                    else:
                        error_msg = error_data.get('message', '')
                else:
                    error_msg = str(e)

                if not error_msg:
                    error_msg = str(e)

                error_lower = error_msg.lower()

                is_title_conflict = (
                    'already exists' in error_lower or
                    'same title' in error_lower or
                    'page already exists' in error_lower
                )

                if is_title_conflict:
                    raise TitleConflictError(
                        f"Title conflict when updating page '{title_to_use}' (ID: {page_id}): "
                        f"A page with this title already exists"
                    ) from e
                else:
                    raise Exception(
                        f"Failed to update page ID {page_id} (title: '{title_to_use}'): {error_msg}"
                    ) from e

            # Re-raise other HTTP errors
            raise

    def create_or_update_page_from_storage(
        self,
        title: str,
        storage_format: str,
        content_hash: str,
        parent_id: Optional[str] = None,
        existing_id: Optional[str] = None,
        previous_content_hash: Optional[str] = None,
        previous_parent_id: Optional[str] = None,
        previous_title: Optional[str] = None,
        previous_version: Optional[int] = None,
        file_path: Optional[str] = None
    ) -> Tuple[str, str, Optional[str], Optional[int]]:
        """
        Create or update a page in Confluence using pre-computed storage format.

        DEPRECATED: This method is kept for backward compatibility. New code should use
        find_or_create_page() which implements the proper lookup hierarchy.

        Args:
            title: Page title
            storage_format: Pre-computed Confluence storage format
            content_hash: Content hash for change detection
            parent_id: Optional parent page ID
            existing_id: Optional existing page ID
            previous_content_hash: Previous content hash for quick drift detection
            previous_parent_id: Previous parent page ID (to detect parent changes)
            previous_title: Previous page title (to detect title changes)
            previous_version: Previous page version number (to detect version conflicts)
            file_path: Optional file path (for better error messages)

        Returns:
            Tuple of (page_id, status, content_hash, version)
        """
        # Construct sync_state_entry from existing_id if provided
        sync_state_entry = None
        if existing_id:
            sync_state_entry = {
                'page_id': existing_id,
                'content_hash': previous_content_hash,
                'parent_id': previous_parent_id,
                'page_title': previous_title,
                'version': previous_version
            }

        # Use file_path if provided, otherwise use title as fallback
        lookup_file_path = file_path if file_path else title

        # Delegate to find_or_create_page() which implements the proper lookup hierarchy
        try:
            page_id, status, version = self.find_or_create_page(
                file_path=lookup_file_path,
                title=title,
                storage_format=storage_format,
                content_hash=content_hash,
                parent_id=parent_id,
                sync_state_entry=sync_state_entry,
                previous_content_hash=previous_content_hash,
                previous_parent_id=previous_parent_id,
                previous_title=previous_title,
                previous_version=previous_version,
                root_page_id=None  # create_or_update_page_from_storage doesn't have root_page_id context
            )
            return page_id, status, content_hash, version
        except (ParentPageNotFoundError, DuplicateTitleError, PageNotFoundError):
            # Re-raise custom exceptions as-is
            raise
        except Exception as e:
            # Wrap other exceptions with context
            raise Exception(
                f"Failed to create or update page '{title}'"
                + (f" (file: '{file_path}')" if file_path else "")
                + f": {e}"
            ) from e

    def delete_page(self, page_id: str) -> bool:
        """
        Delete a page from Confluence (uses v2 API).

        Args:
            page_id: Confluence page ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        return self.delete_page_v2(page_id)

    def sync_prepared_content_parallel(
        self,
        prepared_contents: List[PreparedContent],
        parallel_threads: int = 5,
        progress_callback: Optional[Callable[[int, str, Optional[str]], None]] = None,
        root_page_id: Optional[str] = None,
        force_update: bool = False
    ) -> List[SyncResult]:
        """
        Sync prepared content to Confluence using parallel processing.

        Pages are synced concurrently using ThreadPoolExecutor for faster performance.
        This is especially beneficial for large syncs (1000+ files).

        Args:
            prepared_contents: List of PreparedContent objects to sync
            parallel_threads: Number of parallel threads to use (default: 5, recommended: 8-12)
            progress_callback: Optional callback function for progress updates
            root_page_id: Root page ID for ancestry validation
            force_update: If True, force update all pages even if content unchanged

        Returns:
            List of SyncResult objects for each synced file
        """
        """
        Sync prepared content to Confluence in parallel threads.

        Args:
            prepared_contents: List of PreparedContent objects to sync
            parallel_threads: Number of parallel threads to use
            progress_callback: Optional callback(current_count, file_display, status)

        Returns:
            List of SyncResult objects
        """
        results: List[SyncResult] = []
        lock = threading.Lock()
        completed_count = [0]

        # If force_update is True, set force_sync on all prepared items
        if force_update:
            for prepared in prepared_contents:
                prepared.force_sync = True

        def sync_single(prepared: PreparedContent) -> Optional[SyncResult]:
            """Sync a single prepared content item."""
            try:
                prepared.status = 'syncing'

                # Get previous values from history
                previous_title = None
                previous_version = None
                previous_parent_id = None
                if prepared.prev_history:
                    previous_title = prepared.prev_history.get('page_title')
                    previous_version = prepared.prev_history.get('version')
                    previous_parent_id = prepared.prev_history.get('parent_id')

                # Use unified lookup method which implements the proper hierarchy
                page_id, status, version, actual_title_used = self.find_or_create_page(
                    file_path=prepared.file_key,
                    title=prepared.title,
                    title_original=prepared.title,  # Original title from Markdown
                    storage_format=prepared.storage_format,
                    content_hash=prepared.content_hash,
                    parent_id=prepared.parent_id,
                    sync_state_entry=prepared.prev_history,
                    previous_content_hash=None if prepared.force_sync else (prepared.prev_history.get('content_hash') if prepared.prev_history else None),
                    previous_parent_id=previous_parent_id,
                    previous_title=previous_title,
                    previous_version=previous_version,
                    root_page_id=root_page_id
                )

                # Store actual title used for sync state
                prepared.actual_title_used = actual_title_used

                prepared.status = 'synced'
                prepared.sync_status = status
                prepared.page_id = page_id
                prepared.version = version

                # Ensure page_id is never None
                if not page_id:
                    raise Exception(
                        f"Page '{prepared.title}' (file: '{prepared.file_key}') was processed but no page_id was returned. "
                        f"This should not happen."
                    )

                # Upload attachments if any
                if hasattr(prepared, 'image_paths') and prepared.image_paths:
                    pass
                    # Note: attachment_handler should be passed to ConfluenceSync or accessed differently
                    # For now, we'll handle this in the sync-to-confluence.py after page creation

                confluence_url = f"{self.base_url}/pages/viewpage.action?pageId={page_id}"
                result = SyncResult(
                    file_path=prepared.rel_path,
                    source_folder=prepared.source_folder,
                    status=status,
                    page_id=page_id,
                    page_title=prepared.title,
                    confluence_url=confluence_url,
                    github_url=prepared.github_url,
                    old_commit=prepared.prev_history.get('last_sync_commit') if prepared.prev_history else None,
                    old_date=prepared.prev_history.get('last_sync_date') if prepared.prev_history else None,
                    new_commit=prepared.commit_hash,
                    new_date=prepared.commit_date,
                    content_hash=prepared.content_hash
                )
                prepared.sync_result = result
                return result

            except Exception as e:
                prepared.status = 'failed'
                prepared.error = str(e)
                result = SyncResult(
                    file_path=prepared.rel_path,
                    source_folder=prepared.source_folder,
                    status='error',
                    error_message=str(e)
                )
                prepared.sync_result = result
                return result
            finally:
                with lock:
                    completed_count[0] += 1
                    if progress_callback:
                        file_display = prepared.rel_path if len(prepared.rel_path) <= 60 else "..." + prepared.rel_path[-57:]
                        status_display = prepared.sync_status or prepared.status
                        progress_callback(completed_count[0], file_display, status_display if status_display in ['skipped', 'created', 'updated'] else None)

        # Sync in parallel
        # Use shorter polling interval to check progress frequently
        # Set overall timeout: 30 minutes max for entire sync
        polling_interval = 30  # Check every 30 seconds
        overall_timeout = 1800  # 30 minutes total
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            future_to_prepared = {executor.submit(sync_single, prep): prep for prep in prepared_contents}

            remaining_futures = set(future_to_prepared.keys())
            last_progress_time = start_time

            while remaining_futures:
                # Check if overall timeout exceeded
                elapsed = time.time() - start_time
                if elapsed > overall_timeout:
                    print(f"  ⚠ Overall timeout exceeded ({overall_timeout}s). Marking {len(remaining_futures)} remaining file(s) as timed out.")
                    for future in remaining_futures:
                        prepared = future_to_prepared[future]
                        print(f"  ✗ Timeout syncing {prepared.rel_path} (overall timeout exceeded)")
                        result = SyncResult(
                            file_path=prepared.rel_path,
                            source_folder=prepared.source_folder,
                            status='error',
                            error_message=f"Timeout: overall sync exceeded {overall_timeout}s"
                        )
                        results.append(result)
                        future.cancel()
                    break

                # Wait for at least one future to complete, with short polling interval
                done, not_done = wait(remaining_futures, timeout=polling_interval, return_when='FIRST_COMPLETED')

                # Process completed futures
                for future in done:
                    prepared = future_to_prepared[future]
                    try:
                        result = future.result()  # Should complete immediately since it's done
                        if result:
                            results.append(result)
                    except Exception as e:
                        print(f"  ✗ Error syncing {prepared.rel_path}: {e}")
                        result = SyncResult(
                            file_path=prepared.rel_path,
                            source_folder=prepared.source_folder,
                            status='error',
                            error_message=str(e)
                        )
                        results.append(result)

                # Update remaining futures
                remaining_futures = not_done

                # Print progress periodically
                current_time = time.time()
                if done or (current_time - last_progress_time) > 60:
                    completed = len(prepared_contents) - len(remaining_futures)
                    print(f"  Progress: {completed}/{len(prepared_contents)} files completed ({elapsed:.0f}s elapsed)")
                    last_progress_time = current_time

        return results

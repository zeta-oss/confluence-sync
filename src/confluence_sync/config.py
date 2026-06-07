"""
Configuration loader for destination-based Confluence sync.

Loads and validates destination configurations from YAML files.

See ADR 0020: Config discovery precedence (--config → P1 → P2).
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class ConfigError(Exception):
    """Configuration error with user-friendly message."""
    pass


def load_destination_config(
    config_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load destination configuration from YAML file.

    Args:
        config_path: Path to config file (already resolved by paths.resolve_config_path)
        project_root: Project root for validating folder paths (required)

    Returns:
        Configuration dictionary

    Raises:
        ConfigError: If config file is invalid, missing, or destinations invalid
    """
    if config_path is None or not Path(config_path).exists():
        hint = ""
        if config_path:
            hint = f"\nExpected at: {config_path}"
        raise ConfigError(
            f"Configuration file not found.{hint}\n"
            "Run `confluence-sync init` to create a configuration file."
        )

    config_path = Path(config_path).resolve()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise ConfigError(f"Error reading config file: {e}")

    if not isinstance(config, dict):
        raise ConfigError("Config file must contain a YAML dictionary")

    if "destinations" not in config:
        raise ConfigError("Config file must contain a 'destinations' key")

    if not isinstance(config["destinations"], list):
        raise ConfigError("'destinations' must be a list")

    if len(config["destinations"]) == 0:
        raise ConfigError("At least one destination must be configured")

    # Validate each destination
    if project_root is not None:
        repo_root = Path(project_root).resolve()
    else:
        repo_root = Path.cwd()

    for idx, dest in enumerate(config["destinations"]):
        try:
            validate_destination_config(dest, repo_root)
        except ConfigError as e:
            raise ConfigError(f"Destination {idx + 1} is invalid: {e}")

    return config


def get_destination(config: Dict[str, Any], destination_id: str) -> Dict[str, Any]:
    """
    Get a specific destination configuration by ID.

    Raises:
        ConfigError: If destination ID not found
    """
    for dest in config.get("destinations", []):
        if dest.get("id") == destination_id:
            return dest

    available = [d.get("id") for d in config.get("destinations", []) if d.get("id")]
    raise ConfigError(
        f"Destination '{destination_id}' not found.\n"
        f"Available destinations: {', '.join(available) if available else 'none'}"
    )


def validate_destination_config(destination: Dict[str, Any], repo_root: Path) -> None:
    """
    Validate a destination configuration.

    Raises:
        ConfigError: If configuration is invalid
    """
    required_fields = ["id", "name", "confluence", "source", "credentials"]
    for field in required_fields:
        if field not in destination:
            raise ConfigError(f"Missing required field: {field}")

    dest_id = destination["id"]
    if not isinstance(dest_id, str) or not dest_id.strip():
        raise ConfigError("'id' must be a non-empty string")

    if not isinstance(destination["name"], str) or not destination["name"].strip():
        raise ConfigError("'name' must be a non-empty string")

    confluence = destination["confluence"]
    if not isinstance(confluence, dict):
        raise ConfigError("'confluence' must be a dictionary")

    for field in ["url", "space_key", "root_page_title"]:
        if field not in confluence:
            raise ConfigError(f"Missing required confluence field: {field}")
        if not isinstance(confluence[field], str) or not confluence[field].strip():
            raise ConfigError(f"'confluence.{field}' must be a non-empty string")

    source = destination["source"]
    if not isinstance(source, dict):
        raise ConfigError("'source' must be a dictionary")

    if "folders" not in source or not isinstance(source["folders"], list):
        raise ConfigError("'source.folders' must be a list")

    if len(source["folders"]) == 0:
        raise ConfigError("At least one folder must be specified in 'source.folders'")

    for idx, folder in enumerate(source["folders"]):
        if not isinstance(folder, dict):
            raise ConfigError(f"'source.folders[{idx}]' must be a dictionary")

        if "path" not in folder:
            raise ConfigError(f"'source.folders[{idx}].path' is required")

        folder_path = Path(folder["path"])
        if folder_path.is_absolute():
            raise ConfigError(
                f"'source.folders[{idx}].path' must be a relative path (no ../sibling-repo)"
            )

        # Reject paths that escape the project root (ADR 0018)
        resolved = (repo_root / folder_path).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            raise ConfigError(
                f"'source.folders[{idx}].path' ({folder['path']}) escapes the project root. "
                "Each content repo must have its own .confluence-sync/confluence-sync.yml."
            )

        if not resolved.exists():
            raise ConfigError(f"Folder not found: {folder['path']}")

        if not resolved.is_dir():
            raise ConfigError(f"Not a directory: {folder['path']}")

        if "create_root_parent" in folder:
            if not isinstance(folder["create_root_parent"], bool):
                raise ConfigError(f"'source.folders[{idx}].create_root_parent' must be a boolean")

        if "title" in folder:
            if not isinstance(folder["title"], str) or not folder["title"].strip():
                raise ConfigError(f"'source.folders[{idx}].title' must be a non-empty string")

    options = destination.get("options", {})
    if not isinstance(options, dict):
        raise ConfigError("'options' must be a dictionary")

    if "force_sync_paths" in options:
        if not isinstance(options["force_sync_paths"], list):
            raise ConfigError("'options.force_sync_paths' must be a list")
        for idx, path in enumerate(options["force_sync_paths"]):
            if not isinstance(path, str) or not path.strip():
                raise ConfigError(f"'options.force_sync_paths[{idx}]' must be a non-empty string")

    if "parallel_threads" in options:
        if not isinstance(options["parallel_threads"], int):
            raise ConfigError("'options.parallel_threads' must be an integer")
        if not 1 <= options["parallel_threads"] <= 50:
            raise ConfigError("'options.parallel_threads' must be between 1 and 50")

    credentials = destination["credentials"]
    if not isinstance(credentials, dict):
        raise ConfigError("'credentials' must be a dictionary")

    if "username" not in credentials or not isinstance(credentials["username"], str) or not credentials["username"].strip():
        raise ConfigError("'credentials.username' must be a non-empty string")

    if "token_env_var" not in credentials or not isinstance(credentials["token_env_var"], str) or not credentials["token_env_var"].strip():
        raise ConfigError("'credentials.token_env_var' must be a non-empty string")

    if "add_git_metadata" in options:
        if not isinstance(options["add_git_metadata"], bool):
            raise ConfigError("'options.add_git_metadata' must be a boolean")

    if "github_repo_override" in options:
        if options["github_repo_override"] is not None:
            if not isinstance(options["github_repo_override"], str):
                raise ConfigError("'options.github_repo_override' must be a string or null")

    if "dry_run" in options:
        if not isinstance(options["dry_run"], bool):
            raise ConfigError("'options.dry_run' must be a boolean")


def resolve_credentials(destination: Dict[str, Any]) -> Dict[str, str]:
    """
    Resolve credentials from environment variables.

    Returns:
        Dictionary with 'username' and 'token'

    Raises:
        ConfigError: If credentials cannot be resolved
    """
    credentials = destination["credentials"]
    username = credentials["username"]
    token_env_var = credentials["token_env_var"]

    token = os.getenv(token_env_var)
    if not token:
        raise ConfigError(
            f"API token not found in environment variable '{token_env_var}'.\n"
            f"Set it in ~/.local/confluence-sync/.env: {token_env_var}=your-token\n"
            f"Or export it: export {token_env_var}=your-token"
        )

    return {"username": username, "token": token}


def list_destination_ids(config: Dict[str, Any]) -> List[str]:
    """Return all destination IDs from a loaded config."""
    return [d.get("id", "") for d in config.get("destinations", []) if d.get("id")]

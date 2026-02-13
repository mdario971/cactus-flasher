"""Board status logger service for Cactus Flasher.

Logs board online/offline transitions to a persistent YAML file.
Only logs when status actually changes (compared to last known status).
"""
from datetime import datetime, timezone
from typing import List, Optional

from ..config import load_yaml_config, save_yaml_config

STATUS_LOG_FILE = "board_status_log.yaml"


def _load_status_log() -> dict:
    """Load the status log from YAML."""
    data = load_yaml_config(STATUS_LOG_FILE)
    if not data:
        data = {"last_status": {}, "logs": []}
    if "last_status" not in data:
        data["last_status"] = {}
    if "logs" not in data:
        data["logs"] = []
    return data


def get_last_statuses() -> dict:
    """Return the last known status of all boards."""
    data = _load_status_log()
    return data.get("last_status", {})


def log_status_change(board_name: str, new_status: str, details: str = "") -> bool:
    """Log a status change if the status actually changed.

    Returns True if a change was logged, False if status unchanged.
    """
    data = _load_status_log()
    old_status = data["last_status"].get(board_name, "unknown")

    if new_status == old_status:
        return False

    # Record the transition
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "board_name": board_name,
        "event": new_status,
        "details": details,
    }

    data["logs"].append(entry)
    data["last_status"][board_name] = new_status

    # Trim if too many entries
    trim_log(data, max_entries=500)

    save_yaml_config(STATUS_LOG_FILE, data)
    return True


def get_status_log(
    limit: int = 100, board_name: Optional[str] = None
) -> List[dict]:
    """Get recent status log entries, optionally filtered by board name.

    Returns entries in reverse chronological order (newest first).
    """
    data = _load_status_log()
    logs = data.get("logs", [])

    if board_name:
        logs = [entry for entry in logs if entry.get("board_name") == board_name]

    # Return newest first, limited
    return list(reversed(logs[-limit:]))


def trim_log(data: dict, max_entries: int = 500) -> None:
    """Keep only the most recent entries."""
    if len(data["logs"]) > max_entries:
        data["logs"] = data["logs"][-max_entries:]

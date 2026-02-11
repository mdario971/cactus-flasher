"""Configuration loader for Cactus Flasher."""
import os
from pathlib import Path
from typing import Optional
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
UPLOADS_DIR = BASE_DIR / "uploads"
BUILDS_DIR = BASE_DIR / "builds"

# Ensure directories exist
UPLOADS_DIR.mkdir(exist_ok=True)
BUILDS_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)


class Settings:
    """Application settings."""

    SECRET_KEY: str = os.getenv("SECRET_KEY", "cactus-flasher-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DDNS_HOST: str = os.getenv("DDNS_HOST", "esp32gb.ddns.net")

    # Build tool paths
    ESPHOME_PATH: str = os.getenv("ESPHOME_PATH", "esphome")
    ARDUINO_CLI_PATH: str = os.getenv("ARDUINO_CLI_PATH", "arduino-cli")
    PLATFORMIO_PATH: str = os.getenv("PLATFORMIO_PATH", "pio")


settings = Settings()


def load_yaml_config(filename: str) -> dict:
    """Load a YAML configuration file."""
    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        return {}
    with open(filepath, "r") as f:
        return yaml.safe_load(f) or {}


def save_yaml_config(filename: str, data: dict) -> None:
    """Save data to a YAML configuration file."""
    filepath = CONFIG_DIR / filename
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def get_credentials() -> dict:
    """Load user credentials from config."""
    return load_yaml_config("credentials.yaml")


def save_credentials(credentials: dict) -> None:
    """Save user credentials to config."""
    save_yaml_config("credentials.yaml", credentials)


def get_boards() -> dict:
    """Load board registry from config."""
    return load_yaml_config("boards.yaml")


def save_boards(boards: dict) -> None:
    """Save board registry to config."""
    save_yaml_config("boards.yaml", boards)


def get_board_hostname(board_name: str, board_id: int, custom_hostname: Optional[str] = None) -> str:
    """Generate hostname for a board based on its name and ID."""
    if custom_hostname:
        return custom_hostname
    # Strip common prefixes to get short name
    short_name = board_name
    for prefix in ("cactus-", "esp32-", "esp-"):
        if short_name.startswith(prefix):
            short_name = short_name[len(prefix):]
            break
    return f"{short_name}-{board_id:02d}.{settings.DDNS_HOST}"


def get_board_ports(board_id: int) -> dict:
    """Calculate port numbers for a board based on its ID."""
    return {
        "webserver": 8000 + board_id,
        "ota": 8200 + board_id,
        "api": 6000 + board_id,
    }

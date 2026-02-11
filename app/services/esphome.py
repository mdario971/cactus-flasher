"""ESPHome compilation service for Cactus Flasher."""
import asyncio
import os
import re
from pathlib import Path
from typing import Tuple, Optional
import tempfile
import shutil

from ..config import settings


async def compile_esphome(
    yaml_path: str,
    board_type: str = "esp32",
) -> Tuple[bool, Optional[str], str]:
    """
    Compile ESPHome firmware from YAML configuration.

    Args:
        yaml_path: Path to the ESPHome YAML configuration file
        board_type: ESP board type (esp32, esp8266, etc.)

    Returns:
        Tuple of (success: bool, firmware_path: Optional[str], logs: str)
    """
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        return False, None, f"YAML file not found: {yaml_path}"

    # ESPHome compile command
    cmd = [
        settings.ESPHOME_PATH,
        "compile",
        str(yaml_file),
    ]

    logs = []
    logs.append(f"Running: {' '.join(cmd)}\n")

    try:
        # Run ESPHome compile
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=yaml_file.parent,
        )

        # Stream output
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logs.append(line.decode())

        await process.wait()

        log_output = "".join(logs)

        if process.returncode != 0:
            return False, None, log_output

        # Find the generated firmware
        # ESPHome generates firmware in .esphome/build/<name>/.pioenvs/<name>/firmware.bin
        yaml_name = yaml_file.stem
        esphome_dir = yaml_file.parent / ".esphome"

        # Look for firmware.bin in common locations
        possible_paths = [
            esphome_dir / "build" / yaml_name / ".pioenvs" / yaml_name / "firmware.bin",
            esphome_dir / "build" / yaml_name / ".pio" / "build" / yaml_name / "firmware.bin",
            yaml_file.parent / ".pioenvs" / yaml_name / "firmware.bin",
        ]

        firmware_path = None
        for path in possible_paths:
            if path.exists():
                firmware_path = str(path)
                break

        # Also check for any .bin file in the build directory
        if not firmware_path:
            for bin_file in esphome_dir.rglob("firmware.bin"):
                firmware_path = str(bin_file)
                break

        if firmware_path:
            logs.append(f"\nFirmware generated: {firmware_path}\n")
            return True, firmware_path, "".join(logs)
        else:
            logs.append("\nCompilation succeeded but firmware.bin not found\n")
            return False, None, "".join(logs)

    except FileNotFoundError:
        return False, None, f"ESPHome not found at: {settings.ESPHOME_PATH}"
    except Exception as e:
        return False, None, f"Compilation error: {str(e)}"


async def validate_esphome_yaml(yaml_path: str) -> Tuple[bool, str]:
    """
    Validate ESPHome YAML configuration without compiling.

    Args:
        yaml_path: Path to the ESPHome YAML configuration file

    Returns:
        Tuple of (valid: bool, message: str)
    """
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        return False, f"YAML file not found: {yaml_path}"

    cmd = [
        settings.ESPHOME_PATH,
        "config",
        str(yaml_file),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output, _ = await process.communicate()

        if process.returncode == 0:
            return True, "Configuration is valid"
        else:
            return False, output.decode()

    except FileNotFoundError:
        return False, f"ESPHome not found at: {settings.ESPHOME_PATH}"
    except Exception as e:
        return False, str(e)


def create_minimal_esphome_config(
    name: str,
    board: str = "esp32dev",
    wifi_ssid: str = "YOUR_WIFI_SSID",
    wifi_password: str = "YOUR_WIFI_PASSWORD",
) -> str:
    """Generate a minimal ESPHome configuration."""
    return f"""esphome:
  name: {name}
  platform: ESP32
  board: {board}

wifi:
  ssid: "{wifi_ssid}"
  password: "{wifi_password}"

  ap:
    ssid: "{name} Fallback"
    password: "fallback123"

captive_portal:

logger:

api:

ota:
"""

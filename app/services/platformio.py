"""PlatformIO compilation service for Cactus Flasher."""
import asyncio
import os
from pathlib import Path
from typing import Tuple, Optional

from ..config import settings


async def compile_platformio(
    project_dir: str,
    environment: Optional[str] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    Compile PlatformIO project.

    Args:
        project_dir: Path to the PlatformIO project directory (containing platformio.ini)
        environment: Optional environment name to build (e.g., esp32dev)

    Returns:
        Tuple of (success: bool, firmware_path: Optional[str], logs: str)
    """
    project_path = Path(project_dir)

    # Find platformio.ini - it might be in a subdirectory after zip extraction
    platformio_ini = None
    if (project_path / "platformio.ini").exists():
        platformio_ini = project_path / "platformio.ini"
    else:
        # Search in subdirectories
        for ini_file in project_path.rglob("platformio.ini"):
            platformio_ini = ini_file
            project_path = ini_file.parent
            break

    if not platformio_ini:
        return False, None, f"platformio.ini not found in {project_dir}"

    logs = []

    # Build command
    build_cmd = [
        settings.PLATFORMIO_PATH,
        "run",
    ]

    if environment:
        build_cmd.extend(["-e", environment])

    logs.append(f"Running: {' '.join(build_cmd)}\n")
    logs.append(f"Project directory: {project_path}\n\n")

    try:
        process = await asyncio.create_subprocess_exec(
            *build_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=project_path,
        )

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
        # PlatformIO generates firmware in .pio/build/<env>/firmware.bin
        pio_build = project_path / ".pio" / "build"

        firmware_path = None

        if environment:
            env_firmware = pio_build / environment / "firmware.bin"
            if env_firmware.exists():
                firmware_path = str(env_firmware)
        else:
            # Find first firmware.bin in any environment
            for bin_file in pio_build.rglob("firmware.bin"):
                firmware_path = str(bin_file)
                break

        if firmware_path:
            logs.append(f"\nFirmware generated: {firmware_path}\n")
            return True, firmware_path, "".join(logs)
        else:
            logs.append("\nBuild succeeded but firmware.bin not found\n")
            return False, None, "".join(logs)

    except FileNotFoundError:
        return False, None, f"PlatformIO not found at: {settings.PLATFORMIO_PATH}"
    except Exception as e:
        return False, None, f"Build error: {str(e)}"


async def list_platformio_environments(project_dir: str) -> Tuple[bool, list, str]:
    """List available environments in a PlatformIO project."""
    project_path = Path(project_dir)

    # Find platformio.ini
    platformio_ini = None
    if (project_path / "platformio.ini").exists():
        platformio_ini = project_path / "platformio.ini"
    else:
        for ini_file in project_path.rglob("platformio.ini"):
            platformio_ini = ini_file
            break

    if not platformio_ini:
        return False, [], f"platformio.ini not found in {project_dir}"

    # Parse environments from platformio.ini
    environments = []
    try:
        with open(platformio_ini, "r") as f:
            content = f.read()
            import re
            envs = re.findall(r'\[env:(\w+)\]', content)
            environments = envs
    except Exception as e:
        return False, [], str(e)

    return True, environments, f"Found {len(environments)} environment(s)"


async def install_platformio_library(library: str, project_dir: Optional[str] = None) -> Tuple[bool, str]:
    """Install a PlatformIO library."""
    cmd = [
        settings.PLATFORMIO_PATH,
        "pkg",
        "install",
        "-l", library,
    ]

    if project_dir:
        cmd.extend(["-d", project_dir])
    else:
        cmd.append("-g")  # Global install

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()

        if process.returncode == 0:
            return True, f"Library {library} installed successfully"
        else:
            return False, output.decode()
    except FileNotFoundError:
        return False, f"PlatformIO not found at: {settings.PLATFORMIO_PATH}"
    except Exception as e:
        return False, str(e)


def create_minimal_platformio_config(
    board: str = "esp32dev",
    framework: str = "arduino",
) -> str:
    """Generate a minimal PlatformIO configuration."""
    return f"""[env:{board}]
platform = espressif32
board = {board}
framework = {framework}

; Enable OTA
upload_protocol = espota

; Monitor settings
monitor_speed = 115200

; Build flags
build_flags =
    -DCORE_DEBUG_LEVEL=3
"""

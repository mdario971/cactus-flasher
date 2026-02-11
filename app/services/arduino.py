"""Arduino-CLI compilation service for Cactus Flasher."""
import asyncio
import os
from pathlib import Path
from typing import Tuple, Optional

from ..config import settings


async def compile_arduino(
    sketch_path: str,
    board_fqbn: str = "esp32:esp32:esp32",
) -> Tuple[bool, Optional[str], str]:
    """
    Compile Arduino sketch using arduino-cli.

    Args:
        sketch_path: Path to the .ino sketch file
        board_fqbn: Fully Qualified Board Name (e.g., esp32:esp32:esp32)

    Returns:
        Tuple of (success: bool, firmware_path: Optional[str], logs: str)
    """
    sketch_file = Path(sketch_path)
    if not sketch_file.exists():
        return False, None, f"Sketch file not found: {sketch_path}"

    # The sketch must be in a directory with the same name
    sketch_dir = sketch_file.parent
    expected_name = sketch_dir.name + ".ino"

    if sketch_file.name != expected_name:
        return False, None, f"Sketch must be named {expected_name} to match directory {sketch_dir.name}"

    # Output directory for compiled binary
    output_dir = sketch_dir / "build"
    output_dir.mkdir(exist_ok=True)

    logs = []

    # First, ensure ESP32 core is installed
    logs.append("Checking ESP32 board support...\n")
    check_cmd = [
        settings.ARDUINO_CLI_PATH,
        "core",
        "list",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *check_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        logs.append(output.decode())

        # Check if ESP32 core is installed
        if "esp32:esp32" not in output.decode():
            logs.append("\nInstalling ESP32 core...\n")
            install_cmd = [
                settings.ARDUINO_CLI_PATH,
                "core",
                "install",
                "esp32:esp32",
            ]
            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            logs.append(output.decode())

    except FileNotFoundError:
        return False, None, f"arduino-cli not found at: {settings.ARDUINO_CLI_PATH}"

    # Compile the sketch
    compile_cmd = [
        settings.ARDUINO_CLI_PATH,
        "compile",
        "--fqbn", board_fqbn,
        "--output-dir", str(output_dir),
        str(sketch_dir),
    ]

    logs.append(f"\nCompiling: {' '.join(compile_cmd)}\n")

    try:
        process = await asyncio.create_subprocess_exec(
            *compile_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=sketch_dir,
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
        # arduino-cli generates <sketch_name>.ino.bin
        firmware_name = sketch_file.name + ".bin"
        firmware_path = output_dir / firmware_name

        # Also check for .bin without .ino extension
        if not firmware_path.exists():
            alt_firmware = output_dir / (sketch_dir.name + ".bin")
            if alt_firmware.exists():
                firmware_path = alt_firmware

        # Check all .bin files in output
        if not firmware_path.exists():
            for bin_file in output_dir.glob("*.bin"):
                firmware_path = bin_file
                break

        if firmware_path.exists():
            logs.append(f"\nFirmware generated: {firmware_path}\n")
            return True, str(firmware_path), "".join(logs)
        else:
            logs.append("\nCompilation succeeded but .bin file not found\n")
            return False, None, "".join(logs)

    except Exception as e:
        return False, None, f"Compilation error: {str(e)}"


async def list_arduino_boards() -> Tuple[bool, str]:
    """List available Arduino boards."""
    cmd = [
        settings.ARDUINO_CLI_PATH,
        "board",
        "listall",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        return True, output.decode()
    except FileNotFoundError:
        return False, f"arduino-cli not found at: {settings.ARDUINO_CLI_PATH}"
    except Exception as e:
        return False, str(e)


async def install_arduino_library(library_name: str) -> Tuple[bool, str]:
    """Install an Arduino library."""
    cmd = [
        settings.ARDUINO_CLI_PATH,
        "lib",
        "install",
        library_name,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()

        if process.returncode == 0:
            return True, f"Library {library_name} installed successfully"
        else:
            return False, output.decode()
    except FileNotFoundError:
        return False, f"arduino-cli not found at: {settings.ARDUINO_CLI_PATH}"
    except Exception as e:
        return False, str(e)

"""OTA flash service for Cactus Flasher."""
import asyncio
import hashlib
from pathlib import Path
from typing import Callable, Optional, Tuple
from dataclasses import dataclass
import aiohttp


@dataclass
class FlashProgress:
    """Progress information for a flash operation."""
    percent: int
    bytes_sent: int
    total_bytes: int
    message: str


async def flash_firmware(
    firmware_path: str,
    host: str,
    port: int,
    progress_callback: Optional[Callable[[FlashProgress], None]] = None,
    timeout: float = 120.0,
) -> Tuple[bool, str]:
    """
    Flash firmware to an ESP32 board via HTTP OTA.

    ESP32 ArduinoOTA and ESPHome both support HTTP POST to /update endpoint.

    Args:
        firmware_path: Path to the firmware .bin file
        host: Hostname or IP of the ESP32
        port: OTA port (typically 82XX)
        progress_callback: Optional callback for progress updates
        timeout: Timeout in seconds for the entire operation

    Returns:
        Tuple of (success: bool, message: str)
    """
    firmware_file = Path(firmware_path)
    if not firmware_file.exists():
        return False, f"Firmware file not found: {firmware_path}"

    file_size = firmware_file.stat().st_size

    # Calculate MD5 hash for verification
    md5_hash = hashlib.md5()
    with open(firmware_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)
    firmware_md5 = md5_hash.hexdigest()

    # Report initial progress
    if progress_callback:
        progress_callback(FlashProgress(
            percent=0,
            bytes_sent=0,
            total_bytes=file_size,
            message="Preparing upload...",
        ))

    # ESP32 OTA update URL
    url = f"http://{host}:{port}/update"

    try:
        # Create multipart form data with the firmware
        async with aiohttp.ClientSession() as session:
            # Read firmware into memory for upload
            with open(firmware_file, "rb") as f:
                firmware_data = f.read()

            # Create form data
            form = aiohttp.FormData()
            form.add_field(
                "firmware",
                firmware_data,
                filename=firmware_file.name,
                content_type="application/octet-stream",
            )

            # Add MD5 header for verification
            headers = {
                "x-MD5": firmware_md5,
            }

            if progress_callback:
                progress_callback(FlashProgress(
                    percent=10,
                    bytes_sent=0,
                    total_bytes=file_size,
                    message="Connecting to board...",
                ))

            # Upload firmware
            async with session.post(
                url,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if progress_callback:
                    progress_callback(FlashProgress(
                        percent=50,
                        bytes_sent=file_size,
                        total_bytes=file_size,
                        message="Uploading firmware...",
                    ))

                response_text = await response.text()

                if response.status == 200:
                    if progress_callback:
                        progress_callback(FlashProgress(
                            percent=100,
                            bytes_sent=file_size,
                            total_bytes=file_size,
                            message="Flash successful! Board is rebooting...",
                        ))
                    return True, "Firmware flashed successfully"
                else:
                    return False, f"Flash failed: HTTP {response.status} - {response_text}"

    except aiohttp.ClientConnectorError as e:
        return False, f"Connection failed: {str(e)}"
    except asyncio.TimeoutError:
        return False, "Flash operation timed out"
    except Exception as e:
        return False, f"Flash failed: {str(e)}"


async def flash_firmware_chunked(
    firmware_path: str,
    host: str,
    port: int,
    chunk_size: int = 4096,
    progress_callback: Optional[Callable[[FlashProgress], None]] = None,
    timeout: float = 120.0,
) -> Tuple[bool, str]:
    """
    Flash firmware using chunked transfer for better progress tracking.

    Some ESP32 implementations support chunked uploads which allows
    for more accurate progress reporting.
    """
    firmware_file = Path(firmware_path)
    if not firmware_file.exists():
        return False, f"Firmware file not found: {firmware_path}"

    file_size = firmware_file.stat().st_size
    bytes_sent = 0

    url = f"http://{host}:{port}/update"

    async def file_sender():
        nonlocal bytes_sent
        with open(firmware_file, "rb") as f:
            while chunk := f.read(chunk_size):
                bytes_sent += len(chunk)
                if progress_callback:
                    percent = int((bytes_sent / file_size) * 100)
                    progress_callback(FlashProgress(
                        percent=percent,
                        bytes_sent=bytes_sent,
                        total_bytes=file_size,
                        message=f"Uploading: {bytes_sent}/{file_size} bytes",
                    ))
                yield chunk

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file_size),
            }

            async with session.post(
                url,
                data=file_sender(),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 200:
                    if progress_callback:
                        progress_callback(FlashProgress(
                            percent=100,
                            bytes_sent=file_size,
                            total_bytes=file_size,
                            message="Flash successful!",
                        ))
                    return True, "Firmware flashed successfully"
                else:
                    response_text = await response.text()
                    return False, f"Flash failed: HTTP {response.status} - {response_text}"

    except Exception as e:
        return False, f"Flash failed: {str(e)}"


async def check_ota_available(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if OTA update endpoint is available."""
    url = f"http://{host}:{port}/update"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                # Most OTA endpoints return 200 or 405 (method not allowed) for GET
                return response.status in (200, 405)
    except Exception:
        return False

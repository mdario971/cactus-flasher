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


async def _try_flash_to_url(
    url: str,
    firmware_file: Path,
    firmware_data: bytes,
    firmware_md5: str,
    file_size: int,
    progress_callback: Optional[Callable[[FlashProgress], None]],
    timeout: float,
    auth: Optional[aiohttp.BasicAuth] = None,
    label: str = "",
) -> Tuple[bool, str]:
    """Attempt to flash firmware to a specific URL."""
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                "firmware",
                firmware_data,
                filename=firmware_file.name,
                content_type="application/octet-stream",
            )

            headers = {"x-MD5": firmware_md5}

            if progress_callback:
                progress_callback(FlashProgress(
                    percent=10,
                    bytes_sent=0,
                    total_bytes=file_size,
                    message=f"Connecting to board ({label})...",
                ))

            async with session.post(
                url,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                auth=auth,
            ) as response:
                if progress_callback:
                    progress_callback(FlashProgress(
                        percent=50,
                        bytes_sent=file_size,
                        total_bytes=file_size,
                        message=f"Uploading firmware ({label})...",
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
        return False, f"Connection failed ({label}): {str(e)}"
    except asyncio.TimeoutError:
        return False, f"Flash timed out ({label})"
    except Exception as e:
        return False, f"Flash failed ({label}): {str(e)}"


async def flash_firmware(
    firmware_path: str,
    host: str,
    port: int,
    progress_callback: Optional[Callable[[FlashProgress], None]] = None,
    timeout: float = 120.0,
    web_username: str = None,
    web_password: str = None,
    webserver_port: int = None,
) -> Tuple[bool, str]:
    """
    Flash firmware to an ESP32 board via HTTP OTA.

    Tries OTA port first (no auth), then falls back to web_server port with
    HTTP Basic Auth if OTA port fails and web credentials are available.

    Args:
        firmware_path: Path to the firmware .bin file
        host: Hostname or IP of the ESP32
        port: OTA port (typically 82XX)
        progress_callback: Optional callback for progress updates
        timeout: Timeout in seconds for the entire operation
        web_username: Optional HTTP Basic Auth username for web_server OTA
        web_password: Optional HTTP Basic Auth password for web_server OTA
        webserver_port: Optional web_server port for fallback OTA

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

    # Read firmware into memory
    with open(firmware_file, "rb") as f:
        firmware_data = f.read()

    if progress_callback:
        progress_callback(FlashProgress(
            percent=0,
            bytes_sent=0,
            total_bytes=file_size,
            message="Preparing upload...",
        ))

    # Try OTA port first
    ota_url = f"http://{host}:{port}/update"
    success, message = await _try_flash_to_url(
        ota_url, firmware_file, firmware_data, firmware_md5,
        file_size, progress_callback, timeout, label=f"OTA:{port}",
    )

    if success:
        return True, message

    # Fallback: try web_server port with Basic Auth
    if webserver_port and web_username and web_password:
        if progress_callback:
            progress_callback(FlashProgress(
                percent=5,
                bytes_sent=0,
                total_bytes=file_size,
                message=f"OTA port failed, trying web_server port {webserver_port}...",
            ))

        web_url = f"http://{host}:{webserver_port}/update"
        auth = aiohttp.BasicAuth(web_username, web_password)
        success, web_message = await _try_flash_to_url(
            web_url, firmware_file, firmware_data, firmware_md5,
            file_size, progress_callback, timeout, auth=auth,
            label=f"WEB:{webserver_port}",
        )

        if success:
            return True, web_message
        return False, f"OTA failed: {message} | Web fallback failed: {web_message}"

    return False, message


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
                return response.status in (200, 405)
    except Exception:
        return False

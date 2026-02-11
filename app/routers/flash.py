"""Flash router for Cactus Flasher - handles OTA firmware uploads."""
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, BackgroundTasks

from ..config import get_boards, get_board_ports, settings, BUILDS_DIR
from ..models.schemas import FlashRequest, FlashStatus
from ..services.ota import flash_firmware, FlashProgress

router = APIRouter()

# Track ongoing flash operations
flash_operations: dict[str, FlashStatus] = {}


@router.post("/upload")
async def upload_firmware(
    file: UploadFile = File(...),
    board_name: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Upload and flash a firmware binary to a board."""
    # Validate file
    if not file.filename.endswith(".bin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .bin firmware files are supported",
        )

    # Validate board
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_name}' not found",
        )

    # Save firmware file
    flash_id = str(uuid.uuid4())[:8]
    firmware_dir = BUILDS_DIR / flash_id
    firmware_dir.mkdir(exist_ok=True)
    firmware_path = firmware_dir / file.filename

    content = await file.read()
    with open(firmware_path, "wb") as f:
        f.write(content)

    # Create flash status
    flash_operations[flash_id] = FlashStatus(
        flash_id=flash_id,
        board_name=board_name,
        status="pending",
        progress=0,
    )

    # Start flash in background
    board = boards_data[board_name]
    ports = get_board_ports(board["id"])
    host = board.get("host") or settings.DDNS_HOST

    background_tasks.add_task(
        do_flash,
        flash_id,
        str(firmware_path),
        host,
        ports["ota"],
        board_name,
    )

    return {
        "flash_id": flash_id,
        "message": f"Flash operation started for board '{board_name}'",
    }


async def do_flash(
    flash_id: str,
    firmware_path: str,
    host: str,
    port: int,
    board_name: str,
):
    """Execute the firmware flash operation."""
    flash_operations[flash_id].status = "uploading"

    def progress_callback(progress: FlashProgress):
        flash_operations[flash_id].progress = progress.percent
        flash_operations[flash_id].message = progress.message

    try:
        success, message = await flash_firmware(
            firmware_path,
            host,
            port,
            progress_callback=progress_callback,
        )

        if success:
            flash_operations[flash_id].status = "success"
            flash_operations[flash_id].progress = 100
            flash_operations[flash_id].message = message
        else:
            flash_operations[flash_id].status = "failed"
            flash_operations[flash_id].message = message

    except Exception as e:
        flash_operations[flash_id].status = "failed"
        flash_operations[flash_id].message = str(e)


@router.post("/from-build")
async def flash_from_build(
    request: FlashRequest,
    background_tasks: BackgroundTasks,
):
    """Flash a previously built firmware to a board."""
    if not request.build_id and not request.firmware_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either build_id or firmware_path must be provided",
        )

    # Validate board
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if request.board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{request.board_name}' not found",
        )

    # Find firmware path
    if request.build_id:
        # Look for firmware in build directory
        build_dir = BUILDS_DIR / request.build_id
        if not build_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Build '{request.build_id}' not found",
            )

        # Find .bin file in build directory
        bin_files = list(build_dir.glob("*.bin"))
        if not bin_files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No firmware binary found in build '{request.build_id}'",
            )
        firmware_path = str(bin_files[0])
    else:
        firmware_path = request.firmware_path
        if not Path(firmware_path).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Firmware file not found: {firmware_path}",
            )

    # Create flash operation
    flash_id = str(uuid.uuid4())[:8]
    flash_operations[flash_id] = FlashStatus(
        flash_id=flash_id,
        board_name=request.board_name,
        status="pending",
        progress=0,
    )

    # Start flash
    board = boards_data[request.board_name]
    ports = get_board_ports(board["id"])
    host = board.get("host") or settings.DDNS_HOST

    background_tasks.add_task(
        do_flash,
        flash_id,
        firmware_path,
        host,
        ports["ota"],
        request.board_name,
    )

    return {
        "flash_id": flash_id,
        "message": f"Flash operation started for board '{request.board_name}'",
    }


@router.get("/status/{flash_id}", response_model=FlashStatus)
async def get_flash_status(flash_id: str):
    """Get the status of a flash operation."""
    if flash_id not in flash_operations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flash operation '{flash_id}' not found",
        )

    return flash_operations[flash_id]


@router.get("/history")
async def get_flash_history():
    """Get the history of flash operations."""
    return {
        "operations": [
            op.model_dump() for op in flash_operations.values()
        ]
    }

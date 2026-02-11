"""Build router for Cactus Flasher - handles firmware compilation."""
import uuid
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, BackgroundTasks

from ..config import UPLOADS_DIR, BUILDS_DIR
from ..models.schemas import BuildRequest, BuildStatus, ProjectType, BoardType
from ..services.esphome import compile_esphome
from ..services.arduino import compile_arduino
from ..services.platformio import compile_platformio

router = APIRouter()

# Track ongoing build operations
build_operations: dict[str, BuildStatus] = {}


@router.post("/esphome")
async def build_esphome(
    yaml_file: UploadFile = File(...),
    board_type: str = Form("esp32"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Build ESPHome firmware from YAML configuration."""
    if not yaml_file.filename.endswith((".yaml", ".yml")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only YAML files are supported for ESPHome builds",
        )

    # Create build directory
    build_id = str(uuid.uuid4())[:8]
    build_dir = UPLOADS_DIR / build_id
    build_dir.mkdir(exist_ok=True)

    # Save YAML file
    yaml_path = build_dir / yaml_file.filename
    content = await yaml_file.read()
    with open(yaml_path, "wb") as f:
        f.write(content)

    # Create build status
    build_operations[build_id] = BuildStatus(
        build_id=build_id,
        status="pending",
    )

    # Start build in background
    background_tasks.add_task(
        do_esphome_build,
        build_id,
        str(yaml_path),
        board_type,
    )

    return {
        "build_id": build_id,
        "message": "ESPHome build started",
    }


async def do_esphome_build(build_id: str, yaml_path: str, board_type: str):
    """Execute ESPHome compilation."""
    build_operations[build_id].status = "building"

    try:
        success, firmware_path, logs = await compile_esphome(yaml_path, board_type)

        if success and firmware_path:
            # Copy firmware to builds directory
            output_dir = BUILDS_DIR / build_id
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / "firmware.bin"
            shutil.copy(firmware_path, output_path)

            build_operations[build_id].status = "success"
            build_operations[build_id].firmware_path = str(output_path)
            build_operations[build_id].logs = logs
        else:
            build_operations[build_id].status = "failed"
            build_operations[build_id].message = "Compilation failed"
            build_operations[build_id].logs = logs

    except Exception as e:
        build_operations[build_id].status = "failed"
        build_operations[build_id].message = str(e)


@router.post("/arduino")
async def build_arduino(
    sketch_file: UploadFile = File(...),
    libraries: Optional[List[UploadFile]] = File(None),
    board_type: str = Form("esp32:esp32:esp32"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Build Arduino firmware from .ino sketch."""
    if not sketch_file.filename.endswith(".ino"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .ino files are supported for Arduino builds",
        )

    # Create build directory
    build_id = str(uuid.uuid4())[:8]
    sketch_name = sketch_file.filename.replace(".ino", "")
    build_dir = UPLOADS_DIR / build_id / sketch_name
    build_dir.mkdir(parents=True, exist_ok=True)

    # Save sketch file
    sketch_path = build_dir / sketch_file.filename
    content = await sketch_file.read()
    with open(sketch_path, "wb") as f:
        f.write(content)

    # Save library files if provided
    if libraries:
        lib_dir = build_dir / "libraries"
        lib_dir.mkdir(exist_ok=True)
        for lib in libraries:
            lib_path = lib_dir / lib.filename
            lib_content = await lib.read()
            with open(lib_path, "wb") as f:
                f.write(lib_content)

    # Create build status
    build_operations[build_id] = BuildStatus(
        build_id=build_id,
        status="pending",
    )

    # Start build in background
    background_tasks.add_task(
        do_arduino_build,
        build_id,
        str(sketch_path),
        board_type,
    )

    return {
        "build_id": build_id,
        "message": "Arduino build started",
    }


async def do_arduino_build(build_id: str, sketch_path: str, board_type: str):
    """Execute Arduino compilation."""
    build_operations[build_id].status = "building"

    try:
        success, firmware_path, logs = await compile_arduino(sketch_path, board_type)

        if success and firmware_path:
            # Copy firmware to builds directory
            output_dir = BUILDS_DIR / build_id
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / "firmware.bin"
            shutil.copy(firmware_path, output_path)

            build_operations[build_id].status = "success"
            build_operations[build_id].firmware_path = str(output_path)
            build_operations[build_id].logs = logs
        else:
            build_operations[build_id].status = "failed"
            build_operations[build_id].message = "Compilation failed"
            build_operations[build_id].logs = logs

    except Exception as e:
        build_operations[build_id].status = "failed"
        build_operations[build_id].message = str(e)


@router.post("/platformio")
async def build_platformio(
    project_zip: UploadFile = File(...),
    environment: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Build PlatformIO firmware from project zip."""
    if not project_zip.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip project archives are supported for PlatformIO builds",
        )

    # Create build directory
    build_id = str(uuid.uuid4())[:8]
    build_dir = UPLOADS_DIR / build_id
    build_dir.mkdir(exist_ok=True)

    # Save and extract zip
    zip_path = build_dir / project_zip.filename
    content = await project_zip.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    # Extract zip
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(build_dir)

    # Create build status
    build_operations[build_id] = BuildStatus(
        build_id=build_id,
        status="pending",
    )

    # Start build in background
    background_tasks.add_task(
        do_platformio_build,
        build_id,
        str(build_dir),
        environment,
    )

    return {
        "build_id": build_id,
        "message": "PlatformIO build started",
    }


async def do_platformio_build(build_id: str, project_dir: str, environment: Optional[str]):
    """Execute PlatformIO compilation."""
    build_operations[build_id].status = "building"

    try:
        success, firmware_path, logs = await compile_platformio(project_dir, environment)

        if success and firmware_path:
            # Copy firmware to builds directory
            output_dir = BUILDS_DIR / build_id
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / "firmware.bin"
            shutil.copy(firmware_path, output_path)

            build_operations[build_id].status = "success"
            build_operations[build_id].firmware_path = str(output_path)
            build_operations[build_id].logs = logs
        else:
            build_operations[build_id].status = "failed"
            build_operations[build_id].message = "Compilation failed"
            build_operations[build_id].logs = logs

    except Exception as e:
        build_operations[build_id].status = "failed"
        build_operations[build_id].message = str(e)


@router.get("/status/{build_id}", response_model=BuildStatus)
async def get_build_status(
    build_id: str):
    """Get the status of a build operation."""
    if build_id not in build_operations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build operation '{build_id}' not found",
        )

    return build_operations[build_id]


@router.get("/logs/{build_id}")
async def get_build_logs(
    build_id: str):
    """Get the logs of a build operation."""
    if build_id not in build_operations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build operation '{build_id}' not found",
        )

    return {
        "build_id": build_id,
        "logs": build_operations[build_id].logs,
    }


@router.get("/list")
async def list_builds():
    """List all build operations."""
    return {
        "builds": [
            op.model_dump() for op in build_operations.values()
        ]
    }

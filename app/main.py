"""Cactus Flasher - ESP32 Web Flasher Application."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Set

from .config import BASE_DIR, UPLOADS_DIR, BUILDS_DIR
from .auth import init_default_admin
from .routers import boards, flash, build


# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def send_to(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception:
            self.active_connections.discard(websocket)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_default_admin()
    print("Cactus Flasher started!")
    print(f"Uploads directory: {UPLOADS_DIR}")
    print(f"Builds directory: {BUILDS_DIR}")
    yield
    # Shutdown
    print("Cactus Flasher shutting down...")


app = FastAPI(
    title="Cactus Flasher",
    description="ESP32 Web Flasher Application for OTA firmware updates",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(boards.router, prefix="/api/boards", tags=["boards"])
app.include_router(flash.router, prefix="/api/flash", tags=["flash"])
app.include_router(build.router, prefix="/api/build", tags=["build"])

# Mount static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Serve the main application page."""
    index_path = BASE_DIR / "static" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Cactus Flasher API", "docs": "/docs"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_json()
            # Echo back for ping/pong
            if data.get("type") == "ping":
                await manager.send_to(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# Authentication endpoints (not in a separate router for simplicity)
from fastapi import HTTPException, status
from .auth import authenticate_user, create_access_token, create_user, get_current_user, Depends
from .models.schemas import LoginRequest, LoginResponse, UserCreate


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    username = authenticate_user(request.username, request.password)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    access_token = create_access_token(data={"sub": username})
    return LoginResponse(
        access_token=access_token,
        username=username,
    )


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(request: UserCreate, current_user: str = Depends(get_current_user)):
    """Register a new user (requires authentication)."""
    if not create_user(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    return {"message": f"User {request.username} created successfully"}


@app.get("/api/auth/me")
async def get_me(current_user: str = Depends(get_current_user)):
    """Get current user info."""
    return {"username": current_user}


def get_ws_manager() -> ConnectionManager:
    """Get the WebSocket connection manager."""
    return manager

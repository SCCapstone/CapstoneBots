import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from routers import projects, users, storage
from database import init_db, close_db

load_dotenv()

logger = logging.getLogger(__name__)

# Frontend URL
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception:
        logger.exception("Failed to initialize database")
        raise
    yield
    # Shutdown
    await close_db()
    logger.info("Database connection closed")


app = FastAPI(
    title="CapstoneBots API",
    version="1.0.0",
    description="A Blender Collaborative Version Control System API",
    lifespan=lifespan,
    root_path="/capstone-deploy-backend"
)

# Updated CORS middleware configuration
origins = [
    "http://localhost:3000",
    "https://capstone-bots.vercel.app",
    "https://capstonebots-production.up.railway.app",
]

# Add the dynamic DigitalOcean URL if it exists
if frontend_url:
    origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "CapstoneBots API"}


# Include routers
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(storage.router, prefix="/api/projects", tags=["storage"])
app.include_router(users.router, prefix="/api/auth", tags=["auth"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
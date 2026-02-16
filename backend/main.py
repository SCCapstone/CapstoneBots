import sys
import os

# Add the current directory to sys.path to allow imports from this folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from routers import projects, users, storage
from database import init_db, close_db

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("Database initialized successfully")
    yield
    # Shutdown
    await close_db()
    print("Database connection closed")


app = FastAPI(
    title="CapstoneBots API",
    version="1.0.0",
    description="A Blender Collaborative Version Control System API",
    lifespan=lifespan
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://capstone-bots.vercel.app",
        "https://capstonebots-production.up.railway.app"
    ],
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
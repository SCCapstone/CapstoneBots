from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import projects # This imports the projects router

app = FastAPI(
    title="CapstoneBots API",
    version="1.0.0",
    description="A simple API for CapstoneBots"
)

# This is the CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "CapstoneBots API"}

# This includes the projects router under the /api/projects prefix
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
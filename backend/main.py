from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import users

app = FastAPI(
    title="CapstoneBots API",
    version="1.0.0",
    description="A simple API for CapstoneBots"
)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include user/auth routes (in-memory fallback for development)
app.include_router(users.router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Welcome to CapstoneBots API", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
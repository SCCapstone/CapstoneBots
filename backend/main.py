from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
async def root():
    return {"message": "Welcome to CapstoneBots API", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/bots")
async def get_bots():
    # Placeholder for bot data
    return [
        {"id": 1, "name": "Discord Bot", "type": "discord", "active": True},
        {"id": 2, "name": "Telegram Bot", "type": "telegram", "active": False}
    ]

@app.post("/api/bots")
async def create_bot(bot_data: dict):
    # Placeholder for creating a bot
    return {"message": "Bot created", "data": bot_data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
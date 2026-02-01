# CapstoneBots Backend

This is the FastAPI backend for the CapstoneBots project.

## Setup and Run

### Prerequisites
- Python 3.9+
- PostgreSQL database running

### Installation

1.  **Create a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Variables:**
    Create a `.env` file in this directory if you need to override defaults.
    ```env
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/capstonebots
    ```

### Running the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Database Migrations

To run migrations (if Alembic is configured):
```bash
alembic upgrade head
```

## Testing

Automated testing is used to verify core backend functionality and catch regressions early.  
We use **pytest** for unit testing and **FastAPI’s TestClient (httpx)** for behavioral/API testing.

### Running Tests

From the `backend/` directory:

```bash
source .venv/bin/activate
pytest -q
```
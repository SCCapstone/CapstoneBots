# CapstoneBots

Blender Collaborative Version Control System

This project is a Version Control System (VCS) for Blender, enabling teams to collaborate on 3D projects with robust version management capabilities. It replaces traditional file-based VCS by exporting individual Blender objects as JSON (with mesh data stored separately), allowing efficient storage and granular version tracking.

For in-depth information, see the Project Description Wiki.

## Documentation

- **[Storage & Versioning System](./STORAGE.md)** - Comprehensive guide to file routing, object storage, deduplication, and version management
- **[Deployment Guide](./DEPLOYMENT.md)** - Production deployment instructions
- **[API Documentation](http://localhost:8000/docs)** - Interactive Swagger docs (when running locally)

## Quick Start (Docker)

The easiest way to run the entire application (Database, Backend, and Frontend) is using Docker Compose.

1.  **Prerequisites:** Ensure you have [Docker](https://www.docker.com/) and Docker Compose installed.
2.  **Run:**
    ```bash
    docker-compose up --build
    ```
3.  **Access:**
    *   Frontend: [http://localhost:3000](http://localhost:3000)
    *   Backend API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Main Features
- Timeline & History: See all changes and revert to any previous state.
- Merge Conflict Handling: Visualize and resolve merge conflicts directly in Blender.
- Object-Level Locking: Prevent conflicting edits before they happen.
- Web Dashboard: View project history, manage versions, and previews of 3D models.
- Blender Addon: Export, commit, pull updates, and resolve conflicts from inside Blender.

## Technologies Used
- Blender Addon: Python (bpy)
- Backend API: FastAPI (Python)
- Database: PostgreSQL
- Object Storage: MinIO (meshes and blend snapshots)
- Frontend: Next.JS + Tailwind CSS + model-viewer (3D model previews)
- Authentication: JWT-based auth

## Manual Installation and Setup

If you prefer to run services individually without Docker, follow these steps.

### Prerequisites
- Python 3.9+
- Node.js 20+ and npm
- PostgreSQL (running locally or accessible)
- MinIO (running locally or accessible)
- Blender 3.0+

### 1. Database Setup
Ensure you have a PostgreSQL database running.
```bash
# Example using Docker for just the DB
docker-compose up -d db
```

### 2. Backend Setup (FastAPI)

1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```
2.  Create and activate a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the server:
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```
    The API will be available at [http://localhost:8000](http://localhost:8000).

### 3. Frontend Setup (Next.JS)

1.  Navigate to the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Start the development server:
    ```bash
    npm start
    ```
    The application will open at [http://localhost:3000](http://localhost:3000).

## Deployment

Webapps need a deployment section that explains how to get it deployed on the
Internet. These should be detailed enough so anyone can re-deploy if needed
. Note that you **do not put passwords in git**.

Mobile apps will also sometimes need some instructions on how to build a
"release" version, maybe how to sign it, and how to run that binary in an
emulator or in a physical phone.

3. Start the development server (hot reload):

```bash
npm start
```

The frontend dev server will be available at: http://localhost:3000

Running with Docker (single service)

Build and run the frontend image (uses `frontend/Dockerfile`): 

```bash
section that explains how to run them.

The unit tests are in `/test/unit`.


Build and run the backend image (uses `backend/Dockerfile`):

```bash
The behavioral tests are in `/test/casper/`.

## Testing Technology


If you want frontend hot-reload inside Docker during development, mount the source directory and run the dev server from the official node image:

```bash
In some cases you need to install test runners, etc. Explain how.

	-v "$(pwd)/frontend:/app" -w /app \
	node:18-alpine sh -c "npm install && npm start"
```

Running everything with Docker Compose (recommended)

If this repository includes a `docker-compose.yml`, the easiest way to build and run all services is:

```bash
## Running Tests

Explain how to run the automated tests.

This will build images and start services defined in `docker-compose.yml`.

Common ports
- Frontend dev server: 3000
- Backend API (uvicorn): 8000

Stopping containers
- If you ran a container interactively, press Ctrl+C in that terminal.
- To stop containers started by docker-compose run:

```bash
docker-compose down
```

Notes
- Use `docker ps` to list running containers and `docker stop <container-id>` to stop any container.
- If you modify Dockerfiles or package lists you may need to rebuild images with `--no-cache` to avoid cached layers.

Next steps
- See `frontend/README.md` for Create React App notes and `backend/requirements.txt` for backend dependencies.


# Authors

Aarsh Patel - aarsh@email.sc.edu

Alex Mesa - alex@email.sc.edu

Paksh Patel - paksh@email.sc.edu

Joseph Vann - jrvann@email.sc.edu

Vraj Patel - vtpatel@email.sc.edu

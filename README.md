# CapstoneBots

Blender Collaborative Version Control System

This project is a Version Control System (VCS) for Blender, enabling teams to collaborate on 3D projects with robust version management capabilities. It replaces traditional file-based VCS by exporting individual Blender objects as JSON (with mesh data stored separately), allowing efficient storage and granular version tracking.

For in-depth information, see the Project Description Wiki.

Main Features
- Timeline & History: See all changes and revert to any previous state.
- Merge Conflict Handling: Visualize and resolve merge conflicts directly in Blender.
- Object-Level Locking: Prevent conflicting edits before they happen.
- Web Dashboard: View project history, manage versions, and previews of 3D models.
- Blender Addon: Export, commit, pull updates, and resolve conflicts from inside Blender.

Technologies Used
- Blender Addon: Python (bpy)
- Backend API: FastAPI (Python)
- Database: PostgreSQL
- Object Storage: MinIO (meshes and blend snapshots)
- Frontend: React + Tailwind CSS + model-viewer (3D model previews)
- Authentication: JWT-based auth

Installation and Setup
1. Prerequisites
- Python 3.9+
- Node.js 18+ and npm
- PostgreSQL
- MinIO
- Blender 3.0+

## External Requirements

List all the stuff the reader will need to install in order to get you app to
run in their laptop. For example:

In order to build this project you first have to install:

-   [Node.js](https://nodejs.org/en/)
-   [Docker](https://www.docker.com/)

## Running

Specify the commands for a developer to run the app from the cloned repo.

# Deployment

Webapps need a deployment section that explains how to get it deployed on the
Internet. These should be detailed enough so anyone can re-deploy if needed
. Note that you **do not put passwords in git**.

Mobile apps will also sometimes need some instructions on how to build a
"release" version, maybe how to sign it, and how to run that binary in an
emulator or in a physical phone.

## Running

These instructions show how to run the frontend and backend both locally (for development) and with Docker. The project root is the repository top-level where this `README.md` lives.

Prerequisites
- Docker (and docker-compose if you want the compose workflow)
- Node.js (for running frontend locally)
- Python 3 (for running backend locally)

Run the services locally (development)

Backend (FastAPI)

1. Change to the backend directory and create/activate a virtual environment:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

2. Install Python dependencies and run the app with uvicorn (hot reload):

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at: http://localhost:8000

Frontend (React)

1. Change to the frontend directory and install dependencies:

```bash
cd frontend
npm install
```

2. (Optional) Point the frontend at your running backend (default assumes http://localhost:8000):

```bash
export REACT_APP_API_URL=http://localhost:8000
```

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

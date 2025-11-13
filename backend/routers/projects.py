from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Project(BaseModel):
    id: int
    name: str
    description: str | None = None
    active: bool = True

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    active: bool = True

# temporary in-memory "DB"
FAKE_PROJECTS_DB: List[Project] = [
    Project(id=1, name="Demo Project", description="First BVCS project", active=True),
]

@router.get("/", response_model=List[Project])
async def get_projects():
    return FAKE_PROJECTS_DB

@router.post("/", response_model=Project)
async def create_project(data: ProjectCreate):
    new_id = len(FAKE_PROJECTS_DB) + 1
    project = Project(id=new_id, **data.dict())
    FAKE_PROJECTS_DB.append(project)
    return project
"""
FastAPI routers for CapstoneBots API

Includes:
- projects: Project management and version control routes
- users: Authentication and user management routes
- storage: File storage and versioning routes
"""

from . import projects, users, storage

__all__ = ["projects", "users", "storage"]

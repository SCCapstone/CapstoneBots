"""
Permission utilities for project collaboration.

This module provides helper functions to check if users have access to projects
and what level of permissions they have.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status

from models import Project, ProjectMember, User


async def check_project_access(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    require_owner: bool = False
) -> tuple[Project, Optional[str]]:
    """
    Check if a user has access to a project and return their role.
    
    Args:
        project_id: The project UUID to check
        user_id: The user UUID to check
        db: Database session
        require_owner: If True, raises exception if user is not the owner
        
    Returns:
        tuple: (Project object, role string or None)
        - role is "owner" if user owns the project
        - role is "member" if user is a member
        - role is None if user has no access (exception will be raised)
        
    Raises:
        HTTPException 404: If project doesn't exist
        HTTPException 403: If user doesn't have access or isn't owner when required
    """
    # Fetch the project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check if user is the owner
    if project.owner_id == user_id:
        return project, "owner"
    
    # If owner is required and user is not owner, deny access
    if require_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action"
        )
    
    # Check if user is a member
    query = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    )
    result = await db.execute(query)
    member = result.scalars().first()
    
    if member:
        return project, member.role
    
    # User has no access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this project"
    )


async def is_project_member(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession
) -> bool:
    """
    Check if a user is a member or owner of a project.
    
    Args:
        project_id: The project UUID
        user_id: The user UUID
        db: Database session
        
    Returns:
        bool: True if user is owner or member, False otherwise
    """
    # Check if owner
    project = await db.get(Project, project_id)
    if project and project.owner_id == user_id:
        return True
    
    # Check if member
    query = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    )
    result = await db.execute(query)
    member = result.scalars().first()
    
    return member is not None


async def get_user_projects(
    user_id: UUID,
    db: AsyncSession
) -> list[Project]:
    """
    Get all projects that a user has access to (owned or member).
    
    This is used by the Blender add-on to show all available projects to a user.
    
    Args:
        user_id: The user UUID
        db: Database session
        
    Returns:
        list[Project]: List of all projects user can access
    """
    # Get projects where user is owner
    owned_query = select(Project).where(Project.owner_id == user_id)
    
    # Get projects where user is a member
    member_query = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.project_id)
        .where(ProjectMember.user_id == user_id)
    )
    
    # Execute both queries
    owned_result = await db.execute(owned_query)
    owned_projects = owned_result.scalars().all()
    
    member_result = await db.execute(member_query)
    member_projects = member_result.scalars().all()
    
    # Combine and deduplicate (in case of edge cases)
    all_projects = list(owned_projects) + list(member_projects)
    seen = set()
    unique_projects = []
    for project in all_projects:
        if project.project_id not in seen:
            seen.add(project.project_id)
            unique_projects.append(project)
    
    return unique_projects

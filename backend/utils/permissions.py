"""
Permission utilities for project collaboration.

This module provides helper functions to check if users have access to projects
and what level of permissions they have. Supports role hierarchy: owner > editor > viewer.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status

from models import Project, ProjectMember, User, MemberRole, role_at_least


async def check_project_access(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    require_owner: bool = False,
    require_role: Optional[MemberRole] = None,
) -> tuple[Project, Optional[str]]:
    """
    Check if a user has access to a project and return their role.

    Args:
        project_id: The project UUID to check
        user_id: The user UUID to check
        db: Database session
        require_owner: If True, raises exception if user is not the owner
        require_role: If set, user must have at least this role level

    Returns:
        tuple: (Project object, role string)

    Raises:
        HTTPException 404: If project doesn't exist
        HTTPException 403: If user doesn't have access or insufficient role
    """
    # Fetch the project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    # Check membership (includes owner since owner is also in project_members)
    query = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    )
    result = await db.execute(query)
    member = result.scalars().first()

    # Fallback: check if user is the project owner (legacy or if not in members table)
    if not member and project.owner_id == user_id:
        user_role = MemberRole.owner
    elif member:
        try:
            user_role = MemberRole(member.role)
        except ValueError:
            # Legacy "member" role maps to editor
            user_role = MemberRole.editor
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project"
        )

    # If owner is explicitly required
    if require_owner and user_role != MemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action"
        )

    # If a minimum role level is required
    if require_role and not role_at_least(user_role, require_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires at least '{require_role.value}' role"
        )

    return project, user_role.value


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

    Uses a single query via a JOIN on project_members to avoid
    fetching duplicates (owner is always in project_members).

    Args:
        user_id: The user UUID
        db: Database session

    Returns:
        list[Project]: List of all projects user can access
    """
    query = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.project_id)
        .where(ProjectMember.user_id == user_id)
    )
    result = await db.execute(query)
    return list(result.scalars().unique().all())

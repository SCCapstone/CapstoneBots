"""
User Authentication Routes

This module handles user registration and login endpoints for the CapstoneBots API.
It provides JWT-based authentication for secure access to the application.

Endpoints:
    POST /register - Create a new user account
    POST /login - Authenticate and receive access token
    GET /me - Get current authenticated user information
"""

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from database import get_db
from models import User, Project, ProjectMember, ObjectLock, Commit, Branch
import schemas
from utils.auth import get_password_hash, verify_password, create_access_token, get_current_user

# Initialize the router for authentication endpoints
router = APIRouter()


@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user account.
    
    This endpoint creates a new user with a unique username and email.
    Passwords are securely hashed using bcrypt before storage.
    
    Args:
        user: UserCreate schema containing username, email, and password
        db: Database session dependency
        
    Returns:
        UserResponse: Created user details (excludes password)
        
    Raises:
        HTTPException 400: If username or email already exists
        
    Example:
        POST /api/auth/register
        {
            "username": "johndoe",
            "email": "john@example.com",
            "password": "securepass123"
        }
    """
    # Check if email already exists in database
    email_result = await db.execute(select(User).where(User.email == user.email))
    email_user = email_result.scalars().first()
    
    # Check if username already exists in database
    username_result = await db.execute(select(User).where(User.username == user.username))
    username_user = username_result.scalars().first()
    
    # Provide specific error messages for better user experience
    if email_user and username_user:
        raise HTTPException(status_code=400, detail="Both username and email are already registered")
    elif email_user:
        raise HTTPException(status_code=400, detail="Email is already registered")
    elif username_user:
        raise HTTPException(status_code=400, detail="Username is already registered")

    # Hash the password securely using bcrypt (via utils.auth module)
    hashed_password = get_password_hash(user.password)
    
    # Create new user instance with hashed password
    new_user = User(
        username=user.username,
        email=user.email,
        password_hash=hashed_password
    )
    
    # Add user to database and commit transaction
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)  # Refresh to get generated fields (e.g., user_id, created_at)
    
    return new_user


@router.post("/login", response_model=schemas.Token)
async def login(user_credentials: schemas.UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate user and generate JWT access token.
    
    This endpoint validates user credentials and returns a JWT token that can be used
    for authenticated requests. The token should be included in subsequent requests
    as: Authorization: Bearer <token>
    
    Args:
        user_credentials: UserLogin schema containing email and password
        db: Database session dependency
        
    Returns:
        Token: JWT access token and token type
        
    Raises:
        HTTPException 401: If email doesn't exist or password is incorrect
        
    Example:
        POST /api/auth/login
        {
            "email": "john@example.com",
            "password": "securepass123"
        }
        
        Response:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer"
        }
    """
    # Query database for user with provided email
    result = await db.execute(select(User).where(User.email == user_credentials.email))
    user = result.scalars().first()

    # Verify user exists and password matches the stored hash
    # Note: We use the same error message for both cases to prevent user enumeration attacks
    if not user or not verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate JWT token with user's email as the subject claim
    # The token can be decoded later to identify the authenticated user
    access_token = create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get currently authenticated user's information.
    
    This endpoint returns the profile data of the logged-in user based on their
    JWT token. It's commonly used by the frontend to display user info and verify
    the session is still valid.
    
    Args:
        current_user: User object automatically resolved from JWT token via dependency injection
        
    Returns:
        UserResponse: Current user's profile data (excludes password)
        
    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
        
    Example:
        GET /api/auth/me
        Headers: 
            Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
        
        Response:
        {
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "username": "johndoe",
            "email": "john@example.com",
            "created_at": "2025-12-02T10:30:00"
        }
    """
    return current_user


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: schemas.DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the authenticated user's account and handle associated data.

    Requires password confirmation. This action is irreversible.

    Behavior:
    - Owned projects with NO other members → deleted (cascade removes all related data)
    - Owned projects WITH other members → ownership transferred to next member
    - Non-owned project memberships → removed
    - Object locks held by user → released
    - Commits in non-owned projects → author_id set to NULL (anonymized)
    - User record → deleted
    """
    # 1. Verify password
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    user_id = current_user.user_id

    # 2. Handle owned projects
    owned_result = await db.execute(
        select(Project).where(Project.owner_id == user_id)
    )
    owned_projects = owned_result.scalars().all()

    for project in owned_projects:
        # Count members (excluding the current user)
        member_count_result = await db.execute(
            select(func.count(ProjectMember.member_id)).where(
                ProjectMember.project_id == project.project_id,
                ProjectMember.user_id != user_id,
            )
        )
        other_member_count = member_count_result.scalar()

        if other_member_count == 0:
            # Sole member → delete the entire project (cascade handles related data)
            await db.delete(project)
        else:
            # Transfer ownership to the next member
            next_member_result = await db.execute(
                select(ProjectMember)
                .where(
                    ProjectMember.project_id == project.project_id,
                    ProjectMember.user_id != user_id,
                )
                .order_by(ProjectMember.added_at)
                .limit(1)
            )
            next_member = next_member_result.scalars().first()

            if next_member:
                # Update project owner
                project.owner_id = next_member.user_id
                next_member.role = "owner"

            # Remove the deleting user's membership
            user_membership_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.project_id,
                    ProjectMember.user_id == user_id,
                )
            )
            user_membership = user_membership_result.scalars().first()
            if user_membership:
                await db.delete(user_membership)

    # 3. Remove non-owned project memberships
    non_owned_result = await db.execute(
        select(ProjectMember).where(ProjectMember.user_id == user_id)
    )
    for membership in non_owned_result.scalars().all():
        await db.delete(membership)

    # 4. Release all object locks held by user
    locks_result = await db.execute(
        select(ObjectLock).where(ObjectLock.locked_by == user_id)
    )
    for lock in locks_result.scalars().all():
        await db.delete(lock)

    # 5. Anonymize commits in projects user doesn't own (author_id → NULL)
    commits_result = await db.execute(
        select(Commit).where(Commit.author_id == user_id)
    )
    for commit in commits_result.scalars().all():
        commit.author_id = None

    # 6. Anonymize branches created by user in projects user doesn't own
    branches_result = await db.execute(
        select(Branch).where(Branch.created_by == user_id)
    )
    for branch in branches_result.scalars().all():
        branch.created_by = None

    # 7. Delete the user record
    await db.delete(current_user)
    await db.commit()

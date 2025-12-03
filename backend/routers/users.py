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

from database import get_db
from models import User
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

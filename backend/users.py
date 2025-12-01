from fastapi import APIRouter, HTTPException, status, Depends, Form, File, UploadFile
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError
from uuid import uuid4
import hashlib
import json

from database import get_db
from models import User, Branch, Commit, BlenderObject
import schemas
import auth

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ------------------- User Routes ------------------- #

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    email_result = await db.execute(select(User).where(User.email == user.email))
    email_user = email_result.scalars().first()
    username_result = await db.execute(select(User).where(User.username == user.username))
    username_user = username_result.scalars().first()

    if email_user and username_user:
        raise HTTPException(status_code=400, detail="Both username and email are already registered")
    elif email_user:
        raise HTTPException(status_code=400, detail="Email is already registered")
    elif username_user:
        raise HTTPException(status_code=400, detail="Username is already registered")

    hashed_password = auth.get_password_hash(user.password)
    new_user = User(username=user.username, email=user.email, password_hash=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=schemas.Token)
async def login(user_credentials: schemas.UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_credentials.email))
    user = result.scalars().first()

    if not user or not auth.verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserResponse)
async def get_me(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Return the currently logged-in user based on the JWT token.
    """
    try:
        payload = auth.decode_access_token(token)
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return user

    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ------------------- Commit Route ------------------- #

@router.post("/commit")
async def create_commit(
    metadata: str = Form(...),
    files: list[UploadFile] = File([]),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts multipart/form-data:
    - metadata: JSON string with branch_id, author_id, commit_message, objects[]
    - files: includes *.json and *.glb uploads
    """
    try:
        meta = json.loads(metadata)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {e}")

    branch_id = meta.get("branch_id")
    author_id = meta.get("author_id")
    commit_message = meta.get("commit_message")
    objects = meta.get("objects", [])

    # Validate branch
    branch = await db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    # Create commit
    commit_id = uuid4()
    new_commit = Commit(
        commit_id=commit_id,
        author_id=author_id,
        branch_id=branch_id,
        parent_commit_id=branch.head_commit_id,
        commit_message=commit_message,
    )
    db.add(new_commit)

    # Map filename → file data
    uploaded_files = {file.filename: await file.read() for file in files}

    response_objects = []

    # Process objects
    for obj in objects:
        name = obj["object_name"]

        json_filename = f"{name}.json"
        glb_filename = f"{name}.glb"

        json_bytes = uploaded_files.get(json_filename)
        glb_bytes = uploaded_files.get(glb_filename)

        if json_bytes is None or glb_bytes is None:
            raise HTTPException(status_code=400, detail=f"Missing files for object {name}")

        # Hash for storage
        blob_hash = hashlib.sha256(glb_bytes).hexdigest()

        blender_obj = BlenderObject(
            object_id=uuid4(),
            commit_id=commit_id,
            object_name=name,
            object_type=obj["object_type"],
            blob_hash=blob_hash,
            transform=json_bytes.decode("utf-8"),
            glb_data=glb_bytes,  # Stored in DB, not returned
        )
        db.add(blender_obj)

        response_objects.append({
            "object_name": name,
            "object_type": obj["object_type"],
            "blob_hash": blob_hash,
        })

    # Update branch head
    branch.head_commit_id = commit_id

    await db.commit()
    return {
        "status": "ok",
        "commit_id": str(commit_id),
        "objects": response_objects,
    }

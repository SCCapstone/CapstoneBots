from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Lock
from schemas import LockCreate, LockResponse, LockStatus
from utils.auth import get_current_user

router = APIRouter(prefix="/api/locks", tags=["locks"])

# How long a lock is considered valid before we auto-expire it
LOCK_TIMEOUT = timedelta(minutes=30)


def _is_expired(lock: Lock) -> bool:
    """
    Helper to determine whether a lock is too old and should be removed.
    """
    # lock.timestamp is timezone-naive in your model, so compare to utcnow()
    return datetime.utcnow() - lock.timestamp > LOCK_TIMEOUT


# -----------------------
# Acquire a lock
# -----------------------
@router.post("/", response_model=LockResponse)
def lock_object(
    payload: LockCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Try to acquire a lock on a Blender object.

    - If no active lock exists → create one and return it.
    - If a lock exists but is expired → delete it and create a new one.
    - If a valid lock exists by another user → 409 Conflict.
    """

    # Look for an existing lock on this object
    existing = (
        db.query(Lock)
        .filter(Lock.object_id == payload.object_id)
        .first()
    )

    if existing:
        if _is_expired(existing):
            # auto-clear stale lock
            db.delete(existing)
            db.commit()
        else:
            # someone else still holds the lock
            if existing.user_id != current_user.user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Object is already locked by another user.",
                )
            else:
                # current user already holds the lock → just return it
                return LockResponse(
                    lock_id=existing.lock_id,
                    object_id=existing.object_id,
                    user_id=existing.user_id,
                    timestamp=existing.timestamp,
                )

    # Create a new lock
    new_lock = Lock(
        object_id=payload.object_id,
        user_id=current_user.user_id,
        timestamp=datetime.utcnow(),
    )
    db.add(new_lock)
    db.commit()
    db.refresh(new_lock)

    return LockResponse(
        lock_id=new_lock.lock_id,
        object_id=new_lock.object_id,
        user_id=new_lock.user_id,
        timestamp=new_lock.timestamp,
    )


# -----------------------
# Release a lock
# -----------------------
@router.delete("/{object_id}")
def unlock_object(
    object_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Release an existing lock on an object.

    Only the user who owns the lock can release it.
    """
    lock = (
        db.query(Lock)
        .filter(Lock.object_id == object_id)
        .first()
    )

    if not lock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No lock exists on this object.",
        )

    if lock.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this lock.",
        )

    db.delete(lock)
    db.commit()

    return {"status": "unlocked", "object_id": object_id}


# -----------------------
# Check lock status
# -----------------------
@router.get("/{object_id}", response_model=LockStatus)
def get_lock_status(
    object_id: int,
    db: Session = Depends(get_db),
):
    """
    Get whether the object is currently locked, by whom, and when.

    Also automatically deletes expired locks.
    """
    lock = (
        db.query(Lock)
        .filter(Lock.object_id == object_id)
        .first()
    )

    if not lock:
        return LockStatus(
            object_id=object_id,
            is_locked=False,
            locked_by=None,
            timestamp=None,
        )

    if _is_expired(lock):
        db.delete(lock)
        db.commit()
        return LockStatus(
            object_id=object_id,
            is_locked=False,
            locked_by=None,
            timestamp=None,
        )

    return LockStatus(
        object_id=object_id,
        is_locked=True,
        locked_by=lock.user_id,
        timestamp=lock.timestamp,
    )
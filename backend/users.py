from fastapi import APIRouter, HTTPException, status
from typing import Dict

import auth
from schemas import UserIn, UserOut, Token

router = APIRouter()

# Simple in-memory user "database". Keys: email -> {id, email, hashed_password}
USERS_DB: Dict[str, Dict] = {}
_ID_SEQ = 1


def _next_id() -> int:
    global _ID_SEQ
    v = _ID_SEQ
    _ID_SEQ += 1
    return v


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user: UserIn):
    email = user.email.lower()
    if email in USERS_DB:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed = auth.get_password_hash(user.password)
    user_obj = {"id": _next_id(), "email": email, "hashed_password": hashed}
    USERS_DB[email] = user_obj
    return {"id": user_obj["id"], "email": user_obj["email"]}


@router.post("/login", response_model=Token)
def login(form_data: UserIn):
    email = form_data.email.lower()
    user = USERS_DB.get(email)
    if not user or not auth.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = auth.create_access_token({"sub": email})
    return {"access_token": access_token, "token_type": "bearer"}

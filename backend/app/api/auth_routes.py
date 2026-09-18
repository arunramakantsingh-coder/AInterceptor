"""Auth endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.auth import hash_password, verify_password, make_jwt
from app.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    user_id: str
    email: str


@router.post("/signup", response_model=TokenOut)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(token=make_jwt(user.id), user_id=user.id, email=user.email)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(token=make_jwt(user.id), user_id=user.id, email=user.email)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user_id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}

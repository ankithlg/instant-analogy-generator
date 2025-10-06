from fastapi import HTTPException
from models import UserCreate, UserInDB
from utils import hash_password, verify_password
from database import users_collection
import re

def validate_password(password: str):
    pattern = r"^(?=.*[0-9])(?=.*[a-z])(?=.*[A-Z])(?=.*[@#$%^&+=!]).{8,}$"
    if not re.match(pattern, password):
        raise HTTPException(
            status_code=400,
            detail="Password must be ≥8 chars, include 1 uppercase, 1 lowercase, 1 number, 1 special character (@#$%^&+=!)"
        )
    
async def create_user(user: UserCreate):
    validate_password(user.password) 


    # Check if email already exists
    if await users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = hash_password(user.password)
    user_doc = {"username": user.username, "email": user.email, "hashed_password": hashed_pw}
    await users_collection.insert_one(user_doc)
    return {"message": "User created successfully"}

async def authenticate_user(email: str, password: str):
    user = await users_collection.find_one({"email": email})
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return UserInDB(**user)


from fastapi import FastAPI
from app.database.session import engine
from app.database.base import Base
from app.models.user import User
from app.routes import admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, admin, notices 
  # IMPORTANT: import model

from app.routes import auth
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(notices.router)


router = APIRouter(prefix="/notices", tags=["Notices"])


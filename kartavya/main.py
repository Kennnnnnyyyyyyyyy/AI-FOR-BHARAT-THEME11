from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(
    title="Kartavya",
    description="Compliance-operations layer for Karnataka High Court judgments",
    version="0.1.0"
)

# CORS
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Kartavya API running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

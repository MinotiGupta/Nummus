import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.schema import init_db

# Initialize DB tables
init_db()

app = FastAPI(title="AI Revenue Recovery Agent API", version="1.0")

# Configure CORS
origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

from api.routes import router
app.include_router(router, prefix="/api")

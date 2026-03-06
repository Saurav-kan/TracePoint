"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.routers import cases
from app.routers import ingest
from app.routers import planner
from app.routers import workflow

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TracePoint API",
    description="Fact-Checking RAG for law enforcement investigations",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(cases.router)
app.include_router(planner.router)
app.include_router(workflow.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {"message": "TracePoint API"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from auth import router as auth_router, seed_admin, ensure_auth_indexes
from analysis import router as analysis_router
from ai_research import router as ai_router
from db import client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Research Console API")

app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(ai_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await ensure_auth_indexes()
    await seed_admin()
    logger.info("Research Console API ready. LIVE DISARMED — allow_real_live is permanently false.")


@app.on_event("shutdown")
async def shutdown():
    client.close()

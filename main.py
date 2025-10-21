import logging

from fastapi import FastAPI
from routes import api_router
from starlette.middleware.cors import CORSMiddleware

from utils.logger import setup_logging, get_logger

setup_logging(level=logging.DEBUG, log_to_file=True)
log = get_logger("[API]")


app = FastAPI(title="Gorky Maps", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, PUT, DELETE, OPTIONS
    allow_headers=["*"],  # Authorization, Content-Type и т.п.
)

app.include_router(api_router, prefix="/api")

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs")).resolve()

ORS_KEY = os.getenv("ORS_KEY", None)

MAX_ROUTE_CANDIDATES_DEFAULT = int(os.getenv("MAX_ROUTE_CANDIDATES", "12"))
CANDIDATE_EXPANSION_STEP = int(os.getenv("CANDIDATE_EXPANSION_STEP", "12"))
ROUTE_DIFFERENCE_RATIO = float(os.getenv("ROUTE_DIFFERENCE_RATIO", "0.3"))
MAX_ROUTE_EVALUATIONS = int(os.getenv("MAX_ROUTE_EVALUATIONS", "20000"))
MAX_COMBINATIONS_PER_LENGTH = int(os.getenv("MAX_COMBINATIONS_PER_LENGTH", "400"))

GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID", None)
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", None)

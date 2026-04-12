"""Environment configuration — reads credentials and settings from .env file."""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "").strip()

_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | None = None, log_file: str | None = None) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    lvl = (level or LOG_LEVEL).upper()
    root.setLevel(getattr(logging, lvl, logging.INFO))
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(formatter)
    root.addHandler(h)

    path = (log_file or LOG_FILE).strip()
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setFormatter(formatter)
            root.addHandler(fh)
        except OSError:
            root.warning("Could not open log file %s", path)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ── Load .env ────────────────────────────────────────────────────────────────
_env_paths = [
    Path(__file__).resolve().parent / ".env",
    Path.cwd() / ".env",
]
for _env_file in _env_paths:
    if _env_file.exists():
        load_dotenv(_env_file)
        break

logger = get_logger("config")

# ── Operational settings ─────────────────────────────────────────────────────
WORKGRAPH_MODE = os.getenv("WORKGRAPH_MODE", "DRY_RUN").upper()
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "audit.log.jsonl")


def is_execute_allowed() -> bool:
    return WORKGRAPH_MODE == "EXECUTE"


# ── Jira ─────────────────────────────────────────────────────────────────────
JIRA_BASE_URL = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME") or ""
JIRA_TOKEN = os.getenv("JIRA_TOKEN") or ""
JIRA_API_VERSION = os.getenv("JIRA_API_VERSION", "3").strip() or "3"

# ── Bitbucket ────────────────────────────────────────────────────────────────
BITBUCKET_BASE_URL = (os.getenv("BITBUCKET_BASE_URL") or "").rstrip("/")
BITBUCKET_WORKSPACE = os.getenv("BITBUCKET_WORKSPACE") or ""
BITBUCKET_USERNAME = os.getenv("BITBUCKET_USERNAME") or ""
BITBUCKET_APP_PASSWORD = os.getenv("BITBUCKET_APP_PASSWORD") or os.getenv("BITBUCKET_TOKEN") or ""

# ── Confluence ───────────────────────────────────────────────────────────────
CONFLUENCE_BASE_URL = (os.getenv("CONFLUENCE_BASE_URL") or "").rstrip("/")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL") or os.getenv("CONFLUENCE_USERNAME") or ""
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN") or ""

# ── Bamboo ───────────────────────────────────────────────────────────────────
BAMBOO_BASE_URL = (os.getenv("BAMBOO_BASE_URL") or "").rstrip("/")
BAMBOO_USERNAME = os.getenv("BAMBOO_USERNAME") or ""
BAMBOO_TOKEN = os.getenv("BAMBOO_TOKEN") or ""

# ── Allowlists (comma-separated) ────────────────────────────────────────────
def _parse_list(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


ALLOWLIST_JIRA_PROJECT_KEYS = _parse_list(os.getenv("ALLOWLIST_JIRA_PROJECT_KEYS"))
ALLOWLIST_CONFLUENCE_SPACE_KEYS = _parse_list(os.getenv("ALLOWLIST_CONFLUENCE_SPACE_KEYS"))
ALLOWLIST_BITBUCKET_REPOS = _parse_list(os.getenv("ALLOWLIST_BITBUCKET_REPOS"))
ALLOWLIST_BAMBOO_PLANS = _parse_list(os.getenv("ALLOWLIST_BAMBOO_PLANS"))

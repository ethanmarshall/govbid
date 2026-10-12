"""Settings loaded from environment variables (or a .env file in backend/)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

SAM_API_KEY = os.getenv("SAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
# Keys that are not scoped to one workspace must say which workspace to use (Console, Settings, Workspaces: wrkspc_...)
ANTHROPIC_WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID", "")


def anthropic_client(**kw):
    """The Anthropic client with the key, and the workspace header when ANTHROPIC_WORKSPACE_ID is set."""
    import anthropic

    if ANTHROPIC_WORKSPACE_ID:
        kw["default_headers"] = {"anthropic-workspace-id": ANTHROPIC_WORKSPACE_ID}
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, **kw)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'govbid.db'}")
if DATABASE_URL.startswith("sqlite:///"):  # create the folder for the database file (a fresh disk is empty)
    Path(DATABASE_URL[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SAM_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

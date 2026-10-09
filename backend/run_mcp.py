"""Launcher for the GovBid Pro MCP server that works from any working directory.

  python /path/to/backend/run_mcp.py                 stdio (for Claude Desktop / Claude Code)
  python /path/to/backend/run_mcp.py --http --port 8765
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

from app.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()

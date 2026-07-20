"""
main.py
=======
Application entry point.

Usage:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
    python -m backend.main
"""

from __future__ import annotations

import uvicorn

from backend.core.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

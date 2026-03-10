"""
app.config — Application configuration package.

Exports:
    Settings    — Pydantic BaseSettings class loaded from .env
    get_settings — Cached factory function for Settings singleton
"""

from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]

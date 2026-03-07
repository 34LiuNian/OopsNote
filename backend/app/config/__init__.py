"""
Configuration module for OopsNote backend.
"""

# Re-export from app/config_main.py to avoid import conflicts
from ..config_main import AppConfig, load_app_config

__all__ = ["AppConfig", "load_app_config"]

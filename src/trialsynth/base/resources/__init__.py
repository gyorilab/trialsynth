from pathlib import Path

__all__ = [
    "BASE_RESOURCE_DIR",
    "DEFAULT_CONFIG_PATH",
]

BASE_RESOURCE_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = BASE_RESOURCE_DIR / "default_config.ini"

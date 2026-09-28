import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Configuración central de la aplicación."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "galileo-dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'data' / 'galileo.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / "data" / "uploads")
    EXPORT_FOLDER = str(BASE_DIR / "exports")
    BACKUP_FOLDER = str(BASE_DIR / "backups")
    LOG_FOLDER = str(BASE_DIR / "logs")

    os.makedirs(BASE_DIR / "data", exist_ok=True)
    os.makedirs(BASE_DIR / "exports", exist_ok=True)
    os.makedirs(BASE_DIR / "backups", exist_ok=True)
    os.makedirs(BASE_DIR / "logs", exist_ok=True)
    os.makedirs(BASE_DIR / "data" / "uploads", exist_ok=True)

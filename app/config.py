import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Configuración central de la aplicación."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'data' / 'galileo.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / "data" / "uploads")
    EXPORT_FOLDER = str(BASE_DIR / "exports")
    BACKUP_FOLDER = str(BASE_DIR / "backups")
    LOG_FOLDER = str(BASE_DIR / "logs")
    MIGRATIONS_DIRECTORY = str(BASE_DIR / "migrations")

    @staticmethod
    def prepare_storage() -> None:
        """Crear directorios de trabajo cuando se inicia la aplicación."""
        for directory in (
            BASE_DIR / "data" / "uploads",
            BASE_DIR / "exports",
            BASE_DIR / "backups",
            BASE_DIR / "logs",
        ):
            os.makedirs(directory, exist_ok=True)

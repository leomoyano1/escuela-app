from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_db() -> None:
    """Crear tablas si aún no existen."""
    db.create_all()

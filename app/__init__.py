from flask import Flask

from . import models
from .config import Config
from .database import db, init_db
from .routes import bp as main_bp


def create_app() -> Flask:
    """Crear la aplicación Flask principal del sistema escolar."""
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    app.register_blueprint(main_bp)

    with app.app_context():
        init_db()

    return app

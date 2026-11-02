import click
import sqlite3
import secrets
from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from . import models
from .config import Config
from .database import (
    crear_respaldo_sqlite,
    db,
    migrar_esquema,
    restaurar_respaldo_sqlite,
)
from .routes import bp as main_bp


migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message = "Inicia sesión para continuar."


@login_manager.user_loader
def cargar_usuario(id_usuario: str) -> models.Usuario | None:
    if not id_usuario.isdigit():
        return None
    return db.session.get(models.Usuario, int(id_usuario))


def create_app(config_override: dict[str, object] | None = None) -> Flask:
    """Crear la aplicación Flask principal del sistema escolar."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secrets.token_urlsafe(48)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("REMEMBER_COOKIE_HTTPONLY", True)
    app.config["DUMMY_PASSWORD_HASH"] = generate_password_hash(
        secrets.token_urlsafe(32)
    )

    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIRECTORY"])
    login_manager.init_app(app)
    app.register_blueprint(main_bp)

    @app.cli.command("db-upgrade-safe")
    def db_upgrade_safe() -> None:
        """Respaldar SQLite y aplicar las migraciones pendientes."""
        Config.prepare_storage()
        respaldo = migrar_esquema(app)
        if respaldo is not None:
            print(f"Respaldo previo a la migración: {respaldo}")

    @app.cli.command("db-backup")
    def db_backup() -> None:
        """Crear una copia SQLite consistente en la carpeta local de respaldos."""
        try:
            respaldo = crear_respaldo_sqlite(
                db.engine,
                app.config["BACKUP_FOLDER"],
            )
        except (OSError, ValueError, sqlite3.Error, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        if respaldo is None:
            raise click.ClickException(
                "No se pudo respaldar la base: se requiere un archivo SQLite persistente."
            )
        click.echo(f"Respaldo SQLite creado y verificado: {respaldo}")

    @app.cli.command("db-restore")
    @click.argument("archivo_respaldo", type=click.Path(exists=True, dir_okay=False, path_type=str))
    def db_restore(archivo_respaldo: str) -> None:
        """Restaurar una copia SQLite; requiere que no haya otra app abierta."""
        engine = db.engine
        ruta_base = engine.url.database
        if engine.dialect.name != "sqlite" or not ruta_base or ruta_base == ":memory:":
            raise click.ClickException("La restauración requiere una base SQLite persistente.")
        db.session.remove()
        engine.dispose()
        try:
            restaurar_respaldo_sqlite(archivo_respaldo, ruta_base)
        except (OSError, ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Base restaurada desde: {archivo_respaldo}")

    @app.cli.command("audit-verify")
    def audit_verify() -> None:
        """Comprobar la continuidad criptográfica de la bitácora."""
        from .audit import verificar_integridad_auditoria

        if not verificar_integridad_auditoria():
            raise click.ClickException("La bitácora presenta una alteración o una ruptura de cadena.")
        click.echo("Integridad de la bitácora verificada.")

    return app

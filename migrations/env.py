import logging
from logging.config import fileConfig

from alembic import context
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from sqlalchemy import inspect

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")
target_db = current_app.extensions["migrate"].db


def get_engine():
    return target_db.engine


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def get_engine_url():
    return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")


config.set_main_option("sqlalchemy.url", get_engine_url())


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=get_metadata(),
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    def process_revision_directives(migration_context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    configure_args = current_app.extensions["migrate"].configure_args
    if configure_args.get("process_revision_directives") is None:
        configure_args["process_revision_directives"] = process_revision_directives
    configure_args.setdefault("transactional_ddl", True)

    with get_engine().connect() as connection:
        current_revisions = set(MigrationContext.configure(connection).get_current_heads())
        target_revisions = set(ScriptDirectory.from_config(config).get_heads())
        existing_tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
        if current_revisions != target_revisions and (
            current_revisions or existing_tables
        ):
            from app.database import crear_respaldo_sqlite

            backup = crear_respaldo_sqlite(
                get_engine(),
                current_app.config["BACKUP_FOLDER"],
            )
            current_app.config["LAST_MIGRATION_BACKUP"] = str(backup) if backup else None

        if connection.in_transaction():
            connection.rollback()

        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **configure_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

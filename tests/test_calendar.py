import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.database import db, migrar_esquema
from app.models import AnioLectivo, CicloEscolar, EventoAuditoria, NivelGrado
from app.services import (
    crear_anio_lectivo,
    crear_ciclo_escolar,
    crear_usuario,
    editar_anio_lectivo,
    editar_ciclo_escolar,
)


class CalendarioEscolarTests(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        raiz = Path(self.directorio.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key-not-for-production",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{raiz / 'test.sqlite3'}",
                "BACKUP_FOLDER": str(raiz / "backups"),
                "MIGRATIONS_DIRECTORY": str(
                    Path(__file__).resolve().parents[1] / "migrations"
                ),
                "SESSION_COOKIE_SECURE": False,
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            migrar_esquema(self.app)
            self.actor = crear_usuario(
                "directora",
                "ClaveSegura-Calendario!",
                bootstrap=True,
            )
            db.session.add_all(
                [
                    NivelGrado(id=1, nombre_nivel="Secundario", grado_año="1er Año"),
                    NivelGrado(id=2, nombre_nivel="Secundario", grado_año="2do Año"),
                ]
            )
            db.session.commit()
            self.actor_id = self.actor.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directorio.cleanup()

    def test_anio_valida_rango_tipo_unicidad_y_cambio_de_fechas(self):
        with self.app.app_context():
            with self.assertRaisesRegex(ValueError, "fecha de fin"):
                crear_anio_lectivo(
                    2026,
                    date(2026, 12, 1),
                    date(2026, 3, 1),
                    actor_id=self.actor_id,
                )
            with self.assertRaisesRegex(ValueError, "fecha de inicio"):
                crear_anio_lectivo(
                    2026,
                    "2026-03-01",
                    date(2027, 2, 28),
                    actor_id=self.actor_id,
                )

            anio = crear_anio_lectivo(
                2026,
                date(2026, 3, 1),
                date(2027, 2, 28),
                actor_id=self.actor_id,
            )
            with self.assertRaisesRegex(ValueError, "ya está registrado"):
                crear_anio_lectivo(
                    2026,
                    date(2026, 4, 1),
                    date(2027, 3, 31),
                    actor_id=self.actor_id,
                )

            with self.assertRaises(IntegrityError):
                db.session.add(
                    AnioLectivo(
                        numero_ciclo=2030,
                        fecha_inicio=date(2031, 1, 1),
                        fecha_fin=date(2030, 12, 31),
                    )
                )
                db.session.flush()
            db.session.rollback()

            editar_anio_lectivo(
                anio.id,
                2026,
                date(2026, 2, 15),
                date(2027, 3, 15),
                actor_id=self.actor_id,
            )
            eventos = (
                db.session.query(EventoAuditoria)
                .filter_by(entidad="anio_lectivo", entidad_id=str(anio.id))
                .order_by(EventoAuditoria.id)
                .all()
            )
            self.assertEqual([evento.accion for evento in eventos], [
                "anio_lectivo.creado",
                "anio_lectivo.editado",
            ])
            self.assertTrue(all(evento.actor_id == self.actor_id for evento in eventos))
            cambios = json.loads(eventos[-1].detalles_json)["cambios"]
            self.assertEqual(
                cambios["fecha_inicio"],
                {"anterior": "2026-03-01", "nuevo": "2026-02-15"},
            )
            self.assertEqual(
                cambios["fecha_fin"],
                {"anterior": "2027-02-28", "nuevo": "2027-03-15"},
            )

    def test_ciclo_valida_relaciones_rango_y_unicidad_incluida_nulidad_sqlite(self):
        with self.app.app_context():
            anio = crear_anio_lectivo(
                2026,
                date(2026, 3, 1),
                date(2027, 2, 28),
                actor_id=self.actor_id,
            )
            with self.assertRaisesRegex(ValueError, "comprendido"):
                crear_ciclo_escolar(
                    anio.id,
                    1,
                    date(2026, 2, 28),
                    date(2026, 8, 1),
                    actor_id=self.actor_id,
                )
            with self.assertRaisesRegex(ValueError, "fecha de cierre"):
                crear_ciclo_escolar(
                    anio.id,
                    1,
                    date(2026, 9, 1),
                    date(2026, 8, 31),
                    actor_id=self.actor_id,
                )
            with self.assertRaisesRegex(ValueError, "No existe el nivel"):
                crear_ciclo_escolar(
                    anio.id,
                    999,
                    date(2026, 3, 1),
                    date(2026, 8, 31),
                    actor_id=self.actor_id,
                )

            ciclo_global = crear_ciclo_escolar(
                anio.id,
                None,
                date(2026, 3, 1),
                date(2026, 12, 15),
                actor_id=self.actor_id,
            )
            with self.assertRaisesRegex(ValueError, "ciclo global"):
                crear_ciclo_escolar(
                    anio.id,
                    None,
                    date(2026, 4, 1),
                    date(2026, 12, 20),
                    actor_id=self.actor_id,
                )

            ciclo_nivel = crear_ciclo_escolar(
                anio.id,
                1,
                date(2026, 3, 1),
                date(2026, 11, 30),
                actor_id=self.actor_id,
            )
            with self.assertRaisesRegex(ValueError, "nivel y año"):
                crear_ciclo_escolar(
                    anio.id,
                    1,
                    date(2026, 4, 1),
                    date(2026, 12, 1),
                    actor_id=self.actor_id,
                )
            crear_ciclo_escolar(
                anio.id,
                2,
                date(2026, 3, 1),
                date(2026, 11, 30),
                actor_id=self.actor_id,
            )

            editar_ciclo_escolar(
                ciclo_nivel.id,
                anio.id,
                1,
                date(2026, 3, 15),
                date(2026, 12, 1),
                actor_id=self.actor_id,
            )
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(
                    entidad="ciclo_escolar",
                    entidad_id=str(ciclo_nivel.id),
                    accion="ciclo_escolar.editado",
                )
                .one()
            )
            cambios = json.loads(evento.detalles_json)["cambios"]
            self.assertEqual(
                cambios["fecha_apertura"],
                {"anterior": "2026-03-01", "nuevo": "2026-03-15"},
            )
            self.assertEqual(evento.actor_id, self.actor_id)
            self.assertIsNotNone(ciclo_global)

            with self.assertRaises(IntegrityError):
                db.session.add(
                    CicloEscolar(
                        id_anio=anio.id,
                        id_nivel=None,
                        fecha_apertura=date(2026, 4, 1),
                        fecha_cierre=date(2026, 12, 1),
                    )
                )
                db.session.flush()
            db.session.rollback()
            indices = db.session.execute(
                text("PRAGMA index_list('ciclo_escolar')")
            ).all()
            self.assertTrue(
                any(fila[1] == "uq_ciclo_escolar_anio_global" and fila[2] == 1 for fila in indices)
            )

    def test_editar_anio_no_deja_ciclos_fuera_de_rango(self):
        with self.app.app_context():
            anio = crear_anio_lectivo(
                2026,
                date(2026, 1, 1),
                date(2027, 12, 31),
                actor_id=self.actor_id,
            )
            crear_ciclo_escolar(
                anio.id,
                None,
                date(2026, 3, 1),
                date(2026, 11, 30),
                actor_id=self.actor_id,
            )
            with self.assertRaisesRegex(ValueError, "fuera del año lectivo"):
                editar_anio_lectivo(
                    anio.id,
                    2026,
                    date(2026, 4, 1),
                    date(2027, 12, 31),
                    actor_id=self.actor_id,
                )

    def test_migracion_valida_datos_previos_y_preserva_anios_y_ciclos(self):
        directorio = tempfile.TemporaryDirectory()
        try:
            raiz = Path(directorio.name)
            app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "migration-calendar-test",
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{raiz / 'migration.sqlite3'}",
                    "BACKUP_FOLDER": str(raiz / "backups"),
                    "MIGRATIONS_DIRECTORY": str(
                        Path(__file__).resolve().parents[1] / "migrations"
                    ),
                }
            )
            with app.app_context():
                config = app.extensions["migrate"].migrate.get_config(
                    app.config["MIGRATIONS_DIRECTORY"]
                )
                command.upgrade(config, "ab41d879c562")
                with db.engine.begin() as conexion:
                    conexion.exec_driver_sql(
                        "INSERT INTO anio_lectivo "
                        "(id, numero_ciclo, fecha_inicio, fecha_fin) "
                        "VALUES (401, 2040, '2040-01-01', '2039-12-31')"
                    )
                    conexion.exec_driver_sql(
                        "INSERT INTO anio_lectivo "
                        "(id, numero_ciclo, fecha_inicio, fecha_fin) "
                        "VALUES (402, 2041, '2041-03-01', '2042-02-28')"
                    )
                    conexion.exec_driver_sql(
                        "INSERT INTO ciclo_escolar "
                        "(id, id_anio, id_nivel, fecha_apertura, fecha_cierre) "
                        "VALUES (501, 402, NULL, '2041-03-01', '2041-12-15')"
                    )
                    conexion.exec_driver_sql(
                        "INSERT INTO ciclo_escolar "
                        "(id, id_anio, id_nivel, fecha_apertura, fecha_cierre) "
                        "VALUES (502, 402, NULL, '2041-04-01', '2041-12-20')"
                    )

                with self.assertRaisesRegex(RuntimeError, "fecha_fin anterior"):
                    command.upgrade(config, "head")
                with db.engine.begin() as conexion:
                    conexion.exec_driver_sql(
                        "UPDATE anio_lectivo SET fecha_fin = '2040-12-31' WHERE id = 401"
                    )
                with self.assertRaisesRegex(RuntimeError, "ciclo global"):
                    command.upgrade(config, "head")
                with db.engine.begin() as conexion:
                    conexion.exec_driver_sql(
                        "DELETE FROM ciclo_escolar WHERE id = 502"
                    )

                command.upgrade(config, "head")
                anio = db.session.get(AnioLectivo, 402)
                ciclo = db.session.get(CicloEscolar, 501)
                self.assertEqual(anio.numero_ciclo, 2041)
                self.assertEqual(anio.fecha_inicio, date(2041, 3, 1))
                self.assertEqual(ciclo.id_anio, 402)
                self.assertIsNone(ciclo.id_nivel)
                db.session.remove()
                db.engine.dispose()
        finally:
            directorio.cleanup()

    def test_falla_de_auditoria_revierte_el_registro_y_no_hay_borrado_fisico(self):
        with self.app.app_context():
            with patch("app.services.registrar_evento_auditoria", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    crear_anio_lectivo(
                        2026,
                        date(2026, 3, 1),
                        date(2027, 2, 28),
                        actor_id=self.actor_id,
                    )
            self.assertEqual(db.session.query(AnioLectivo).count(), 0)

            anio = crear_anio_lectivo(
                2026,
                date(2026, 3, 1),
                date(2027, 2, 28),
                actor_id=self.actor_id,
            )
            with patch("app.services.registrar_evento_auditoria", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    editar_anio_lectivo(
                        anio.id,
                        2026,
                        date(2026, 2, 1),
                        date(2027, 3, 31),
                        actor_id=self.actor_id,
                    )
            db.session.expire_all()
            anio = db.session.get(AnioLectivo, anio.id)
            self.assertEqual(anio.fecha_inicio, date(2026, 3, 1))
            self.assertEqual(anio.fecha_fin, date(2027, 2, 28))

            db.session.delete(anio)
            with self.assertRaisesRegex(ValueError, "borrado físico"):
                db.session.flush()
            db.session.rollback()
            self.assertIsNotNone(db.session.get(AnioLectivo, anio.id))

    def test_interfaz_requiere_autenticacion_y_no_completa_fechas(self):
        self.assertEqual(self.client.get("/calendario").status_code, 302)
        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        with self.client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]
        login = self.client.post(
            "/login",
            data={
                "csrf_token": csrf_token,
                "username": "directora",
                "password": "ClaveSegura-Calendario!",
            },
        )
        self.assertEqual(login.status_code, 302)
        page = self.client.get("/calendario")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="fecha_inicio" type="date" required\n             value=""', page.data)
        self.assertIn(b"Calendario institucional", page.data)
        with self.app.app_context():
            consulta = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="calendario.consultado")
                .one()
            )
            self.assertEqual(consulta.actor_id, self.actor_id)

        with self.client.session_transaction() as browser_session:
            csrf_token = browser_session["csrf_token"]
        response = self.client.post(
            "/calendario",
            data={
                "csrf_token": csrf_token,
                "entidad": "anio_lectivo",
                "operacion": "crear",
                "numero_ciclo": "2026",
                "fecha_inicio": "2026-03-01",
                "fecha_fin": "2027-02-28",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="anio_lectivo.creado")
                .one()
            )
            self.assertEqual(evento.actor_id, self.actor_id)


if __name__ == "__main__":
    unittest.main()

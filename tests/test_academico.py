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
from app.models import (
    Alumno,
    AnioLectivo,
    Asignatura,
    CursoDireccion,
    Docente,
    EventoAuditoria,
    GrupoSeccion,
    HistorialGrupoMatricula,
    Matricula,
    NivelGrado,
    Tutor,
)
from app.services import (
    cambiar_grupo_matricula,
    crear_asignatura,
    crear_grupo_seccion,
    crear_nivel_grado,
    crear_usuario,
    editar_grupo_seccion,
    listar_historial_grupo_matricula,
)


ROOT = Path(__file__).resolve().parents[1]


class AdministracionAcademicaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key-not-for-production",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory / 'school.sqlite3'}",
                "BACKUP_FOLDER": str(directory / "backups"),
                "MIGRATIONS_DIRECTORY": str(ROOT / "migrations"),
                "SESSION_COOKIE_SECURE": False,
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            migrar_esquema(self.app)
            self.actor = crear_usuario("academico", "Clave-segura-123!", bootstrap=True)
            self.nivel = crear_nivel_grado("Secundario", "1er Año", self.actor.id)
            self.grupo_a = crear_grupo_seccion(
                self.nivel.id, "A", 30, actor_id=self.actor.id
            )
            self.grupo_b = crear_grupo_seccion(
                self.nivel.id, "B", 30, actor_id=self.actor.id
            )
            self.grupo_sin_seccion = crear_grupo_seccion(
                self.nivel.id, "  ", 30, actor_id=self.actor.id
            )
            self.asignatura = crear_asignatura("Artes Visuales", 4, self.actor.id)
            self.anio = AnioLectivo(
                numero_ciclo=2026,
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2027, 2, 28),
            )
            tutor = Tutor(nombre="Responsable", dni_cuit="TEST-ACAD-1")
            alumno = Alumno(
                tutor=tutor,
                nombre="Alumna",
                apellido="Prueba",
                dni="TEST-ALUMNA-1",
            )
            self.matricula = Matricula(
                alumno=alumno,
                anio_lectivo=self.anio,
                grupo=self.grupo_a,
                fecha_inscripcion=date(2026, 3, 1),
            )
            db.session.add_all([self.anio, tutor, alumno, self.matricula])
            db.session.flush()
            self.periodo_inicial = HistorialGrupoMatricula(
                matricula=self.matricula,
                grupo=self.grupo_a,
                fecha_desde=date(2026, 3, 1),
            )
            db.session.add(self.periodo_inicial)
            db.session.commit()
            self.actor_id = self.actor.id
            self.nivel_id = self.nivel.id
            self.matricula_id = self.matricula.id
            self.grupo_a_id = self.grupo_a.id
            self.grupo_b_id = self.grupo_b.id
            self.grupo_sin_seccion_id = self.grupo_sin_seccion.id
            self.asignatura_id = self.asignatura.id
            self.anio_id = self.anio.id
            self.periodo_inicial_id = self.periodo_inicial.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def test_crea_nivel_asignatura_y_grupos_con_division_opcional(self):
        with self.app.app_context():
            grupo_sin_seccion = db.session.get(
                GrupoSeccion, self.grupo_sin_seccion_id
            )
            self.assertIsNone(grupo_sin_seccion.seccion)
            asignatura = db.session.get(Asignatura, self.asignatura_id)
            self.assertEqual(asignatura.nombre_materia, "Artes Visuales")
            grupos = (
                db.session.query(GrupoSeccion)
                .filter_by(id_nivel=self.nivel_id)
                .all()
            )
            self.assertEqual({grupo.seccion for grupo in grupos}, {"A", "B", None})
            auditaron = (
                db.session.query(EventoAuditoria.actor_id)
                .filter_by(entidad="grupo_seccion")
                .all()
            )
            self.assertTrue(all(actor_id == self.actor_id for (actor_id,) in auditaron))
            with self.assertRaises(ValueError):
                crear_grupo_seccion(
                    self.nivel.id, "", 30, actor_id=self.actor_id
                )

    def test_servicios_de_escritura_exigen_usuario_activo(self):
        with self.app.app_context():
            with self.assertRaisesRegex(ValueError, "usuario autenticado"):
                crear_nivel_grado("Primario", "6to")
            with self.assertRaisesRegex(ValueError, "no existe o está inactivo"):
                crear_nivel_grado("Primario", "6to", actor_id=999)

    def test_grupo_con_asignacion_docente_no_reescribe_su_identidad_historica(self):
        with self.app.app_context():
            docente = Docente(nombre="Docente", legajo_laboral="DOC-1")
            curso = CursoDireccion(
                docente=docente,
                asignatura=db.session.get(Asignatura, self.asignatura_id),
                grupo=db.session.get(GrupoSeccion, self.grupo_b_id),
                horario="Lunes",
            )
            db.session.add(curso)
            db.session.commit()

            with self.assertRaisesRegex(ValueError, "asignaciones docentes"):
                editar_grupo_seccion(
                    self.grupo_b_id,
                    self.nivel_id,
                    "C",
                    30,
                    actor_id=self.actor_id,
                )

            self.assertEqual(
                db.session.get(GrupoSeccion, self.grupo_b_id).seccion,
                "B",
            )

    def test_transiciones_conservan_matricula_y_forman_periodos_consecutivos(self):
        with self.app.app_context():
            matricula_original_id = db.session.get(Matricula, self.matricula_id).id
            cambiar_grupo_matricula(
                self.matricula_id,
                self.grupo_b_id,
                date(2026, 7, 1),
                actor_id=self.actor_id,
            )
            grupo_c = crear_grupo_seccion(
                self.nivel_id, "C", 30, actor_id=self.actor_id
            )
            cambiar_grupo_matricula(
                self.matricula_id,
                grupo_c.id,
                date(2026, 9, 10),
                actor_id=self.actor_id,
            )

            matriculas = db.session.query(Matricula).filter_by(
                id_alumno=db.session.get(Matricula, self.matricula_id).id_alumno,
                id_anio=self.anio_id,
            ).all()
            self.assertEqual(len(matriculas), 1)
            self.assertEqual(matriculas[0].id, matricula_original_id)
            self.assertEqual(matriculas[0].id_grupo, grupo_c.id)

            periodos = listar_historial_grupo_matricula(
                self.matricula_id, actor_id=self.actor_id
            )
            self.assertEqual(
                [
                    (periodo.grupo.seccion, periodo.fecha_desde, periodo.fecha_hasta)
                    for periodo in periodos
                ],
                [
                    ("A", date(2026, 3, 1), date(2026, 6, 30)),
                    ("B", date(2026, 7, 1), date(2026, 9, 9)),
                    ("C", date(2026, 9, 10), None),
                ],
            )
            for anterior, siguiente in zip(periodos, periodos[1:]):
                self.assertEqual(
                    anterior.fecha_hasta.toordinal() + 1,
                    siguiente.fecha_desde.toordinal(),
                )
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(
                    accion="matricula.grupo_cambiado",
                    entidad_id=str(self.matricula_id),
                )
                .order_by(EventoAuditoria.id.desc())
                .first()
            )
            self.assertIsNotNone(evento)
            self.assertEqual(evento.actor_id, self.actor_id)
            self.assertIn("id_grupo", json.loads(evento.detalles_json)["cambios"])
            eventos_historial = (
                db.session.query(EventoAuditoria)
                .filter(
                    EventoAuditoria.entidad == "historial_grupo_matricula",
                    EventoAuditoria.accion.in_(
                        [
                            "historial_grupo_matricula.cerrado",
                            "historial_grupo_matricula.creado",
                        ]
                    ),
                )
                .all()
            )
            self.assertEqual(len(eventos_historial), 4)
            self.assertTrue(
                all(evento.actor_id == self.actor_id for evento in eventos_historial)
            )

    def test_rechaza_vigencias_invalidas_y_no_modifica_historial(self):
        with self.app.app_context():
            invalidas = (
                date(2026, 3, 1),
                date(2026, 2, 28),
                date(2027, 3, 1),
            )
            for efectiva in invalidas:
                with self.subTest(fecha=efectiva):
                    with self.assertRaises(ValueError):
                        cambiar_grupo_matricula(
                            self.matricula_id,
                            self.grupo_b_id,
                            efectiva,
                            actor_id=self.actor_id,
                        )
            self.assertEqual(
                db.session.query(HistorialGrupoMatricula)
                .filter_by(id_matricula=self.matricula_id)
                .count(),
                1,
            )
            matricula = db.session.get(Matricula, self.matricula_id)
            self.assertEqual(matricula.id_grupo, self.grupo_a_id)

    def test_falla_de_auditoria_revierte_cambio_completo(self):
        with self.app.app_context():
            with patch("app.services.registrar_evento_auditoria", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    cambiar_grupo_matricula(
                        self.matricula_id,
                        self.grupo_b_id,
                        date(2026, 7, 1),
                        actor_id=self.actor_id,
                    )
            db.session.expire_all()
            matricula = db.session.get(Matricula, self.matricula_id)
            periodos = (
                db.session.query(HistorialGrupoMatricula)
                .filter_by(id_matricula=self.matricula_id)
                .all()
            )
            self.assertEqual(matricula.id_grupo, self.grupo_a_id)
            self.assertEqual(len(periodos), 1)
            self.assertIsNone(periodos[0].fecha_hasta)

    def test_historial_no_se_borra_y_sqlite_impide_solapamientos(self):
        with self.app.app_context():
            periodo = db.session.get(
                HistorialGrupoMatricula, self.periodo_inicial_id
            )
            db.session.delete(periodo)
            with self.assertRaisesRegex(ValueError, "historial_grupo_matricula"):
                db.session.flush()
            db.session.rollback()

            with self.assertRaises(IntegrityError):
                db.session.execute(
                    text(
                        "DELETE FROM historial_grupo_matricula WHERE id = :periodo"
                    ),
                    {"periodo": self.periodo_inicial_id},
                )
            db.session.rollback()

            with self.assertRaises(IntegrityError):
                db.session.execute(
                    text(
                        """
                        INSERT INTO historial_grupo_matricula
                            (id_matricula, id_grupo, fecha_desde, fecha_hasta)
                        VALUES (:matricula, :grupo, '2026-03-15', NULL)
                        """
                    ),
                    {"matricula": self.matricula_id, "grupo": self.grupo_a_id},
                )
                db.session.flush()
            db.session.rollback()

    def test_interfaz_catalogos_exige_sesion_y_csrf(self):
        self.assertEqual(self.client.get("/academico").status_code, 302)
        self._iniciar_sesion()
        self.assertEqual(self.client.get("/academico").status_code, 200)
        respuesta = self.client.post(
            "/academico",
            data={
                "csrf_token": "incorrecto",
                "entidad": "nivel_grado",
                "operacion": "crear",
                "nombre_nivel": "Primario",
                "grado_año": "6to",
            },
        )
        self.assertEqual(respuesta.status_code, 400)
        with self.app.app_context():
            self.assertEqual(
                db.session.query(NivelGrado).filter_by(grado_año="6to").count(),
                0,
            )

    def _iniciar_sesion(self):
        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        response = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "academico",
                "password": "Clave-segura-123!",
            },
        )
        self.assertEqual(response.status_code, 302)


class HistorialGrupoMigracionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "migration-test",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory / 'legacy.sqlite3'}",
                "BACKUP_FOLDER": str(directory / "backups"),
                "MIGRATIONS_DIRECTORY": str(ROOT / "migrations"),
            }
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def test_backfill_mantiene_matricula_y_registra_grupo_inicial(self):
        with self.app.app_context():
            config = self.app.extensions["migrate"].migrate.get_config(
                self.app.config["MIGRATIONS_DIRECTORY"]
            )
            command.upgrade(config, "ab41d879c562")
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO tutor (id, nombre, dni_cuit) VALUES (10, 'Tutor', 'T-10')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO alumno (id, id_tutor, nombre, apellido, dni) "
                    "VALUES (20, 10, 'Ana', 'Paz', 'A-20')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO anio_lectivo "
                    "(id, numero_ciclo, fecha_inicio, fecha_fin) "
                    "VALUES (30, 2026, '2026-03-01', '2027-02-28')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO nivel_grado (id, nombre_nivel, grado_año) "
                    "VALUES (40, 'Secundario', '1er Año')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO grupo_seccion "
                    "(id, id_nivel, seccion, capacidad_maxima) VALUES (50, 40, 'A', 30)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO matricula "
                    "(id, id_alumno, id_anio, id_grupo, fecha_inscripcion, estado, repitente) "
                    "VALUES (60, 20, 30, 50, '2026-03-05', 'Activa', 0)"
                )
            command.upgrade(config, "head")
            db.session.expire_all()
            matricula = db.session.get(Matricula, 60)
            historial = db.session.query(HistorialGrupoMatricula).one()
            self.assertEqual(matricula.id, 60)
            self.assertEqual(matricula.id_grupo, 50)
            self.assertEqual(historial.id_matricula, 60)
            self.assertEqual(historial.id_grupo, 50)
            self.assertEqual(historial.fecha_desde, date(2026, 3, 5))
            self.assertIsNone(historial.fecha_hasta)
            nullable = db.session.execute(
                text("PRAGMA table_info('grupo_seccion')")
            ).all()
            columna_seccion = next(row for row in nullable if row[1] == "seccion")
            self.assertEqual(columna_seccion[3], 0)

    def test_preflight_detiene_grupos_duplicados_sin_descartarlos(self):
        with self.app.app_context():
            config = self.app.extensions["migrate"].migrate.get_config(
                self.app.config["MIGRATIONS_DIRECTORY"]
            )
            command.upgrade(config, "4a9e3cb713d1")
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO nivel_grado (id, nombre_nivel, grado_año) "
                    "VALUES (70, 'Secundario', '2do Año')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO grupo_seccion "
                    "(id, id_nivel, seccion, capacidad_maxima) VALUES (80, 70, 'A', 30)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO grupo_seccion "
                    "(id, id_nivel, seccion, capacidad_maxima) VALUES (81, 70, 'A', 25)"
                )
            with self.assertRaisesRegex(RuntimeError, "grupos duplicados"):
                command.upgrade(config, "head")
            with db.engine.connect() as connection:
                grupos = connection.exec_driver_sql(
                    "SELECT id, seccion FROM grupo_seccion WHERE id IN (80, 81) ORDER BY id"
                ).all()
                tablas = {
                    row[0]
                    for row in connection.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).all()
                }
            self.assertEqual(grupos, [(80, "A"), (81, "A")])
            self.assertNotIn("historial_grupo_matricula", tablas)

    def test_migracion_convierte_seccion_vacia_en_division_nula(self):
        with self.app.app_context():
            config = self.app.extensions["migrate"].migrate.get_config(
                self.app.config["MIGRATIONS_DIRECTORY"]
            )
            command.upgrade(config, "4a9e3cb713d1")
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO nivel_grado (id, nombre_nivel, grado_año) "
                    "VALUES (90, 'Secundario', '3er Año')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO grupo_seccion "
                    "(id, id_nivel, seccion, capacidad_maxima) "
                    "VALUES (91, 90, '', 30)"
                )

            command.upgrade(config, "head")
            with self.assertRaises(IntegrityError):
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "INSERT INTO grupo_seccion "
                        "(id_nivel, seccion, capacidad_maxima) "
                        "VALUES (90, NULL, 30)"
                    )
            with db.engine.connect() as connection:
                grupo = connection.exec_driver_sql(
                    "SELECT seccion FROM grupo_seccion WHERE id = 91"
                ).scalar_one()
            self.assertIsNone(grupo)


if __name__ == "__main__":
    unittest.main()

import json
import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.database import db, migrar_esquema
from app.models import (
    Alumno,
    AnioLectivo,
    Asignatura,
    Calificacion,
    CondicionMateria,
    CursoDireccion,
    Docente,
    EventoAuditoria,
    GrupoSeccion,
    InscripcionMateria,
    IntentoCalificacion,
    Matricula,
    NivelGrado,
    Tutor,
)
from app.services import consultar_calificaciones, crear_usuario, registrar_intento_calificacion


ROOT = Path(__file__).resolve().parents[1]


class CalificacionesTrimestralesTests(unittest.TestCase):
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
            actor = crear_usuario("notas", "Clave-segura-notas!", bootstrap=True)
            nivel = NivelGrado(nombre_nivel="Secundario", grado_año="1er Año")
            grupo = GrupoSeccion(nivel=nivel, seccion="A", capacidad_maxima=30)
            anio = AnioLectivo(
                numero_ciclo=2026,
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2027, 2, 28),
            )
            tutor = Tutor(nombre="Responsable", dni_cuit="TEST-NOTAS-TUTOR")
            alumno = Alumno(
                tutor=tutor,
                nombre="Alumna",
                apellido="Prueba",
                dni="TEST-NOTAS-ALUMNA",
            )
            asignatura = Asignatura(nombre_materia="Artes Visuales", carga_horaria=4)
            docente = Docente(nombre="Docente de prueba", legajo_laboral="TEST-NOTAS-DOC")
            matricula = Matricula(
                alumno=alumno,
                anio_lectivo=anio,
                grupo=grupo,
                fecha_inscripcion=date(2026, 3, 1),
            )
            db.session.add_all(
                [nivel, grupo, anio, tutor, alumno, asignatura, docente, matricula]
            )
            db.session.flush()
            curso = CursoDireccion(
                docente=docente,
                asignatura=asignatura,
                grupo=grupo,
            )
            inscripcion = InscripcionMateria(
                matricula=matricula,
                asignatura=asignatura,
            )
            db.session.add_all([curso, inscripcion])
            db.session.commit()
            self.actor_id = actor.id
            self.inscripcion_id = inscripcion.id
            self.matricula_id = matricula.id
            self.curso_id = curso.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def _login(self):
        response = self.client.get("/login")
        with self.client.session_transaction() as browser_session:
            csrf = browser_session["csrf_token"]
        response = self.client.post(
            "/login",
            data={
                "csrf_token": csrf,
                "username": "notas",
                "password": "Clave-segura-notas!",
            },
        )
        self.assertEqual(response.status_code, 302)

    def _csrf(self):
        self.client.get("/calificaciones")
        with self.client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def test_guarda_notas_validas_como_intentos_independientes(self):
        with self.app.app_context():
            for valor in (1, 10, "A"):
                registrar_intento_calificacion(
                    self.inscripcion_id,
                    1,
                    "PARCIAL_1",
                    valor,
                    actor_id=self.actor_id,
                )

            intentos = (
                db.session.query(IntentoCalificacion)
                .filter_by(id_inscripcion_materia=self.inscripcion_id)
                .order_by(IntentoCalificacion.id)
                .all()
            )
            self.assertEqual([intento.valor for intento in intentos], ["1", "10", "A"])
            self.assertEqual(
                [intento.trimestre for intento in intentos],
                [1, 1, 1],
            )
            self.assertEqual(
                [intento.actor_id for intento in intentos],
                [self.actor_id] * 3,
            )
            eventos = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="calificacion.intento_registrado")
                .all()
            )
            self.assertEqual(len(eventos), 3)
            self.assertEqual([evento.actor_id for evento in eventos], [self.actor_id] * 3)

    def test_rechaza_notas_instancias_y_trimestres_invalidos(self):
        with self.app.app_context():
            for valor in (0, 11, "0", "11", "5.0", "AUS", "a", True):
                with self.subTest(valor=valor):
                    with self.assertRaises(ValueError):
                        registrar_intento_calificacion(
                            self.inscripcion_id,
                            1,
                            "PARCIAL_1",
                            valor,
                            actor_id=self.actor_id,
                        )
            for trimestre in (0, 4):
                with self.assertRaises(ValueError):
                    registrar_intento_calificacion(
                        self.inscripcion_id,
                        trimestre,
                        "PARCIAL_1",
                        8,
                        actor_id=self.actor_id,
                    )
            with self.assertRaises(ValueError):
                registrar_intento_calificacion(
                    self.inscripcion_id,
                    1,
                    "EVALUACION_INVENTADA",
                    8,
                    actor_id=self.actor_id,
                )
            self.assertEqual(db.session.query(IntentoCalificacion).count(), 0)

    def test_snapshot_libre_y_nulo_no_alteran_condicion_vigente(self):
        with self.app.app_context():
            inscripcion = db.session.get(InscripcionMateria, self.inscripcion_id)
            inscripcion.id_condicion = 3
            db.session.commit()

            intento_libre = registrar_intento_calificacion(
                self.inscripcion_id,
                2,
                "RECUPERATORIO",
                9,
                actor_id=self.actor_id,
            )
            self.assertEqual(intento_libre.id_condicion_rendida, 3)
            self.assertEqual(inscripcion.id_condicion, 3)
            self.assertEqual(
                db.session.get(CondicionMateria, intento_libre.id_condicion_rendida).codigo,
                "LIBRE",
            )

            inscripcion.id_condicion = 1
            db.session.commit()
            intento_aprobado_preexistente = registrar_intento_calificacion(
                self.inscripcion_id,
                2,
                "PARCIAL_2",
                10,
                actor_id=self.actor_id,
            )
            self.assertEqual(intento_aprobado_preexistente.id_condicion_rendida, 1)
            self.assertEqual(inscripcion.id_condicion, 1)

            inscripcion.id_condicion = None
            db.session.commit()
            intento_cursando = registrar_intento_calificacion(
                self.inscripcion_id,
                3,
                "NOTA_FINAL",
                10,
                actor_id=self.actor_id,
            )
            self.assertIsNone(intento_cursando.id_condicion_rendida)
            self.assertIsNone(inscripcion.id_condicion)

    def test_consulta_audita_solo_filtros_y_cantidad(self):
        with self.app.app_context():
            registrar_intento_calificacion(
                self.inscripcion_id,
                1,
                "DIAGNOSTICO",
                8,
                actor_id=self.actor_id,
            )
            _, intentos = consultar_calificaciones(
                self.inscripcion_id,
                1,
                actor_id=self.actor_id,
            )
            self.assertEqual(len(intentos), 1)
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="calificaciones.consultadas")
                .order_by(EventoAuditoria.id.desc())
                .first()
            )
            detalles = json.loads(evento.detalles_json)
            self.assertEqual(evento.actor_id, self.actor_id)
            self.assertEqual(detalles["resultados"]["intentos"], 1)
            self.assertNotIn("valor", evento.detalles_json)
            self.assertNotIn('"8"', evento.detalles_json)

    def test_intento_no_se_puede_editar_ni_borrar(self):
        with self.app.app_context():
            intento = registrar_intento_calificacion(
                self.inscripcion_id,
                1,
                "DIAGNOSTICO",
                8,
                actor_id=self.actor_id,
            )
            intento.valor = "9"
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            intento = db.session.get(IntentoCalificacion, intento.id)
            self.assertEqual(intento.valor, "8")
            db.session.delete(intento)
            with self.assertRaisesRegex(ValueError, "intento_calificacion"):
                db.session.flush()
            db.session.rollback()
            self.assertIsNotNone(db.session.get(IntentoCalificacion, intento.id))

    def test_preserva_calificacion_legacy_y_no_actualiza_condicion_por_nota(self):
        with self.app.app_context():
            legacy = Calificacion(
                id_matricula=self.matricula_id,
                id_curso_dir=self.curso_id,
                parcial_1="7",
                eval_trimestral="A",
                periodo_evaluacion="1° Trimestre",
            )
            db.session.add(legacy)
            db.session.commit()
            legacy_id = legacy.id

            registrar_intento_calificacion(
                self.inscripcion_id,
                1,
                "NOTA_FINAL",
                10,
                actor_id=self.actor_id,
            )

            conservada = db.session.get(Calificacion, legacy_id)
            inscripcion = db.session.get(InscripcionMateria, self.inscripcion_id)
            self.assertEqual(conservada.parcial_1, "7")
            self.assertEqual(conservada.eval_trimestral, "A")
            self.assertIsNone(inscripcion.id_condicion)

    def test_migracion_de_intentos_conserva_filas_legacy_sin_transformarlas(self):
        migracion_temporal = tempfile.TemporaryDirectory()
        directory = Path(migracion_temporal.name)
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key-not-for-production",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory / 'legacy.sqlite3'}",
                "BACKUP_FOLDER": str(directory / "backups"),
                "MIGRATIONS_DIRECTORY": str(ROOT / "migrations"),
            }
        )
        try:
            with app.app_context():
                extension = app.extensions["migrate"].migrate
                config = extension.get_config(app.config["MIGRATIONS_DIRECTORY"])
                command.upgrade(config, "81b5a7d209c4")

                nivel = NivelGrado(nombre_nivel="Secundario", grado_año="1er Año")
                grupo = GrupoSeccion(nivel=nivel, seccion="A", capacidad_maxima=30)
                anio = AnioLectivo(
                    numero_ciclo=2026,
                    fecha_inicio=date(2026, 3, 1),
                    fecha_fin=date(2027, 2, 28),
                )
                tutor = Tutor(nombre="Responsable", dni_cuit="TEST-LEGACY-TUTOR")
                alumno = Alumno(
                    tutor=tutor,
                    nombre="Alumno",
                    apellido="Histórico",
                    dni="TEST-LEGACY-ALUMNO",
                )
                asignatura = Asignatura(
                    nombre_materia="Artes Visuales",
                    carga_horaria=4,
                )
                docente = Docente(
                    nombre="Docente de prueba",
                    legajo_laboral="TEST-LEGACY-DOC",
                )
                matricula = Matricula(
                    alumno=alumno,
                    anio_lectivo=anio,
                    grupo=grupo,
                    fecha_inscripcion=date(2026, 3, 1),
                )
                db.session.add_all(
                    [
                        nivel,
                        grupo,
                        anio,
                        tutor,
                        alumno,
                        asignatura,
                        docente,
                        matricula,
                    ]
                )
                db.session.flush()
                curso = CursoDireccion(
                    docente=docente,
                    asignatura=asignatura,
                    grupo=grupo,
                )
                db.session.add(curso)
                db.session.flush()
                legacy = Calificacion(
                    id_matricula=matricula.id,
                    id_curso_dir=curso.id,
                    diagnostico="A",
                    parcial_1="6",
                    parcial_2="7",
                    eval_trimestral="8",
                    recuperatorio=None,
                    nota_final="8",
                    periodo_evaluacion="1° Trimestre",
                )
                db.session.add(legacy)
                db.session.commit()
                legacy_id = legacy.id

                migrar_esquema(app)

                conservada = db.session.get(Calificacion, legacy_id)
                self.assertEqual(
                    (
                        conservada.diagnostico,
                        conservada.parcial_1,
                        conservada.parcial_2,
                        conservada.eval_trimestral,
                        conservada.recuperatorio,
                        conservada.nota_final,
                        conservada.periodo_evaluacion,
                    ),
                    ("A", "6", "7", "8", None, "8", "1° Trimestre"),
                )
                self.assertEqual(db.session.query(IntentoCalificacion).count(), 0)
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
            migracion_temporal.cleanup()

    def test_migracion_aborta_con_mensaje_si_hay_inscripciones_duplicadas(self):
        archivo_migracion = (
            ROOT
            / "migrations"
            / "versions"
            / "c51d7a2e9f04_append_only_grade_attempts.py"
        )
        especificacion = importlib.util.spec_from_file_location(
            "migracion_intentos",
            archivo_migracion,
        )
        migracion = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(migracion)

        engine = create_engine("sqlite://")
        try:
            with engine.begin() as conexion:
                conexion.exec_driver_sql(
                    "CREATE TABLE condicion_materia "
                    "(id INTEGER PRIMARY KEY, codigo TEXT UNIQUE, nombre TEXT, activo BOOLEAN)"
                )
                conexion.exec_driver_sql(
                    "INSERT INTO condicion_materia (id, codigo, nombre, activo) VALUES "
                    "(1, 'APROBADO', 'Aprobado', 1), "
                    "(2, 'DESAPROBADO', 'Desaprobado', 1), "
                    "(3, 'LIBRE', 'Libre', 1)"
                )
                conexion.exec_driver_sql(
                    "CREATE TABLE inscripcion_materia "
                    "(id INTEGER PRIMARY KEY, id_matricula INTEGER NOT NULL, "
                    "id_asignatura INTEGER NOT NULL, id_condicion INTEGER)"
                )
                conexion.exec_driver_sql(
                    "INSERT INTO inscripcion_materia "
                    "(id, id_matricula, id_asignatura) VALUES "
                    "(1, 7, 12), (2, 7, 12)"
                )
                with Operations.context(MigrationContext.configure(conexion)):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "matrícula 7, asignatura 12",
                    ):
                        migracion.upgrade()
                tablas = {
                    fila[0]
                    for fila in conexion.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertNotIn("intento_calificacion", tablas)
        finally:
            engine.dispose()

    def test_pantalla_autenticada_csrf_y_guardado_por_post(self):
        self.assertEqual(self.client.get("/calificaciones").status_code, 302)
        self._login()
        pagina = self.client.get("/calificaciones")
        self.assertEqual(pagina.status_code, 200)
        self.assertIn(b"Historial de intentos", pagina.data)

        csrf = self._csrf()
        sin_token = self.client.post(
            "/calificaciones",
            data={
                "id_inscripcion_materia": self.inscripcion_id,
                "trimestre": 1,
                "tipo_evaluacion": "PARCIAL_1",
                "valor": 8,
            },
        )
        self.assertEqual(sin_token.status_code, 400)

        respuesta = self.client.post(
            "/calificaciones",
            data={
                "csrf_token": csrf,
                "id_inscripcion_materia": self.inscripcion_id,
                "trimestre": 1,
                "tipo_evaluacion": "PARCIAL_1",
                "valor": 8,
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.query(IntentoCalificacion).count(), 1)
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="calificacion.intento_registrado")
                .one()
            )
            self.assertEqual(evento.actor_id, self.actor_id)


if __name__ == "__main__":
    unittest.main()

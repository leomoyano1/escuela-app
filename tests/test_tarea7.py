import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app import create_app
from app.database import db, migrar_esquema
from app.models import (
    Alumno,
    AnioLectivo,
    EventoAuditoria,
    GrupoSeccion,
    HistorialGrupoMatricula,
    Matricula,
    NivelGrado,
    Tutor,
)
from app.services import (
    crear_usuario,
    editar_alumno_existente,
    editar_tutor_existente,
    obtener_alumno_mantenimiento,
)


ROOT = Path(__file__).resolve().parents[1]


class MantenimientoAlumnosTutoresTests(unittest.TestCase):
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
            actor = crear_usuario("tarea7", "Clave-segura-tarea7!", bootstrap=True)
            nivel = NivelGrado(nombre_nivel="Secundario", grado_año="1er Año")
            grupo = GrupoSeccion(nivel=nivel, seccion="A", capacidad_maxima=30)
            anio = AnioLectivo(
                numero_ciclo=2026,
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2027, 2, 28),
            )
            tutor = Tutor(
                nombre="Responsable inicial",
                dni_cuit="TEST-TUTOR-7",
                telefono="381000000",
                direccion="Domicilio de prueba",
            )
            alumno = Alumno(
                tutor=tutor,
                nombre="Nombre inicial",
                apellido="Apellido inicial",
                dni="TEST-ALUMNO-7",
                fecha_nacimiento=date(2012, 5, 6),
                legajo="LEG-HIST-7",
            )
            matricula = Matricula(
                alumno=alumno,
                anio_lectivo=anio,
                grupo=grupo,
                fecha_inscripcion=date(2026, 3, 1),
            )
            db.session.add_all([nivel, grupo, anio, tutor, alumno, matricula])
            db.session.flush()
            historial = HistorialGrupoMatricula(
                matricula=matricula,
                grupo=grupo,
                fecha_desde=date(2026, 3, 1),
            )
            db.session.add(historial)
            db.session.commit()
            self.actor_id = actor.id
            self.alumno_id = alumno.id
            self.tutor_id = tutor.id
            self.anio_id = anio.id
            self.grupo_id = grupo.id
            self.matricula_id = matricula.id
            self.historial_id = historial.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def test_edita_alumno_sin_cambiar_legajo_matricula_ni_historial(self):
        with self.app.app_context():
            alumno = editar_alumno_existente(
                self.alumno_id,
                "Nombre actualizado",
                "Apellido actualizado",
                "TEST-ALUMNO-7",
                date(2012, 5, 6),
                actor_id=self.actor_id,
            )
            self.assertEqual(alumno.legajo, "LEG-HIST-7")
            matriculas = db.session.query(Matricula).filter_by(
                id_alumno=self.alumno_id
            ).all()
            self.assertEqual([matricula.id for matricula in matriculas], [self.matricula_id])
            periodos = db.session.query(HistorialGrupoMatricula).filter_by(
                id_matricula=self.matricula_id
            ).all()
            self.assertEqual([periodo.id for periodo in periodos], [self.historial_id])

            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(
                    entidad="alumno",
                    entidad_id=str(self.alumno_id),
                    accion="alumno.editado",
                )
                .one()
            )
            self.assertEqual(evento.actor_id, self.actor_id)
            cambios = json.loads(evento.detalles_json)["cambios"]
            self.assertEqual(
                cambios["nombre"],
                {"anterior": "Nombre inicial", "nuevo": "Nombre actualizado"},
            )
            self.assertNotIn("legajo", cambios)

    def test_edita_tutor_existente_y_audita_solo_campos_modificados(self):
        with self.app.app_context():
            editar_tutor_existente(
                self.tutor_id,
                "Responsable actualizado",
                "TEST-TUTOR-7",
                "381111111",
                "Nuevo domicilio",
                "responsable@example.invalid",
                actor_id=self.actor_id,
            )
            alumno = db.session.get(Alumno, self.alumno_id)
            self.assertEqual(alumno.id_tutor, self.tutor_id)
            tutor = db.session.get(Tutor, self.tutor_id)
            self.assertEqual(tutor.telefono, "381111111")
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(
                    entidad="tutor",
                    entidad_id=str(self.tutor_id),
                    accion="tutor.editado",
                )
                .one()
            )
            self.assertEqual(evento.actor_id, self.actor_id)
            cambios = json.loads(evento.detalles_json)["cambios"]
            self.assertEqual(
                cambios["direccion"],
                {"anterior": "Domicilio de prueba", "nuevo": "Nuevo domicilio"},
            )
            self.assertNotIn("dni_cuit", cambios)

    def test_matricula_es_unica_por_alumno_y_anio_incluso_si_tiene_baja(self):
        with self.app.app_context():
            original = db.session.get(Matricula, self.matricula_id)
            original.fecha_baja = date(2026, 12, 1)
            db.session.commit()
            with self.assertRaises(IntegrityError):
                db.session.add(
                    Matricula(
                        id_alumno=self.alumno_id,
                        id_anio=self.anio_id,
                        id_grupo=self.grupo_id,
                        fecha_inscripcion=date(2026, 12, 2),
                    )
                )
                db.session.flush()
            db.session.rollback()

            nuevo_anio = AnioLectivo(
                numero_ciclo=2027,
                fecha_inicio=date(2027, 3, 1),
                fecha_fin=date(2028, 2, 29),
            )
            db.session.add(nuevo_anio)
            db.session.flush()
            matricula_siguiente = Matricula(
                id_alumno=self.alumno_id,
                id_anio=nuevo_anio.id,
                id_grupo=self.grupo_id,
                fecha_inscripcion=date(2027, 3, 1),
            )
            db.session.add(matricula_siguiente)
            db.session.commit()
            self.assertNotEqual(matricula_siguiente.id, self.matricula_id)

    def test_datos_invalidos_no_se_persisten_y_lectura_no_copia_contenido(self):
        with self.app.app_context():
            with self.assertRaisesRegex(ValueError, "no puede ser futura"):
                editar_alumno_existente(
                    self.alumno_id,
                    "No debe persistir",
                    "Apellido",
                    "TEST-ALUMNO-7",
                    date(2999, 1, 1),
                    actor_id=self.actor_id,
                )
            alumno = obtener_alumno_mantenimiento(
                self.alumno_id,
                actor_id=self.actor_id,
            )
            self.assertEqual(alumno.nombre, "Nombre inicial")
            evento_lectura = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="alumno.ficha_consultada")
                .one()
            )
            self.assertEqual(
                json.loads(evento_lectura.detalles_json),
                {"resultado": "cargado"},
            )

    def test_interfaz_mantenimiento_requiere_sesion_y_csrf(self):
        respuesta_sin_sesion = self.client.get("/alumnos")
        self.assertEqual(respuesta_sin_sesion.status_code, 302)

        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.actor_id)
            session["_fresh"] = True
            session["csrf_token"] = "token-de-prueba"

        respuesta = self.client.get(f"/alumnos/{self.alumno_id}/editar")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"Legajo escolar", respuesta.data)
        respuesta_post = self.client.post(
            f"/alumnos/{self.alumno_id}/editar",
            data={
                "csrf_token": "token-de-prueba",
                "nombre": "Nombre por web",
                "apellido": "Apellido inicial",
                "dni": "TEST-ALUMNO-7",
                "fecha_nacimiento": "2012-05-06",
            },
        )
        self.assertEqual(respuesta_post.status_code, 302)

        respuesta_sin_csrf = self.client.post(
            f"/tutores/{self.tutor_id}/editar",
            data={"nombre": "Cambio rechazado"},
        )
        self.assertEqual(respuesta_sin_csrf.status_code, 400)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command

from app import create_app
from app.database import db, migrar_esquema
from app.models import (
    Alumno,
    AnioLectivo,
    Asistencia,
    EventoAuditoria,
    GrupoSeccion,
    Matricula,
    NivelGrado,
    NotificacionAsistencia,
    Tutor,
)
from app.services import (
    consultar_asistencias,
    contar_faltas_injustificadas,
    crear_usuario,
    registrar_asistencia,
)


ROOT = Path(__file__).resolve().parents[1]


class AsistenciaYJustificacionesTests(unittest.TestCase):
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
            actor = crear_usuario("asistencia", "Clave-segura-asistencia!", bootstrap=True)
            nivel = NivelGrado(nombre_nivel="Secundario", grado_año="1er Año")
            grupo = GrupoSeccion(nivel=nivel, seccion="A", capacidad_maxima=30)
            anio = AnioLectivo(
                numero_ciclo=2026,
                fecha_inicio=date(2026, 3, 1),
                fecha_fin=date(2027, 2, 28),
            )
            tutor = Tutor(nombre="Responsable", dni_cuit="TEST-ASIST-TUTOR")
            alumno = Alumno(
                tutor=tutor,
                nombre="Alumna",
                apellido="Prueba",
                dni="TEST-ASIST-ALUMNA",
            )
            matricula = Matricula(
                alumno=alumno,
                anio_lectivo=anio,
                grupo=grupo,
                fecha_inscripcion=date(2026, 3, 1),
            )
            db.session.add_all([nivel, grupo, anio, tutor, alumno, matricula])
            db.session.commit()
            self.actor_id = actor.id
            self.matricula_id = matricula.id
            self.anio_id = anio.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def test_valores_se_eligen_explicitos_y_se_aceptan_solo_los_tres_cortes(self):
        with self.app.app_context():
            for dia, valor in enumerate((0, 0.5, 1), start=1):
                registrar_asistencia(
                    self.matricula_id,
                    date(2026, 4, dia),
                    valor,
                    actor_id=self.actor_id,
                )
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("1.5"),
            )
            for dia, valor in enumerate((1.5, -0.5, 2, "07:11", True), start=10):
                with self.subTest(valor=valor), self.assertRaises(ValueError):
                    registrar_asistencia(
                        self.matricula_id,
                        date(2026, 4, dia),
                        valor,
                        actor_id=self.actor_id,
                    )
            self.assertEqual(db.session.query(Asistencia).count(), 3)

    def test_justificacion_conserva_actor_fecha_observaciones_y_no_cuenta(self):
        with self.app.app_context():
            asistencia = registrar_asistencia(
                self.matricula_id,
                date(2026, 5, 1),
                1,
                justificada=True,
                observaciones="Certificado presentado",
                actor_id=self.actor_id,
            )
            primera_fecha = asistencia.justificada_en
            self.assertEqual(asistencia.justificada_por_id, self.actor_id)
            self.assertIsNotNone(primera_fecha)
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("0"),
            )

            registrar_asistencia(
                self.matricula_id,
                date(2026, 5, 1),
                1,
                justificada=False,
                observaciones="Certificado presentado",
                actor_id=self.actor_id,
            )
            asistencia = db.session.get(Asistencia, asistencia.id)
            self.assertFalse(asistencia.justificada)
            self.assertEqual(asistencia.justificada_por_id, self.actor_id)
            self.assertEqual(asistencia.justificada_en, primera_fecha)
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("1"),
            )

            eventos = (
                db.session.query(EventoAuditoria)
                .filter_by(entidad="asistencia", entidad_id=str(asistencia.id))
                .order_by(EventoAuditoria.id)
                .all()
            )
            self.assertEqual(len(eventos), 2)
            self.assertTrue(all(evento.actor_id == self.actor_id for evento in eventos))
            cambio_inicial = json.loads(eventos[0].detalles_json)["cambios"]
            self.assertEqual(cambio_inicial["justificada"]["nuevo"], True)
            self.assertEqual(
                cambio_inicial["justificada_por_id"]["nuevo"],
                self.actor_id,
            )
            cambio_reversion = json.loads(eventos[1].detalles_json)["cambios"]
            self.assertEqual(cambio_reversion["justificada"]["anterior"], True)
            self.assertEqual(cambio_reversion["justificada"]["nuevo"], False)

    def test_avisa_al_llegar_a_quince_y_por_cada_falta_injustificada_siguiente(self):
        with self.app.app_context():
            for numero in range(1, 15):
                registrar_asistencia(
                    self.matricula_id,
                    date(2026, 6, numero),
                    1,
                    actor_id=self.actor_id,
                )
            self.assertEqual(db.session.query(NotificacionAsistencia).count(), 0)

            matricula = db.session.get(Matricula, self.matricula_id)
            estado_original = matricula.estado
            registrar_asistencia(
                self.matricula_id,
                date(2026, 6, 15),
                1,
                actor_id=self.actor_id,
            )
            registrar_asistencia(
                self.matricula_id,
                date(2026, 6, 16),
                1,
                actor_id=self.actor_id,
            )
            registrar_asistencia(
                self.matricula_id,
                date(2026, 6, 17),
                1,
                actor_id=self.actor_id,
            )

            avisos = (
                db.session.query(NotificacionAsistencia)
                .order_by(NotificacionAsistencia.id)
                .all()
            )
            self.assertEqual(
                [aviso.faltas_injustificadas for aviso in avisos],
                [Decimal("15.0"), Decimal("16.0"), Decimal("17.0")],
            )
            self.assertEqual([aviso.actor_id for aviso in avisos], [self.actor_id] * 3)
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("17"),
            )
            self.assertEqual(matricula.estado, estado_original)
            eventos = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="asistencia.notificacion_generada")
                .order_by(EventoAuditoria.id)
                .all()
            )
            self.assertEqual(len(eventos), 3)
            self.assertTrue(all(evento.actor_id == self.actor_id for evento in eventos))

    def test_justificada_no_dispara_aviso_hasta_que_se_valida_como_injustificada(self):
        with self.app.app_context():
            for numero in range(1, 15):
                registrar_asistencia(
                    self.matricula_id,
                    date(2026, 7, numero),
                    1,
                    actor_id=self.actor_id,
                )
            registrar_asistencia(
                self.matricula_id,
                date(2026, 7, 15),
                1,
                justificada=True,
                actor_id=self.actor_id,
            )
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("14"),
            )
            self.assertEqual(db.session.query(NotificacionAsistencia).count(), 0)

            registrar_asistencia(
                self.matricula_id,
                date(2026, 7, 15),
                1,
                justificada=False,
                actor_id=self.actor_id,
            )
            self.assertEqual(
                contar_faltas_injustificadas(self.matricula_id, self.actor_id),
                Decimal("15"),
            )
            self.assertEqual(db.session.query(NotificacionAsistencia).count(), 1)

    def test_consulta_auditada_solo_registra_filtros_y_cantidad(self):
        with self.app.app_context():
            registrar_asistencia(
                self.matricula_id,
                date(2026, 8, 1),
                0.5,
                observaciones="Dato que no debe copiarse a la auditoría de lectura",
                actor_id=self.actor_id,
            )
            _, registros, _, contadores = consultar_asistencias(
                self.matricula_id,
                actor_id=self.actor_id,
            )
            self.assertEqual(len(registros), 1)
            self.assertEqual(contadores[self.matricula_id], Decimal("0.5"))
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="asistencias.consultadas")
                .order_by(EventoAuditoria.id.desc())
                .first()
            )
            self.assertEqual(evento.actor_id, self.actor_id)
            detalles = json.loads(evento.detalles_json)
            self.assertEqual(
                detalles["filtros"]["id_matricula"],
                self.matricula_id,
            )
            self.assertNotIn("Dato que no debe copiarse", evento.detalles_json)

    def test_ruta_exige_sesion_csrf_y_permision_no_depende_de_horarios(self):
        self.assertEqual(self.client.get("/asistencias").status_code, 302)
        with self.client.session_transaction() as browser_session:
            csrf = browser_session.get("csrf_token")
        if csrf is None:
            self.client.get("/login")
            with self.client.session_transaction() as browser_session:
                csrf = browser_session["csrf_token"]
        login = self.client.post(
            "/login",
            data={
                "csrf_token": csrf,
                "username": "asistencia",
                "password": "Clave-segura-asistencia!",
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(self.client.get("/asistencias").status_code, 200)

        payload = {
            "id_matricula": str(self.matricula_id),
            "fecha": "2026-09-10",
            "valor_falta": "0.5",
        }
        self.assertEqual(
            self.client.post("/asistencias", data=payload).status_code,
            400,
        )
        with self.client.session_transaction() as browser_session:
            payload["csrf_token"] = browser_session["csrf_token"]
        respuesta = self.client.post("/asistencias", data=payload)
        self.assertEqual(respuesta.status_code, 302)
        with self.app.app_context():
            asistencia = db.session.query(Asistencia).one()
            self.assertEqual(asistencia.valor_falta, 0.5)


class MigracionAsistenciaTests(unittest.TestCase):
    def test_migracion_conserva_asistencia_legacy(self):
        temporary = tempfile.TemporaryDirectory()
        try:
            directory = Path(temporary.name)
            app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "test-key-not-for-production",
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory / 'legacy.sqlite3'}",
                    "BACKUP_FOLDER": str(directory / "backups"),
                    "MIGRATIONS_DIRECTORY": str(ROOT / "migrations"),
                }
            )
            with app.app_context():
                extension = app.extensions["migrate"].migrate
                config = extension.get_config(app.config["MIGRATIONS_DIRECTORY"])
                command.upgrade(config, "c51d7a2e9f04")
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "INSERT INTO usuario "
                        "(id, username, password_hash, activo, creado_en) "
                        "VALUES (1, 'legacy', 'hash-no-usable', 1, '2026-01-01')"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO tutor (id, nombre, dni_cuit) VALUES (1, 'Tutor', 'T-1')"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO alumno (id, id_tutor, nombre, apellido, dni) "
                        "VALUES (1, 1, 'Ana', 'Paz', 'A-1')"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO anio_lectivo "
                        "(id, numero_ciclo, fecha_inicio, fecha_fin) "
                        "VALUES (1, 2026, '2026-03-01', '2027-02-28')"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO nivel_grado (id, nombre_nivel, grado_año) "
                        "VALUES (1, 'Secundario', '1er Año')"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO grupo_seccion "
                        "(id, id_nivel, seccion, capacidad_maxima) VALUES (1, 1, 'A', 30)"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO matricula "
                        "(id, id_alumno, id_anio, id_grupo, fecha_inscripcion, estado, repitente) "
                        "VALUES (1, 1, 1, 1, '2026-03-01', 'Activa', 0)"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO asistencia "
                        "(id, id_matricula, fecha, hora_llegada, valor_falta) "
                        "VALUES (73, 1, '2026-03-02', '07:11', 0.5)"
                    )

                migrar_esquema(app)
                asistencia = db.session.get(Asistencia, 73)
                self.assertIsNotNone(asistencia)
                self.assertEqual(asistencia.id_matricula, 1)
                self.assertEqual(asistencia.valor_falta, 0.5)
                self.assertEqual(asistencia.hora_llegada, "07:11")
                self.assertFalse(asistencia.justificada)
                self.assertIsNone(asistencia.justificada_por_id)
        finally:
            if "app" in locals():
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()

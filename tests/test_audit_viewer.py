import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import create_app
from app.audit import registrar_evento_auditoria
from app.database import db, migrar_esquema
from app.models import EventoAuditoria, Usuario
from app.services import crear_usuario


class VisorAuditoriaTests(unittest.TestCase):
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

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directorio.cleanup()

    def _csrf(self, ruta: str) -> str:
        with self.client.session_transaction() as browser_session:
            token = browser_session.get("csrf_token")
        if token is None:
            self.client.get(ruta)
            with self.client.session_transaction() as browser_session:
                token = browser_session["csrf_token"]
        return token

    def _crear_cuenta_inicial(self) -> None:
        self.client.post(
            "/setup",
            data={
                "csrf_token": self._csrf("/setup"),
                "username": "directora",
                "password": "ClaveSegura-2026!",
                "confirm_password": "ClaveSegura-2026!",
            },
        )

    def _crear_eventos(self) -> tuple[int, int]:
        with self.app.app_context():
            usuarios = db.session.query(Usuario).order_by(Usuario.id).all()
            director = usuarios[0]
            segundo = crear_usuario(
                "secretaria",
                "OtraClaveSegura-2026!",
                actor_id=director.id,
            )
            evento = registrar_evento_auditoria(
                "ficha.abierta",
                "alumno",
                "17",
                detalles={
                    "cambios": {
                        "dni": {"anterior": "DNI-PRIVADO-ANTERIOR", "nuevo": "DNI-PRIVADO-NUEVO"},
                        "estado": {"anterior": "inactivo", "nuevo": "activo"},
                        "password_hash": {"anterior": "HASH-PRIVADO", "nuevo": "HASH-NUEVO"},
                        "access_token": "TOKEN-PRIVADO",
                    },
                    "resultado": "cargado",
                },
                actor_id=director.id,
            )
            otro = registrar_evento_auditoria(
                "calendario.consultado",
                "calendario",
                detalles={"cantidad": 2},
                actor_id=segundo.id,
            )
            db.session.commit()
            return evento.id, otro.id

    def test_sesion_requerida_y_visor_sin_rutas_mutantes(self):
        respuesta_sin_sesion = self.client.get("/auditoria")
        self.assertEqual(respuesta_sin_sesion.status_code, 302)

        self._crear_cuenta_inicial()
        self.assertEqual(self.client.get("/auditoria").status_code, 200)
        self.assertEqual(self.client.post("/auditoria").status_code, 405)

        reglas_visor = [
            regla
            for regla in self.app.url_map.iter_rules()
            if regla.endpoint == "main.auditoria"
        ]
        self.assertEqual(len(reglas_visor), 1)
        self.assertEqual(reglas_visor[0].methods, {"GET", "HEAD", "OPTIONS"})
        self.assertFalse(
            any(
                regla.rule.startswith("/auditoria/")
                and regla.endpoint != "main.auditoria"
                for regla in self.app.url_map.iter_rules()
            )
        )

    def test_filtros_usuario_fecha_entidad_y_accion(self):
        self._crear_cuenta_inicial()
        self._crear_eventos()
        with self.app.app_context():
            directora = db.session.query(Usuario).filter_by(username="directora").one()
            secretaria = db.session.query(Usuario).filter_by(username="secretaria").one()

        hoy = datetime.now(timezone.utc).date().isoformat()
        respuesta = self.client.get(
            "/auditoria",
            query_string={
                "usuario": directora.id,
                "desde": hoy,
                "hasta": hoy,
                "entidad": "alumno",
                "accion": "ficha.abierta",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(f"ficha.abierta".encode(), respuesta.data)
        self.assertIn(f"Registro:</strong> 17".encode(), respuesta.data)
        self.assertNotIn(b"<h2>calendario.consultado", respuesta.data)

        respuesta_sin_coincidencias = self.client.get(
            "/auditoria",
            query_string={"usuario": secretaria.id, "entidad": "alumno"},
        )
        self.assertEqual(respuesta_sin_coincidencias.status_code, 200)
        self.assertNotIn(b"<h2>ficha.abierta", respuesta_sin_coincidencias.data)

        respuesta_fecha_invalida = self.client.get(
            "/auditoria",
            query_string={"desde": "fecha-invalida"},
        )
        self.assertEqual(respuesta_fecha_invalida.status_code, 400)
        self.assertIn("formato AAAA-MM-DD".encode(), respuesta_fecha_invalida.data)

    def test_detalles_redactan_credenciales_y_datos_sensibles_y_lectura_auditada(self):
        self._crear_cuenta_inicial()
        self._crear_eventos()
        respuesta = self.client.get(
            "/auditoria",
            query_string={"accion": "ficha.abierta"},
        )
        contenido = respuesta.get_data(as_text=True)
        for secreto in (
            "DNI-PRIVADO-ANTERIOR",
            "DNI-PRIVADO-NUEVO",
            "HASH-PRIVADO",
            "HASH-NUEVO",
            "TOKEN-PRIVADO",
        ):
            self.assertNotIn(secreto, contenido)
        self.assertIn("[REDACTADO]", contenido)
        self.assertIn('"estado"', contenido)

        with self.app.app_context():
            evento_lectura = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="auditoria.consultada")
                .order_by(EventoAuditoria.id.desc())
                .first()
            )
            detalles = json.loads(evento_lectura.detalles_json)
            self.assertEqual(detalles["filtros"]["accion"], "ficha.abierta")
            self.assertEqual(detalles["resultados"], 1)
            self.assertNotIn("DNI-PRIVADO", evento_lectura.detalles_json)
            self.assertNotIn("TOKEN-PRIVADO", evento_lectura.detalles_json)

    def test_indicador_del_visor_detecta_cadena_alterada(self):
        self._crear_cuenta_inicial()
        self._crear_eventos()
        with self.app.app_context():
            evento_id = db.session.query(EventoAuditoria.id).order_by(EventoAuditoria.id).first()[0]
            with db.engine.begin() as conexion:
                conexion.exec_driver_sql("DROP TRIGGER evento_auditoria_no_update")
                conexion.exec_driver_sql(
                    "UPDATE evento_auditoria SET resultado = 'alterado' WHERE id = ?",
                    (evento_id,),
                )

        respuesta = self.client.get("/auditoria")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("No se pudo verificar la integridad".encode(), respuesta.data)
        self.assertNotIn("Integridad local verificada.".encode(), respuesta.data)

    def test_comandos_locales_crean_y_restauran_respaldo_verificado(self):
        self._crear_cuenta_inicial()
        runner = self.app.test_cli_runner()
        resultado_respaldo = runner.invoke(args=["db-backup"])
        self.assertEqual(resultado_respaldo.exit_code, 0, resultado_respaldo.output)
        ruta_respaldo = Path(resultado_respaldo.output.strip().split(": ", 1)[1])
        self.assertTrue(ruta_respaldo.is_file())

        with self.app.app_context():
            directora = db.session.query(Usuario).filter_by(username="directora").one()
            directora.activo = False
            db.session.commit()

        resultado_restauracion = runner.invoke(
            args=["db-restore", str(ruta_respaldo)]
        )
        self.assertEqual(
            resultado_restauracion.exit_code,
            0,
            resultado_restauracion.output,
        )
        with self.app.app_context():
            db.session.expire_all()
            directora = db.session.query(Usuario).filter_by(username="directora").one()
            self.assertTrue(directora.activo)


if __name__ == "__main__":
    unittest.main()

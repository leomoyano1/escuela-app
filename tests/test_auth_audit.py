import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.audit import verificar_integridad_auditoria
from app.database import db, migrar_esquema
from app.models import EventoAuditoria, Usuario
from app.services import crear_usuario


class AutenticacionYAuditoriaTests(unittest.TestCase):
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

    def token_csrf(self, ruta: str) -> str:
        with self.client.session_transaction() as sesion:
            token = sesion.get("csrf_token")
        if token is None:
            respuesta = self.client.get(ruta)
            self.assertIn(respuesta.status_code, (200, 302))
            with self.client.session_transaction() as sesion:
                token = sesion["csrf_token"]
        return token

    def crear_cuenta_inicial(self) -> None:
        token = self.token_csrf("/setup")
        respuesta = self.client.post(
            "/setup",
            data={
                "csrf_token": token,
                "username": "directora",
                "password": "ClaveSegura-2026!",
                "confirm_password": "ClaveSegura-2026!",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

    def test_login_redirige_a_configuracion_inicial_sin_cuentas(self):
        respuesta = self.client.get("/login")
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers["Location"].endswith("/setup"))

    def test_configuracion_inicial_login_logout_y_cuentas_sin_roles(self):
        self.crear_cuenta_inicial()

        with self.app.app_context():
            directora = db.session.query(Usuario).filter_by(username="directora").one()
            self.assertNotEqual(directora.password_hash, "ClaveSegura-2026!")
            self.assertTrue(directora.check_password("ClaveSegura-2026!"))

        token = self.token_csrf("/accounts")
        respuesta = self.client.post(
            "/accounts",
            data={
                "csrf_token": token,
                "username": "secretaria",
                "password": "OtraClaveSegura-2026!",
                "confirm_password": "OtraClaveSegura-2026!",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        token = self.token_csrf("/logout")
        respuesta = self.client.post("/logout", data={"csrf_token": token})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.client.get("/accounts").status_code, 302)

        token = self.token_csrf("/login")
        respuesta = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "secretaria",
                "password": "OtraClaveSegura-2026!",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.client.get("/accounts").status_code, 200)

        with self.app.app_context():
            usuarios = db.session.query(Usuario).order_by(Usuario.id).all()
            self.assertEqual([usuario.username for usuario in usuarios], ["directora", "secretaria"])
            self.assertEqual([usuario.activo for usuario in usuarios], [True, True])
            self.assertTrue(verificar_integridad_auditoria())
            eventos_cuenta = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="cuenta.creada")
                .order_by(EventoAuditoria.id)
                .all()
            )
            self.assertEqual(len(eventos_cuenta), 2)
            self.assertEqual(
                [evento.actor_id for evento in eventos_cuenta],
                [usuarios[0].id, usuarios[0].id],
            )
            evento_lectura = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="cuentas.listadas")
                .order_by(EventoAuditoria.id.desc())
                .first()
            )
            self.assertEqual(evento_lectura.actor_id, usuarios[1].id)

    def test_alta_de_cuenta_y_evento_se_revierten_juntos(self):
        self.crear_cuenta_inicial()

        with self.app.app_context():
            directora = db.session.query(Usuario).filter_by(username="directora").one()
            with patch(
                "app.services.registrar_evento_auditoria",
                side_effect=RuntimeError("fallo simulado al registrar auditoría"),
            ):
                with self.assertRaisesRegex(RuntimeError, "fallo simulado"):
                    crear_usuario(
                        "cuenta_incompleta",
                        "ClaveSegura-2026!",
                        actor_id=directora.id,
                    )

            self.assertIsNone(
                db.session.query(Usuario)
                .filter_by(username="cuenta_incompleta")
                .first()
            )
            self.assertTrue(verificar_integridad_auditoria())

    def test_configuracion_inicial_no_se_repite_y_solo_desde_loopback(self):
        self.crear_cuenta_inicial()
        respuesta = self.client.get("/setup")
        self.assertEqual(respuesta.status_code, 302)

        self.assertEqual(
            self.client.get(
                "/setup",
                environ_base={"REMOTE_ADDR": "192.0.2.10"},
            ).status_code,
            403,
        )
        with self.app.app_context():
            self.assertEqual(db.session.query(Usuario).count(), 1)

    def test_login_fallido_queda_auditado_sin_revelar_si_usuario_existe(self):
        self.crear_cuenta_inicial()
        self.client.post("/logout", data={"csrf_token": self.token_csrf("/logout")})
        token = self.token_csrf("/login")

        respuesta = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "directora",
                "password": "incorrecta",
            },
        )
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn("Usuario o contraseña incorrectos", respuesta.get_data(as_text=True))

        with self.app.app_context():
            evento = (
                db.session.query(EventoAuditoria)
                .filter_by(accion="autenticacion.fallida")
                .one()
            )
            self.assertIsNone(evento.actor_id)
            self.assertEqual(evento.resultado, "fallido")
            self.assertIn("directora", evento.detalles_json)
            self.assertNotIn("incorrecta", evento.detalles_json)
            self.assertTrue(verificar_integridad_auditoria())

    def test_cadena_detecta_manipulacion_y_base_rechaza_edicion_eventos(self):
        self.crear_cuenta_inicial()

        with self.app.app_context():
            evento_id = db.session.query(EventoAuditoria.id).order_by(EventoAuditoria.id).first()[0]
            with self.assertRaisesRegex(ValueError, "inmutables"):
                db.session.execute(
                    update(EventoAuditoria)
                    .where(EventoAuditoria.id == evento_id)
                    .values(resultado="alterado")
                )
            db.session.rollback()

            with self.assertRaisesRegex(ValueError, "borrar"):
                db.session.execute(
                    delete(EventoAuditoria).where(EventoAuditoria.id == evento_id)
                )
            db.session.rollback()

            with self.assertRaises(IntegrityError):
                with db.engine.begin() as conexion:
                    conexion.exec_driver_sql(
                        "UPDATE evento_auditoria SET resultado = 'alterado' WHERE id = ?",
                        (evento_id,),
                    )

            with self.assertRaises(IntegrityError):
                with db.engine.begin() as conexion:
                    conexion.exec_driver_sql(
                        "DELETE FROM evento_auditoria WHERE id = ?",
                        (evento_id,),
                    )

            with db.engine.begin() as conexion:
                conexion.exec_driver_sql("DROP TRIGGER evento_auditoria_no_update")
                conexion.exec_driver_sql(
                    "UPDATE evento_auditoria SET resultado = 'alterado' WHERE id = ?",
                    (evento_id,),
                )
            db.session.expire_all()
            self.assertFalse(verificar_integridad_auditoria())

    def test_csrf_y_contraseñas_debilies_rechazados(self):
        respuesta = self.client.post(
            "/setup",
            data={
                "username": "directora",
                "password": "corta",
                "confirm_password": "corta",
            },
        )
        self.assertEqual(respuesta.status_code, 400)

        token = self.token_csrf("/setup")
        respuesta = self.client.post(
            "/setup",
            data={
                "csrf_token": token,
                "username": "directora",
                "password": "corta",
                "confirm_password": "corta",
            },
        )
        self.assertEqual(respuesta.status_code, 400)

        with self.app.app_context():
            self.assertEqual(db.session.query(Usuario).count(), 0)


if __name__ == "__main__":
    unittest.main()

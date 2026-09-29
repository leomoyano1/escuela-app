import unittest
from datetime import date
from decimal import Decimal
from typing import Any

from flask import Flask

from app.database import db, init_db
from app.models import (
    Alumno,
    AnioLectivo,
    CondicionMateria,
    DetalleFactura,
    DescuentoTipo,
    Factura,
    GrupoSeccion,
    Matricula,
    NivelGrado,
    Tutor,
)
from app.routes import bp
from app.services import ConceptoFacturable, crear_factura


def crear_modelo(modelo: Any, **atributos: Any) -> Any:
    return modelo(**atributos)


class FuncionesExistentesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        cls.app.register_blueprint(bp)
        cls.context = cls.app.app_context()
        cls.context.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.context.pop()

    def setUp(self):
        db.drop_all()
        init_db()

        self.tutor = crear_modelo(Tutor, nombre="Tutor", dni_cuit="T-1")
        self.anio = crear_modelo(
            AnioLectivo,
            numero_ciclo=2026,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
        nivel = crear_modelo(NivelGrado, nombre_nivel="Secundario", grado_año="1")
        self.grupo = crear_modelo(GrupoSeccion, nivel=nivel, seccion="A")
        self.descuento = crear_modelo(
            DescuentoTipo,
            codigo="HERMANO",
            nombre="Descuento por hermano",
            porcentaje=10,
        )
        self.alumno = crear_modelo(
            Alumno,
            tutor=self.tutor,
            nombre="Ana",
            apellido="Paz",
            dni="A-1",
        )
        self.matricula = crear_modelo(
            Matricula,
            alumno=self.alumno,
            anio_lectivo=self.anio,
            grupo=self.grupo,
            descuento_tipo=self.descuento,
        )
        db.session.add_all(
            [self.tutor, self.anio, nivel, self.grupo, self.descuento, self.alumno, self.matricula]
        )
        db.session.commit()

    def test_ruta_raiz_responde_estado_ok(self):
        respuesta = self.app.test_client().get("/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json(), {"status": "ok", "app": "Galileo Galilei"})

    def test_catalogo_de_condiciones_academicas_usa_ids_estables(self):
        condiciones = db.session.query(CondicionMateria).order_by(CondicionMateria.id).all()

        self.assertEqual(
            [(condicion.id, condicion.codigo) for condicion in condiciones],
            [(1, "APROBADO"), (2, "DESAPROBADO"), (3, "LIBRE")],
        )

    def test_crea_factura_aplicando_descuento_y_mora(self):
        factura = crear_factura(
            self.tutor.id,
            [ConceptoFacturable(self.matricula.id, "Cuota", Decimal("100"), Decimal("5"))],
        )
        detalle = db.session.query(DetalleFactura).filter_by(id_factura=factura.id).one()

        self.assertAlmostEqual(detalle.descuento_aplicado, 10.00)
        self.assertAlmostEqual(detalle.monto_final, 95.00)
        self.assertAlmostEqual(factura.total_pagar, 95.00)
        self.assertEqual(factura.estado_pago, "Pendiente")

    def test_rechaza_matricula_de_otro_tutor_y_revierte_factura(self):
        otro_tutor = crear_modelo(Tutor, nombre="Otro tutor", dni_cuit="T-2")
        otro_alumno = crear_modelo(
            Alumno,
            tutor=otro_tutor,
            nombre="Luis",
            apellido="Sol",
            dni="A-2",
        )
        otra_matricula = crear_modelo(
            Matricula,
            alumno=otro_alumno,
            anio_lectivo=self.anio,
            grupo=self.grupo,
        )
        db.session.add_all([otro_tutor, otro_alumno, otra_matricula])
        db.session.commit()

        with self.assertRaisesRegex(ValueError, "no pertenece"):
            crear_factura(
                self.tutor.id,
                [ConceptoFacturable(otra_matricula.id, "Cuota", Decimal("100"))],
            )

        self.assertEqual(db.session.query(Factura).count(), 0)

    def test_rechaza_importe_negativo_sin_persistir_factura(self):
        with self.assertRaisesRegex(ValueError, "no negativo"):
            crear_factura(
                self.tutor.id,
                [ConceptoFacturable(self.matricula.id, "Cuota", Decimal("-1"))],
            )

        self.assertEqual(db.session.query(Factura).count(), 0)


if __name__ == "__main__":
    unittest.main()
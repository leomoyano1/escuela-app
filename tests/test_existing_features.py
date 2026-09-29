import unittest
from datetime import date
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.database import db, init_db
from app.models import (
    Alumno,
    AnioLectivo,
    Asignatura,
    AspiranteCRM,
    CicloEscolar,
    CondicionMateria,
    DetalleFactura,
    DescuentoTipo,
    Factura,
    GrupoSeccion,
    InscripcionMateria,
    Matricula,
    NivelGrado,
    Tutor,
)
from app.routes import bp
from app.services import (
    ConceptoFacturable,
    DatosAspirante,
    crear_factura,
    listar_aspirantes,
    registrar_aspirante,
)


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
        self.nivel = crear_modelo(NivelGrado, nombre_nivel="Secundario", grado_año="1")
        self.grupo = crear_modelo(GrupoSeccion, nivel=self.nivel, seccion="A")
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
            [
                self.tutor,
                self.anio,
                self.nivel,
                self.grupo,
                self.descuento,
                self.alumno,
                self.matricula,
            ]
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

    def test_ciclo_escolar_guarda_fechas_y_repitente_inicia_en_cero(self):
        ciclo = crear_modelo(
            CicloEscolar,
            anio_lectivo=self.anio,
            fecha_apertura=date(2026, 3, 1),
            fecha_cierre=date(2026, 11, 30),
        )
        db.session.add(ciclo)
        db.session.commit()

        matricula = db.session.get(Matricula, self.matricula.id)
        if matricula is None:
            self.fail("La matrícula de prueba no fue encontrada.")
        self.assertEqual(matricula.repitente, 0)
        self.assertEqual(ciclo.anio_lectivo.id, self.anio.id)

    def test_repitente_solo_admite_cero_o_uno(self):
        self.matricula.repitente = 2
        db.session.add(self.matricula)

        with self.assertRaises(IntegrityError):
            db.session.commit()

        db.session.rollback()

    def test_condicion_libre_identifica_la_materia_previa(self):
        asignatura = crear_modelo(Asignatura, nombre_materia="Matemática")
        inscripcion = crear_modelo(
            InscripcionMateria,
            matricula=self.matricula,
            asignatura=asignatura,
            id_condicion=3,
        )
        db.session.add(inscripcion)
        db.session.commit()

        previas = (
            db.session.query(InscripcionMateria)
            .filter_by(id_matricula=self.matricula.id, id_condicion=3)
            .all()
        )

        self.assertEqual(len(previas), 1)
        self.assertEqual(previas[0].asignatura.nombre_materia, "Matemática")

    def test_registra_aspirante_en_espera_con_checklist(self):
        aspirante = registrar_aspirante(
            DatosAspirante(
                nombre="Luis",
                apellido="Sol",
                dni="A-2",
                fecha_nacimiento=date(2012, 4, 10),
                nombre_tutor="Tutor Sol",
                dni_cuit_tutor="T-2",
                telefono_whatsapp="3815550000",
                id_anio=self.anio.id,
                id_nivel=self.nivel.id,
                partida_nacimiento=1,
                documento=1,
                certificado_primaria=1,
            )
        )

        self.assertEqual(aspirante.estado, "En espera")
        self.assertEqual(aspirante.partida_nacimiento, 1)
        self.assertEqual(aspirante.documento, 1)
        self.assertEqual(aspirante.certificado_primaria, 1)
        self.assertIsNone(aspirante.id_alumno)
        self.assertEqual(len(listar_aspirantes()), 1)
        self.assertEqual(db.session.query(Alumno).filter_by(dni="A-2").count(), 0)

    def test_rechaza_flag_documental_distinto_de_cero_o_uno(self):
        with self.assertRaisesRegex(ValueError, "debe ser 0 o 1"):
            registrar_aspirante(
                DatosAspirante(
                    nombre="Luis",
                    apellido="Sol",
                    dni="A-3",
                    fecha_nacimiento=date(2012, 4, 10),
                    nombre_tutor="Tutor Sol",
                    dni_cuit_tutor="T-3",
                    documento=2,
                )
            )

        self.assertEqual(db.session.query(AspiranteCRM).count(), 0)

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
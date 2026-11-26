import unittest
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import call, patch

from flask import Flask
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.config import BASE_DIR, Config
from app.database import db, sembrar_catalogos_iniciales
from app.models import (
    Alumno,
    Asistencia,
    AnioLectivo,
    Asignatura,
    AspiranteCRM,
    Calificacion,
    CertificadoMedico,
    CicloEscolar,
    CondicionMateria,
    CursoDireccion,
    DetalleFactura,
    DescuentoTipo,
    Docente,
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
    dar_de_baja_alumno,
    dar_de_baja_aspirante,
    dar_de_baja_matricula,
    listar_aspirantes,
    listar_aspirantes_archivados,
    registrar_aspirante,
)
from app.pagos import crear_preferencia_pago


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
        db.session.remove()
        db.drop_all()
        db.create_all()
        sembrar_catalogos_iniciales()

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

    def test_health_responde_estado_ok(self):
        respuesta = self.app.test_client().get("/health")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json(), {"status": "ok", "app": "Galileo Galilei"})

    @patch("app.config.os.makedirs")
    def test_prepara_directorios_locales_al_iniciar(self, makedirs: Any):
        Config.prepare_storage()

        makedirs.assert_has_calls(
            [
                call(BASE_DIR / "data" / "uploads", exist_ok=True),
                call(BASE_DIR / "exports", exist_ok=True),
                call(BASE_DIR / "backups", exist_ok=True),
                call(BASE_DIR / "logs", exist_ok=True),
            ]
        )
        self.assertEqual(makedirs.call_count, 4)

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

    def crear_historial_academico_y_financiero(self):
        asignatura = crear_modelo(Asignatura, nombre_materia="Matemática")
        docente = crear_modelo(
            Docente,
            nombre="Docente",
            legajo_laboral="D-1",
        )
        curso = crear_modelo(
            CursoDireccion,
            docente=docente,
            asignatura=asignatura,
            grupo=self.grupo,
        )
        inscripcion = crear_modelo(
            InscripcionMateria,
            matricula=self.matricula,
            asignatura=asignatura,
            id_condicion=2,
        )
        calificacion = crear_modelo(
            Calificacion,
            matricula=self.matricula,
            curso_direccion=curso,
            nota_final="4",
        )
        asistencia = crear_modelo(
            Asistencia,
            matricula=self.matricula,
            fecha=date(2026, 6, 2),
            valor_falta=0.5,
        )
        certificado = crear_modelo(
            CertificadoMedico,
            matricula=self.matricula,
            fecha_presentacion=date(2026, 6, 3),
            diagnostico_observacion="Certificado presentado",
        )
        db.session.add_all(
            [
                asignatura,
                docente,
                curso,
                inscripcion,
                calificacion,
                asistencia,
                certificado,
            ]
        )
        factura = crear_factura(
            self.tutor.id,
            [ConceptoFacturable(self.matricula.id, "Cuota", Decimal("100"))],
        )
        return inscripcion, calificacion, asistencia, certificado, factura

    def test_bajas_logicas_preservan_historial_academico_y_financiero(self):
        inscripcion, calificacion, asistencia, certificado, factura = (
            self.crear_historial_academico_y_financiero()
        )

        with self.assertRaisesRegex(ValueError, "motivo de baja"):
            dar_de_baja_matricula(self.matricula.id, "  ")

        matricula = dar_de_baja_matricula(
            self.matricula.id,
            "Traslado a otro establecimiento",
            date(2026, 7, 1),
        )
        alumno = dar_de_baja_alumno(
            self.alumno.id,
            "Traslado a otra localidad",
            date(2026, 7, 2),
        )

        self.assertEqual(matricula.estado, "Activa")
        self.assertEqual(matricula.fecha_baja, date(2026, 7, 1))
        self.assertEqual(matricula.motivo_baja, "Traslado a otro establecimiento")
        self.assertEqual(alumno.fecha_baja, date(2026, 7, 2))
        self.assertEqual(alumno.motivo_baja, "Traslado a otra localidad")
        self.assertEqual(db.session.get(Matricula, self.matricula.id).id_alumno, alumno.id)
        self.assertIsNotNone(db.session.get(InscripcionMateria, inscripcion.id))
        self.assertEqual(db.session.get(Calificacion, calificacion.id).nota_final, "4")
        self.assertEqual(db.session.get(Asistencia, asistencia.id).valor_falta, 0.5)
        self.assertIsNotNone(db.session.get(CertificadoMedico, certificado.id))
        self.assertEqual(db.session.get(Factura, factura.id).estado_pago, "Pendiente")
        self.assertEqual(
            db.session.query(DetalleFactura).filter_by(id_factura=factura.id).count(),
            1,
        )
        with self.assertRaisesRegex(ValueError, "ya tiene una baja"):
            dar_de_baja_matricula(
                self.matricula.id,
                "No reemplazar el motivo original",
            )
        self.assertEqual(matricula.motivo_baja, "Traslado a otro establecimiento")

    def test_baja_logica_de_aspirante_no_altera_su_estado_de_inscripcion(self):
        aspirante = registrar_aspirante(
            DatosAspirante(
                nombre="Luis",
                apellido="Sol",
                dni="A-8",
                fecha_nacimiento=date(2012, 4, 10),
                nombre_tutor="Tutor Sol",
                dni_cuit_tutor="T-8",
            )
        )

        aspirante = dar_de_baja_aspirante(
            aspirante.id,
            "La familia desistió del trámite",
        )

        self.assertEqual(aspirante.estado, "En espera")
        self.assertEqual(aspirante.fecha_baja, date.today())
        self.assertEqual(aspirante.motivo_baja, "La familia desistió del trámite")
        self.assertIsNone(aspirante.id_alumno)
        self.assertEqual(listar_aspirantes(), [])
        self.assertEqual(listar_aspirantes_archivados(), [aspirante])

    def test_no_permite_borrado_fisico_ni_desvinculacion_de_matriculas(self):
        self.crear_historial_academico_y_financiero()

        with self.assertRaisesRegex(ValueError, "baja lógica"):
            db.session.delete(self.alumno)
            db.session.flush()
        db.session.rollback()

        with self.assertRaisesRegex(ValueError, "baja lógica"):
            db.session.execute(delete(Matricula).where(Matricula.id == self.matricula.id))

        self.alumno.matriculas.remove(self.matricula)
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        self.assertIsNotNone(db.session.get(Alumno, self.alumno.id))
        self.assertIsNotNone(db.session.get(Matricula, self.matricula.id))

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
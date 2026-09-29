from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .database import db
from .models import (
    AnioLectivo,
    AspiranteCRM,
    DetalleFactura,
    Factura,
    Matricula,
    NivelGrado,
    Tutor,
)


CENTAVO = Decimal("0.01")


@dataclass(frozen=True)
class ConceptoFacturable:
    id_matricula: int
    concepto: str
    monto_base: Decimal
    recargo_mora: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class DatosAspirante:
    nombre: str
    apellido: str
    dni: str
    fecha_nacimiento: date
    nombre_tutor: str
    dni_cuit_tutor: str
    telefono_whatsapp: str | None = None
    email_tutor: str | None = None
    direccion_tutor: str | None = None
    id_anio: int | None = None
    id_nivel: int | None = None
    legajo: str | None = None
    curso_interes: str | None = None
    estado_entrevista: str | None = None
    observaciones: str | None = None
    partida_nacimiento: int = 0
    documento: int = 0
    certificado_primaria: int = 0
    pase_otra_escuela: int = 0
    libre_deuda: int = 0
    plan_estudio: int = 0
    libro_matriz: int = 0
    materias_adeudadas: int = 0


def registrar_aspirante(datos: DatosAspirante) -> AspiranteCRM:
    """Guardar una ficha de aspirante en espera, sin crear aún un alumno."""
    nombre = _texto_requerido(datos.nombre, "nombre del alumno")
    apellido = _texto_requerido(datos.apellido, "apellido del alumno")
    dni = _texto_requerido(datos.dni, "DNI del alumno")
    nombre_tutor = _texto_requerido(datos.nombre_tutor, "nombre del tutor")
    dni_cuit_tutor = _texto_requerido(datos.dni_cuit_tutor, "DNI/CUIT del tutor")

    if datos.fecha_nacimiento > date.today():
        raise ValueError("La fecha de nacimiento no puede ser futura.")

    if datos.id_anio is not None and db.session.get(AnioLectivo, datos.id_anio) is None:
        raise ValueError("No existe el año lectivo indicado.")
    if datos.id_nivel is not None and db.session.get(NivelGrado, datos.id_nivel) is None:
        raise ValueError("No existe el nivel indicado.")

    flags = {
        "partida_nacimiento": _flag_documental(datos.partida_nacimiento, "partida de nacimiento"),
        "documento": _flag_documental(datos.documento, "documento"),
        "certificado_primaria": _flag_documental(
            datos.certificado_primaria,
            "certificado de primaria",
        ),
        "pase_otra_escuela": _flag_documental(datos.pase_otra_escuela, "pase de otra escuela"),
        "libre_deuda": _flag_documental(datos.libre_deuda, "libre deuda"),
        "plan_estudio": _flag_documental(datos.plan_estudio, "plan de estudio"),
        "libro_matriz": _flag_documental(datos.libro_matriz, "libro matriz"),
        "materias_adeudadas": _flag_documental(datos.materias_adeudadas, "materias adeudadas"),
    }

    aspirante = AspiranteCRM()
    aspirante.nombre = nombre
    aspirante.apellido = apellido
    aspirante.dni = dni
    aspirante.fecha_nacimiento = datos.fecha_nacimiento
    aspirante.nombre_tutor = nombre_tutor
    aspirante.dni_cuit_tutor = dni_cuit_tutor
    aspirante.telefono_whatsapp = _texto_opcional(datos.telefono_whatsapp)
    aspirante.email_tutor = _texto_opcional(datos.email_tutor)
    aspirante.direccion_tutor = _texto_opcional(datos.direccion_tutor)
    aspirante.id_anio = datos.id_anio
    aspirante.id_nivel = datos.id_nivel
    aspirante.legajo = _texto_opcional(datos.legajo)
    aspirante.curso_interes = _texto_opcional(datos.curso_interes)
    aspirante.estado_entrevista = _texto_opcional(datos.estado_entrevista)
    aspirante.estado = "En espera"
    aspirante.observaciones = _texto_opcional(datos.observaciones)
    for nombre_flag, valor in flags.items():
        setattr(aspirante, nombre_flag, valor)

    try:
        db.session.add(aspirante)
        db.session.commit()
        return aspirante
    except Exception:
        db.session.rollback()
        raise


def listar_aspirantes(estado: str = "En espera") -> list[AspiranteCRM]:
    """Obtener aspirantes por estado, ordenados del más antiguo al más reciente."""
    return (
        db.session.query(AspiranteCRM)
        .filter_by(estado=estado)
        .order_by(AspiranteCRM.fecha_registro, AspiranteCRM.id)
        .all()
    )


def _texto_requerido(valor: str, nombre: str) -> str:
    texto = valor.strip()
    if not texto:
        raise ValueError(f"El {nombre} es obligatorio.")
    return texto


def _texto_opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None


def _flag_documental(valor: int, nombre: str) -> int:
    if valor not in (0, 1):
        raise ValueError(f"El flag de {nombre} debe ser 0 o 1.")
    return valor


def crear_factura(
    id_tutor: int,
    conceptos: list[ConceptoFacturable],
    fecha_vencimiento: date | None = None,
    metodo_pago: str = "Efectivo",
) -> Factura:
    """Crear una factura aplicando descuentos del catálogo por matrícula."""
    if not conceptos:
        raise ValueError("La factura debe incluir al menos un concepto.")

    tutor = db.session.get(Tutor, id_tutor)
    if tutor is None:
        raise ValueError("No existe el tutor indicado.")

    factura = Factura(
        tutor=tutor,
        fecha_vencimiento=fecha_vencimiento,
        metodo_pago=metodo_pago,
    )
    db.session.add(factura)
    total = Decimal("0.00")

    try:
        for concepto in conceptos:
            base = _importe_no_negativo(concepto.monto_base, "monto base")
            mora = _importe_no_negativo(concepto.recargo_mora, "recargo por mora")
            matricula = db.session.get(Matricula, concepto.id_matricula)

            if matricula is None or matricula.alumno.id_tutor != id_tutor:
                raise ValueError("La matrícula no pertenece al tutor indicado.")
            if not concepto.concepto.strip():
                raise ValueError("Cada concepto debe tener una descripción.")

            descuento_tipo = matricula.descuento_tipo
            porcentaje = Decimal("0")
            if descuento_tipo is not None:
                if not descuento_tipo.activo:
                    raise ValueError("La matrícula tiene asignado un descuento inactivo.")
                porcentaje = Decimal(str(descuento_tipo.porcentaje))
                if porcentaje < 0 or porcentaje > 100:
                    raise ValueError("El porcentaje de descuento debe estar entre 0 y 100.")

            descuento = (base * porcentaje / Decimal("100")).quantize(
                CENTAVO,
                rounding=ROUND_HALF_UP,
            )
            importe_final = base - descuento + mora
            total += importe_final

            factura.detalles.append(
                DetalleFactura(
                    matricula=matricula,
                    concepto=concepto.concepto.strip(),
                    monto_base=float(base),
                    descuento_aplicado=float(descuento),
                    recargo_mora=float(mora),
                    monto_final=float(importe_final),
                )
            )

        factura.total_pagar = float(total.quantize(CENTAVO, rounding=ROUND_HALF_UP))
        db.session.commit()
        return factura
    except Exception:
        db.session.rollback()
        raise


def _importe_no_negativo(importe: Decimal, nombre: str) -> Decimal:
    try:
        valor = Decimal(str(importe)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError) as error:
        raise ValueError(f"El {nombre} debe ser un importe válido.") from error
    if not valor.is_finite() or valor < 0:
        raise ValueError(f"El {nombre} debe ser un importe no negativo.")
    return valor
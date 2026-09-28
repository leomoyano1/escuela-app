from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .database import db
from .models import DetalleFactura, Factura, Matricula, Tutor


CENTAVO = Decimal("0.01")


@dataclass(frozen=True)
class ConceptoFacturable:
    id_matricula: int
    concepto: str
    monto_base: Decimal
    recargo_mora: Decimal = Decimal("0.00")


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
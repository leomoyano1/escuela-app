import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from flask import has_request_context
from flask_login import current_user

from .database import db
from .models import EventoAuditoria

_CAMPOS_SECRETOS = (
    "password",
    "passwd",
    "token",
    "secret",
    "credential",
    "authorization",
    "cookie",
    "session",
)
_CAMPOS_SENSIBLES = (
    "dni",
    "cuit",
    "telefono",
    "phone",
    "direccion",
    "domicilio",
    "email",
    "nombre",
    "apellido",
    "nacimiento",
    "observacion",
    "motivo",
    "salud",
    "certificado",
    "calificacion",
    "nota",
    "valor",
    "username",
)


def registrar_evento_auditoria(
    accion: str,
    entidad: str,
    entidad_id: int | str | None = None,
    resultado: str = "correcto",
    detalles: dict[str, Any] | None = None,
    actor_id: int | None = None,
) -> EventoAuditoria:
    """Añadir un evento a la transacción activa y encadenarlo al anterior."""
    if actor_id is None and has_request_context() and current_user.is_authenticated:
        actor_id = int(current_user.get_id())

    ultimo_evento = (
        db.session.query(EventoAuditoria)
        .order_by(EventoAuditoria.id.desc())
        .first()
    )
    evento = EventoAuditoria(
        actor_id=actor_id,
        ocurrido_en=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        resultado=resultado,
        detalles_json=json.dumps(
            detalles or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        hash_anterior=ultimo_evento.hash_evento if ultimo_evento else None,
    )
    evento.hash_evento = _calcular_hash_evento(evento)
    db.session.add(evento)
    return evento


def verificar_integridad_auditoria() -> bool:
    """Comprobar continuidad y hash de todos los eventos almacenados."""
    hash_anterior: str | None = None
    eventos = db.session.query(EventoAuditoria).order_by(EventoAuditoria.id).all()
    for evento in eventos:
        if evento.hash_anterior != hash_anterior:
            return False
        if evento.hash_evento != _calcular_hash_evento(evento):
            return False
        hash_anterior = evento.hash_evento
    return True


def detalles_auditoria_visibles(detalles_json: str) -> dict[str, Any]:
    """Preparar detalles para el visor, ocultando secretos y datos sensibles."""
    try:
        detalles = json.loads(detalles_json)
    except (TypeError, json.JSONDecodeError):
        return {"detalle": "No se pudieron interpretar los detalles del evento."}

    if not isinstance(detalles, dict):
        return {"detalle": "El formato de detalles del evento no es válido."}

    def ocultar_valores(valor: Any) -> Any:
        if isinstance(valor, dict):
            resultado: dict[str, Any] = {}
            for clave, contenido in valor.items():
                clave_segura = str(clave)
                clave_normalizada = re.sub(r"[^a-z0-9]", "", clave_segura.lower())
                campos_redactados = _CAMPOS_SECRETOS + _CAMPOS_SENSIBLES
                if any(campo in clave_normalizada for campo in campos_redactados):
                    resultado[clave_segura] = "[REDACTADO]"
                else:
                    resultado[clave_segura] = ocultar_valores(contenido)
            return resultado
        if isinstance(valor, list):
            return [ocultar_valores(elemento) for elemento in valor]
        if valor is None or isinstance(valor, (str, int, float, bool)):
            return valor
        return str(valor)

    return ocultar_valores(detalles)


def _calcular_hash_evento(evento: EventoAuditoria) -> str:
    contenido = {
        "actor_id": evento.actor_id,
        "accion": evento.accion,
        "entidad": evento.entidad,
        "entidad_id": evento.entidad_id,
        "resultado": evento.resultado,
        "ocurrido_en": evento.ocurrido_en,
        "detalles_json": evento.detalles_json,
        "hash_anterior": evento.hash_anterior,
    }
    serializado = json.dumps(
        contenido,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()

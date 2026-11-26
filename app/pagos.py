from flask import current_app, request
from .audit import registrar_evento_auditoria
from .database import db
from .models import Factura
import mercadopago

def crear_preferencia_pago(factura_id: int, monto: float, titulo: str) -> str:
    """Crea una preferencia en MercadoPago y devuelve el link de pago (init_point)."""
    token = current_app.config.get("MP_ACCESS_TOKEN")
    if not token:
        registrar_evento_auditoria(
            "pago.error",
            "factura",
            factura_id,
            resultado="error",
            detalles={"error": "Falta MP_ACCESS_TOKEN en la configuración"}
        )
        raise ValueError("MercadoPago no está configurado.")

    sdk = mercadopago.SDK(token)

    # Se obtiene la URL de notificación desde la configuración
    notification_url = current_app.config.get("MP_NOTIFICATION_URL")

    preference_data = {
        "items": [
            {
                "title": titulo,
                "quantity": 1,
                "unit_price": float(monto),
                "currency_id": "ARS"
            }
        ],
        "payer": {
            "name": "Nombre de Prueba",
            "surname": "Apellido de Prueba",
            "email": "test_user_123456@testuser.com",
            "phone": {
                "area_code": "011",
                "number": "4444-4444"
            },
            "identification": {
                "type": "DNI",
                "number": "12345678"
            },
            "address": {
                "street_name": "Calle Falsa",
                "street_number": 123,
                "zip_code": "1000"
            }
        },
        "payment_methods": {
            "excluded_payment_methods": [
                {"id": "amex"}  # Ejemplo: excluir American Express
            ],
            "excluded_payment_types": [
                {"id": "atm"}   # Ejemplo: excluir cajeros (Red Link/Banelco)
            ],
            "installments": 6   # Máximo 6 cuotas
        },
        "external_reference": str(factura_id),
        "back_urls": {
            "success": "http://127.0.0.1:5000/pagos/success",
            "failure": "http://127.0.0.1:5000/pagos/failure",
            "pending": "http://127.0.0.1:5000/pagos/pending"
        },
        "auto_return": "approved",
        "notification_url": notification_url,
        "expires": True,
        "expiration_date_from": "2026-11-26T00:00:00.000-03:00",
        "expiration_date_to": "2026-12-31T23:59:59.000-03:00",
        "metadata": {
            "factura_id": factura_id,
            "origen": "escuela-app-v1"
        }
    }

    try:
        result = sdk.preference().create(preference_data)
        if result["status"] >= 400:
            raise ValueError(f"Error MP: {result['response']['message']}")
        
        init_point = result["response"]["init_point"]
        
        registrar_evento_auditoria(
            "pago.preferencia_creada",
            "factura",
            factura_id,
            detalles={"preference_id": result["response"]["id"]}
        )
        
        return init_point
    except Exception as e:
        registrar_evento_auditoria(
            "pago.error",
            "factura",
            factura_id,
            resultado="error",
            detalles={"error": str(e)}
        )
        raise

def procesar_notificacion_pago(payment_id: str) -> bool:
    """Valida el pago en MP y actualiza el estado de la factura."""
    token = current_app.config.get("MP_ACCESS_TOKEN")
    sdk = mercadopago.SDK(token)
    
    # Obtener detalle del pago desde API de MP
    payment_info = sdk.payment().get(payment_id)
    if payment_info["status"] != 200:
        return False
        
    payment = payment_info["response"]
    factura_id = payment.get("external_reference")
    status = payment.get("status") # ej: 'approved'
    
    if not factura_id:
        return False
        
    factura = db.session.get(Factura, int(factura_id))
    if factura:
        factura.estado_pago = status.capitalize()
        db.session.commit()
        registrar_evento_auditoria(
            "pago.actualizado",
            "factura",
            factura.id,
            detalles={"payment_id": payment_id, "nuevo_estado": status}
        )
        return True
    return False

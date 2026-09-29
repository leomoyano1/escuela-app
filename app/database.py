from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_db() -> None:
    """Crear tablas si aún no existen."""
    db.create_all()

    from .models import CondicionMateria

    condiciones_iniciales = (
        (1, "APROBADO", "Aprobado"),
        (2, "DESAPROBADO", "Desaprobado"),
        (3, "LIBRE", "Libre"),
    )
    for id_condicion, codigo, nombre in condiciones_iniciales:
        condicion = db.session.get(CondicionMateria, id_condicion)
        if condicion is None:
            condicion = CondicionMateria()
            condicion.id = id_condicion
            condicion.codigo = codigo
            condicion.nombre = nombre
            db.session.add(condicion)
    db.session.commit()

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
            db.session.add(
                CondicionMateria(
                    id=id_condicion,
                    codigo=codigo,
                    nombre=nombre,
                )
            )
    db.session.commit()

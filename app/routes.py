import ipaddress
import json
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash

from .audit import (
    detalles_auditoria_visibles,
    registrar_evento_auditoria,
    verificar_integridad_auditoria,
)
from .database import db
from .models import CicloEscolar, EventoAuditoria, Factura, NivelGrado, Usuario
from .services import (
    crear_asignatura,
    crear_anio_lectivo,
    crear_ciclo_escolar,
    crear_grupo_seccion,
    crear_nivel_grado,
    crear_usuario,
    editar_asignatura,
    editar_anio_lectivo,
    editar_ciclo_escolar,
    editar_grupo_seccion,
    editar_nivel_grado,
    editar_alumno_existente,
    editar_tutor_existente,
    listar_asignaturas,
    listar_alumnos_mantenimiento,
    listar_anios_lectivos,
    listar_ciclos_escolares,
    consultar_calificaciones,
    consultar_asistencias,
    registrar_asistencia,
    listar_grupos_secciones,
    listar_niveles_grados,
    listar_tutores_mantenimiento,
    listar_usuarios,
    obtener_alumno_mantenimiento,
    obtener_tutor_mantenimiento,
    registrar_intento_calificacion,
    registrar_aspirante,
    listar_aspirantes,
    editar_aspirante,
    bajar_aspirante,
    procesar_notificacion_pago,
    registrar_pago_manual,
    TIPOS_EVALUACION,
)

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    registrar_evento_auditoria(
        "panel.consultado",
        "aplicacion",
        detalles={"resultado": "cargado"},
    )
    db.session.commit()
    return render_template("dashboard.html", usuario=current_user)


@bp.route("/auditoria", methods=["GET"])
@login_required
def auditoria():
    filtros = {
        "usuario": request.args.get("usuario", "").strip(),
        "desde": request.args.get("desde", "").strip(),
        "hasta": request.args.get("hasta", "").strip(),
        "entidad": request.args.get("entidad", "").strip(),
        "accion": request.args.get("accion", "").strip(),
    }
    error = None
    fecha_desde = None
    fecha_hasta = None
    usuario_id = None
    pagina_texto = request.args.get("pagina", "1")
    pagina = int(pagina_texto) if re.fullmatch(r"[1-9][0-9]{0,5}", pagina_texto) else 1

    if (
        len(filtros["desde"]) > 10
        or len(filtros["hasta"]) > 10
        or len(filtros["entidad"]) > 80
        or len(filtros["accion"]) > 80
    ):
        error = "Los filtros seleccionados no son válidos."
    if filtros["usuario"]:
        if not re.fullmatch(r"[0-9]+", filtros["usuario"]):
            error = "El usuario seleccionado no es válido."
        else:
            usuario_id = int(filtros["usuario"])
    try:
        if filtros["desde"]:
            fecha_desde = date.fromisoformat(filtros["desde"])
            if fecha_desde.isoformat() != filtros["desde"]:
                raise ValueError
        if filtros["hasta"]:
            fecha_hasta = date.fromisoformat(filtros["hasta"])
            if fecha_hasta.isoformat() != filtros["hasta"]:
                raise ValueError
        if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
            error = "La fecha final no puede ser anterior a la fecha inicial."
    except ValueError:
        error = "Las fechas deben tener formato AAAA-MM-DD."

    consulta = db.session.query(EventoAuditoria).options(
        joinedload(EventoAuditoria.actor)
    )
    if error is None:
        if usuario_id is not None:
            consulta = consulta.filter(EventoAuditoria.actor_id == usuario_id)
        if fecha_desde:
            inicio = datetime.combine(fecha_desde, time.min, tzinfo=timezone.utc)
            consulta = consulta.filter(EventoAuditoria.ocurrido_en >= inicio.isoformat())
        if fecha_hasta:
            fin_exclusivo = datetime.combine(
                fecha_hasta + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
            consulta = consulta.filter(EventoAuditoria.ocurrido_en < fin_exclusivo.isoformat())
        if filtros["entidad"]:
            consulta = consulta.filter(EventoAuditoria.entidad == filtros["entidad"])
        if filtros["accion"]:
            consulta = consulta.filter(EventoAuditoria.accion == filtros["accion"])

    cantidad_total = consulta.count() if error is None else 0
    por_pagina = 50
    paginas = max(1, (cantidad_total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, paginas)
    eventos = (
        consulta.order_by(EventoAuditoria.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    ) if error is None else []
    integridad_valida = verificar_integridad_auditoria()
    registrar_evento_auditoria(
        "auditoria.consultada",
        "evento_auditoria",
        detalles={
            "filtros": {
                "usuario_id": usuario_id,
                "desde": fecha_desde.isoformat() if fecha_desde else None,
                "hasta": fecha_hasta.isoformat() if fecha_hasta else None,
                "entidad": filtros["entidad"][:80] or None,
                "accion": filtros["accion"][:80] or None,
            },
            "pagina": pagina,
            "resultados": cantidad_total,
            "integridad_valida": integridad_valida,
        },
    )
    db.session.commit()

    usuarios = db.session.query(Usuario).order_by(Usuario.username).all()
    entidades = [
        valor[0]
        for valor in db.session.query(EventoAuditoria.entidad)
        .distinct()
        .order_by(EventoAuditoria.entidad)
        .all()
    ]
    acciones = [
        valor[0]
        for valor in db.session.query(EventoAuditoria.accion)
        .distinct()
        .order_by(EventoAuditoria.accion)
        .all()
    ]
    eventos_visibles = [
        {
            "evento": evento,
            "detalles": detalles_auditoria_visibles(evento.detalles_json),
        }
        for evento in eventos
    ]
    return render_template(
        "auditoria.html",
        eventos=eventos_visibles,
        filtros=filtros,
        error=error,
        usuarios=usuarios,
        entidades=entidades,
        acciones=acciones,
        integridad_valida=integridad_valida,
        cantidad_total=cantidad_total,
        pagina=pagina,
        paginas=paginas,
    ), (400 if error else 200)


@bp.route("/health")
def health():
    return jsonify({"status": "ok", "app": "Galileo Galilei"})


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if not _es_loopback():
        abort(403)
    if db.session.query(Usuario.id).first() is not None:
        return redirect(url_for("main.index" if current_user.is_authenticated else "main.login"))

    error = None
    csrf_token = _obtener_token_csrf()
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            _validar_confirmacion_contrasena()
            usuario = crear_usuario(
                request.form.get("username", ""),
                request.form.get("password", ""),
                bootstrap=True,
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            session.clear()
            login_user(usuario)
            _obtener_token_csrf()
            registrar_evento_auditoria(
                "autenticacion.exitosa",
                "usuario",
                usuario.id,
                detalles={"username": usuario.username, "metodo": "configuracion_inicial"},
                actor_id=usuario.id,
            )
            db.session.commit()
            return redirect(url_for("main.index"))

    return render_template("setup.html", csrf_token=csrf_token, error=error), (
        400 if error else 200
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if db.session.query(Usuario.id).first() is None:
        return redirect(url_for("main.setup"))
    error = None
    csrf_token = _obtener_token_csrf()
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")

        username = request.form.get("username", "").strip().lower()
        usuario = db.session.query(Usuario).filter_by(username=username).first()
        password = request.form.get("password", "")
        valido = usuario is not None and usuario.activo and usuario.check_password(password)

        if not valido and (usuario is None or not usuario.activo):
            check_password_hash(current_app.config["DUMMY_PASSWORD_HASH"], password)
        if not valido:
            registrar_evento_auditoria(
                "autenticacion.fallida",
                "usuario",
                resultado="fallido",
                detalles={"username": username[:64]},
            )
            db.session.commit()
            error = "Usuario o contraseña incorrectos."
        else:
            session.clear()
            login_user(usuario)
            _obtener_token_csrf()
            registrar_evento_auditoria(
                "autenticacion.exitosa",
                "usuario",
                usuario.id,
                detalles={"username": usuario.username},
                actor_id=usuario.id,
            )
            db.session.commit()
            return redirect(url_for("main.index"))

    return render_template("login.html", csrf_token=csrf_token, error=error), (
        401 if error else 200
    )


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    if not _csrf_valido():
        abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
    usuario_id = int(current_user.get_id())
    registrar_evento_auditoria(
        "autenticacion.cerro_sesion",
        "usuario",
        usuario_id,
        actor_id=usuario_id,
    )
    db.session.commit()
    logout_user()
    session.clear()
    _obtener_token_csrf()
    return redirect(url_for("main.login"))


@bp.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    error = None
    csrf_token = _obtener_token_csrf()
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            _validar_confirmacion_contrasena()
            crear_usuario(
                request.form.get("username", ""),
                request.form.get("password", ""),
                actor_id=int(current_user.get_id()),
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(url_for("main.accounts"))

    usuarios = listar_usuarios()
    return render_template(
        "accounts.html",
        csrf_token=csrf_token,
        error=error,
        usuarios=usuarios,
    ), (400 if error else 200)


@bp.route("/calendario", methods=["GET", "POST"])
@login_required
def calendario():
    error = None
    formulario = {}
    editar_anio_id = _id_consulta(request.args.get("editar_anio"))
    editar_ciclo_id = _id_consulta(request.args.get("editar_ciclo"))

    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        formulario = request.form.to_dict()
        try:
            entidad = request.form.get("entidad", "")
            operacion = request.form.get("operacion", "")
            if entidad == "anio_lectivo":
                datos = {
                    "numero_ciclo": _entero_formulario("numero_ciclo", "número de ciclo"),
                    "fecha_inicio": _fecha_formulario("fecha_inicio", "fecha de inicio"),
                    "fecha_fin": _fecha_formulario("fecha_fin", "fecha de fin"),
                }
                if operacion == "crear":
                    crear_anio_lectivo(**datos)
                elif operacion == "editar":
                    editar_anio_lectivo(
                        id_anio=_entero_formulario("id_registro", "año lectivo"),
                        **datos,
                    )
                else:
                    raise ValueError("La operación solicitada no es válida.")
            elif entidad == "ciclo_escolar":
                datos_ciclo = {
                    "id_anio": _entero_formulario("id_anio", "año lectivo"),
                    "id_nivel": _id_opcional_formulario("id_nivel"),
                    "fecha_apertura": _fecha_formulario("fecha_apertura", "fecha de apertura"),
                    "fecha_cierre": _fecha_formulario("fecha_cierre", "fecha de cierre"),
                }
                if operacion == "crear":
                    crear_ciclo_escolar(**datos_ciclo)
                elif operacion == "editar":
                    editar_ciclo_escolar(
                        id_ciclo=_entero_formulario("id_registro", "ciclo escolar"),
                        **datos_ciclo,
                    )
                else:
                    raise ValueError("La operación solicitada no es válida.")
            else:
                raise ValueError("El tipo de calendario solicitado no es válido.")
        except ValueError as error_validacion:
            error = str(error_validacion)
            if formulario.get("operacion") == "editar":
                id_edicion = _id_consulta(request.form.get("id_registro"))
                if formulario.get("entidad") == "anio_lectivo":
                    editar_anio_id = id_edicion
                elif formulario.get("entidad") == "ciclo_escolar":
                    editar_ciclo_id = id_edicion
        else:
            return redirect(url_for("main.calendario"))

    anios = listar_anios_lectivos()
    ciclos = listar_ciclos_escolares()
    anio_edicion = next((anio for anio in anios if anio.id == editar_anio_id), None)
    ciclo_edicion = next((ciclo for ciclo in ciclos if ciclo.id == editar_ciclo_id), None)
    if editar_anio_id is not None and anio_edicion is None and error is None:
        error = "No existe el año lectivo seleccionado."
    if editar_ciclo_id is not None and ciclo_edicion is None and error is None:
        error = "No existe el ciclo escolar seleccionado."

    niveles = db.session.query(NivelGrado).order_by(NivelGrado.id).all()
    registrar_evento_auditoria(
        "calendario.niveles_listados",
        "nivel_grado",
        detalles={"cantidad": len(niveles), "filtros": {"uso": "formulario_calendario"}},
    )
    registrar_evento_auditoria(
        "calendario.consultado",
        "calendario",
        detalles={
            "filtros": {
                "anio_id": editar_anio_id,
                "ciclo_id": editar_ciclo_id,
            },
            "resultado": "cargado",
        },
    )
    db.session.commit()
    return render_template(
        "calendar.html",
        csrf_token=_obtener_token_csrf(),
        error=error,
        formulario=formulario,
        anios=anios,
        ciclos=ciclos,
        niveles=niveles,
        anio_edicion=anio_edicion,
        ciclo_edicion=ciclo_edicion,
    ), (400 if error else 200)


@bp.route("/academico", methods=["GET", "POST"])
@login_required
def academico():
    error = None
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        actor_id = int(current_user.get_id())
        entidad = request.form.get("entidad", "")
        operacion = request.form.get("operacion", "")
        try:
            if entidad == "nivel_grado":
                datos = {
                    "nombre_nivel": request.form.get("nombre_nivel", ""),
                    "grado_año": request.form.get("grado_año", ""),
                }
                if operacion == "crear":
                    crear_nivel_grado(**datos, actor_id=actor_id)
                elif operacion == "editar":
                    editar_nivel_grado(
                        _entero_formulario("id_registro", "nivel"),
                        **datos,
                        actor_id=actor_id,
                    )
                else:
                    raise ValueError("La operación solicitada no es válida.")
            elif entidad == "asignatura":
                datos = {
                    "nombre_materia": request.form.get("nombre_materia", ""),
                    "carga_horaria": _entero_no_negativo_formulario(
                        "carga_horaria", "carga horaria"
                    ),
                }
                if operacion == "crear":
                    crear_asignatura(**datos, actor_id=actor_id)
                elif operacion == "editar":
                    editar_asignatura(
                        _entero_formulario("id_registro", "asignatura"),
                        **datos,
                        actor_id=actor_id,
                    )
                else:
                    raise ValueError("La operación solicitada no es válida.")
            elif entidad == "grupo_seccion":
                datos_grupo = {
                    "id_nivel": _entero_formulario("id_nivel", "nivel"),
                    "seccion": request.form.get("seccion", ""),
                    "capacidad_maxima": _entero_formulario(
                        "capacidad_maxima", "capacidad máxima"
                    ),
                }
                if operacion == "crear":
                    crear_grupo_seccion(**datos_grupo, actor_id=actor_id)
                elif operacion == "editar":
                    editar_grupo_seccion(
                        _entero_formulario("id_registro", "grupo"),
                        **datos_grupo,
                        actor_id=actor_id,
                    )
                else:
                    raise ValueError("La operación solicitada no es válida.")
            else:
                raise ValueError("El catálogo solicitado no es válido.")
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(url_for("main.academico"))

    actor_id = int(current_user.get_id())
    niveles = listar_niveles_grados(actor_id=actor_id)
    asignaturas = listar_asignaturas(actor_id=actor_id)
    grupos = listar_grupos_secciones(actor_id=actor_id)
    registrar_evento_auditoria(
        "academico.catalogos_consultados",
        "catalogos_academicos",
        detalles={
            "filtros": {"catalogos": ["nivel_grado", "asignatura", "grupo_seccion"]},
            "resultados": {
                "nivel_grado": len(niveles),
                "asignatura": len(asignaturas),
                "grupo_seccion": len(grupos),
            },
        },
    )
    db.session.commit()
    return render_template(
        "academico.html",
        csrf_token=_obtener_token_csrf(),
        error=error,
        niveles=niveles,
        asignaturas=asignaturas,
        grupos=grupos,
    ), (400 if error else 200)


@bp.route("/alumnos")
@login_required
def alumnos():
    actor_id = int(current_user.get_id())
    alumnos_registrados = listar_alumnos_mantenimiento(actor_id=actor_id)
    tutores_registrados = listar_tutores_mantenimiento(actor_id=actor_id)
    return render_template(
        "alumnos.html",
        alumnos=alumnos_registrados,
        tutores=tutores_registrados,
    )


@bp.route("/calificaciones", methods=["GET", "POST"])
@login_required
def calificaciones():
    error = None
    id_inscripcion = None
    trimestre = 1
    tipo_evaluacion = ""
    valor = ""

    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            id_inscripcion = _entero_formulario(
                "id_inscripcion_materia",
                "inscripción por materia",
            )
            trimestre = _entero_formulario("trimestre", "trimestre")
            tipo_evaluacion = request.form.get("tipo_evaluacion", "")
            valor = request.form.get("valor", "")
            registrar_intento_calificacion(
                id_inscripcion_materia=id_inscripcion,
                trimestre=trimestre,
                tipo_evaluacion=tipo_evaluacion,
                valor=valor,
                actor_id=int(current_user.get_id()),
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(
                url_for(
                    "main.calificaciones",
                    id_inscripcion=id_inscripcion,
                    trimestre=trimestre,
                )
            )
    else:
        inscripcion_arg = request.args.get("id_inscripcion")
        if inscripcion_arg is not None:
            if not re.fullmatch(r"[0-9]+", inscripcion_arg):
                error = "La inscripción seleccionada no es válida."
            else:
                id_inscripcion = int(inscripcion_arg)
        trimestre_arg = request.args.get("trimestre", "1")
        if not re.fullmatch(r"[0-9]+", trimestre_arg) or int(trimestre_arg) not in (1, 2, 3):
            error = "El trimestre debe ser 1, 2 o 3."
            trimestre = 1
        else:
            trimestre = int(trimestre_arg)

    try:
        inscripciones, intentos = consultar_calificaciones(
            id_inscripcion_materia=id_inscripcion,
            trimestre=trimestre,
            actor_id=int(current_user.get_id()),
        )
    except ValueError as error_consulta:
        error = error or str(error_consulta)
        id_inscripcion = None
        if trimestre not in (1, 2, 3):
            trimestre = 1
        inscripciones, intentos = consultar_calificaciones(
            trimestre=trimestre,
            actor_id=int(current_user.get_id()),
        )

    return render_template(
        "calificaciones.html",
        csrf_token=_obtener_token_csrf(),
        error=error,
        inscripciones=inscripciones,
        intentos=intentos,
        id_inscripcion=id_inscripcion,
        trimestre=trimestre,
        tipo_evaluacion=tipo_evaluacion,
        valor=valor,
        tipos_evaluacion=TIPOS_EVALUACION,
    ), (400 if error else 200)


@bp.route("/asistencias", methods=["GET", "POST"])
@login_required
def asistencias():
    error = None
    id_matricula = None
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            id_matricula = _entero_formulario("id_matricula", "matrícula")
            justificada_form = request.form.get("justificada", "")
            if justificada_form not in ("", "1"):
                raise ValueError("La justificación debe ser explícita.")
            registrar_asistencia(
                id_matricula=id_matricula,
                fecha=_fecha_formulario("fecha", "fecha de asistencia"),
                valor_falta=request.form.get("valor_falta", ""),
                justificada=justificada_form == "1",
                observaciones=request.form.get("observaciones", ""),
                actor_id=int(current_user.get_id()),
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(
                url_for("main.asistencias", id_matricula=id_matricula)
            )
    else:
        matricula_arg = request.args.get("id_matricula")
        if matricula_arg is not None:
            if not re.fullmatch(r"[0-9]+", matricula_arg):
                error = "La matrícula seleccionada no es válida."
            else:
                id_matricula = int(matricula_arg)

    try:
        matriculas, registros, notificaciones, contadores = consultar_asistencias(
            id_matricula=id_matricula,
            actor_id=int(current_user.get_id()),
        )
    except ValueError as error_consulta:
        error = error or str(error_consulta)
        id_matricula = None
        matriculas, registros, notificaciones, contadores = consultar_asistencias(
            actor_id=int(current_user.get_id()),
        )

    return render_template(
        "asistencias.html",
        csrf_token=_obtener_token_csrf(),
        error=error,
        matriculas=matriculas,
        registros=registros,
        notificaciones=notificaciones,
        contadores=contadores,
        id_matricula=id_matricula,
        fecha_hoy=date.today().isoformat(),
    ), (400 if error else 200)


@bp.route("/alumnos/<int:id_alumno>/editar", methods=["GET", "POST"])
@login_required
def editar_alumno(id_alumno: int):
    error = None
    actor_id = int(current_user.get_id())
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            editar_alumno_existente(
                id_alumno=id_alumno,
                nombre=request.form.get("nombre", ""),
                apellido=request.form.get("apellido", ""),
                dni=request.form.get("dni", ""),
                fecha_nacimiento=_fecha_formulario(
                    "fecha_nacimiento",
                    "fecha de nacimiento",
                ),
                actor_id=actor_id,
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(url_for("main.editar_alumno", id_alumno=id_alumno))

    try:
        alumno = obtener_alumno_mantenimiento(id_alumno, actor_id=actor_id)
    except ValueError:
        abort(404)
    return render_template(
        "editar_alumno.html",
        alumno=alumno,
        error=error,
        csrf_token=_obtener_token_csrf(),
    ), (400 if error else 200)


@bp.route("/tutores/<int:id_tutor>/editar", methods=["GET", "POST"])
@login_required
def editar_tutor(id_tutor: int):
    error = None
    actor_id = int(current_user.get_id())
    if request.method == "POST":
        if not _csrf_valido():
            abort(400, description="La solicitud expiró. Recarga la página e intenta nuevamente.")
        try:
            editar_tutor_existente(
                id_tutor=id_tutor,
                nombre=request.form.get("nombre", ""),
                dni_cuit=request.form.get("dni_cuit", ""),
                telefono=request.form.get("telefono", ""),
                direccion=request.form.get("direccion", ""),
                email=request.form.get("email", ""),
                actor_id=actor_id,
            )
        except ValueError as error_validacion:
            error = str(error_validacion)
        else:
            return redirect(url_for("main.editar_tutor", id_tutor=id_tutor))

    try:
        tutor = obtener_tutor_mantenimiento(id_tutor, actor_id=actor_id)
    except ValueError:
        abort(404)
    return render_template(
        "editar_tutor.html",
        tutor=tutor,
        error=error,
        csrf_token=_obtener_token_csrf(),
    ), (400 if error else 200)


@bp.route("/aspirantes", methods=["GET", "POST"])
@login_required
def aspirantes():
    """Listado y alta de aspirantes."""
    if request.method == "POST":
        # (Lógica simplificada por ahora para mantener el slice pequeño)
        pass
    aspirantes_list = listar_aspirantes()
    return render_template("aspirantes.html", aspirantes=aspirantes_list)

@bp.route("/pagos/success")
@login_required
def pago_success():
    return render_template("pagos_respuesta.html", mensaje="Pago exitoso.")

@bp.route("/pagos/failure")
@login_required
def pago_failure():
    return render_template("pagos_respuesta.html", mensaje="El pago falló.")

@bp.route("/pagos/pending")
@login_required
def pago_pending():
    return render_template("pagos_respuesta.html", mensaje="El pago está pendiente.")

@bp.route("/facturas")
@login_required
def facturas():
    """Listado de facturas con opción de pago en línea."""
    facturas_list = (
        db.session.query(Factura).order_by(Factura.fecha_emision.desc(), Factura.id.desc()).all()
    )
    return render_template("facturas.html", facturas=facturas_list)


@bp.route("/facturas/<int:id_factura>/pagar", methods=["GET", "POST"])
@login_required
def pagar_factura(id_factura: int):
    """Muestra opciones de pago o procesa el pago directo si se eligió método."""
    factura = db.session.get(Factura, id_factura)
    if not factura:
        abort(404)
    if factura.estado_pago.lower() == "aprobado":
        return render_template("pagos_respuesta.html", mensaje="Esta factura ya se encuentra abonada.")

    metodo = request.args.get("metodo")
    
    if request.method == "POST" or metodo == "mercadopago":
        if metodo == "mercadopago":
            titulo = f"Factura #{factura.id} · Galileo Galilei"
            try:
                checkout_url = crear_preferencia_pago(factura.id, float(factura.total_pagar), titulo)
                return redirect(checkout_url)
            except Exception as exc:
                return render_template("pagos_respuesta.html", mensaje=f"No se pudo iniciar el pago: {exc}"), 502
        
        if metodo == "efectivo":
            if not _csrf_valido():
                return render_template("pagos_respuesta.html", mensaje="Error de seguridad (CSRF)."), 403
            try:
                registrar_pago_manual(factura.id, "Efectivo")
                return render_template("pagos_respuesta.html", mensaje="Pago en efectivo registrado correctamente.")
            except Exception as exc:
                return render_template("pagos_respuesta.html", mensaje=f"Error al registrar pago: {exc}"), 500

    return render_template("seleccionar_pago.html", factura=factura, csrf_token=_obtener_token_csrf())


@bp.route("/pagos/webhook", methods=["POST"])
def pago_webhook():
    """Webhook para recibir notificaciones asíncronas de MercadoPago."""
    data = request.get_json(silent=True) or {}
    payment_id = None
    
    if "data" in data and "id" in data["data"]:
        payment_id = data["data"]["id"]
    elif request.args.get("type") == "payment" or request.args.get("topic") == "payment":
        payment_id = request.args.get("id") or request.args.get("data.id")

    if payment_id:
        procesado = procesar_notificacion_pago(payment_id)
        if procesado:
            return jsonify({"status": "success"}), 200

    return jsonify({"status": "ignored"}), 200


def _obtener_token_csrf() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_valido() -> bool:
    esperado = session.get("csrf_token")
    recibido = request.form.get("csrf_token", "")
    return isinstance(esperado, str) and secrets.compare_digest(esperado, recibido)


def _es_loopback() -> bool:
    direccion = request.remote_addr
    if direccion is None:
        return False
    try:
        return ipaddress.ip_address(direccion).is_loopback
    except ValueError:
        return False


def _validar_confirmacion_contrasena() -> None:
    if request.form.get("password", "") != request.form.get("confirm_password", ""):
        raise ValueError("Las contraseñas no coinciden.")


def _entero_formulario(campo: str, nombre: str) -> int:
    valor = request.form.get(campo, "").strip()
    if not re.fullmatch(r"[0-9]+", valor):
        raise ValueError(f"El campo {nombre} debe ser un entero positivo.")
    return int(valor)


def _entero_no_negativo_formulario(campo: str, nombre: str) -> int:
    valor = request.form.get(campo, "").strip()
    if not re.fullmatch(r"[0-9]+", valor):
        raise ValueError(f"El campo {nombre} debe ser un entero no negativo.")
    return int(valor)


def _id_opcional_formulario(campo: str) -> int | None:
    valor = request.form.get(campo, "").strip()
    if valor == "global":
        return None
    if not re.fullmatch(r"[0-9]+", valor):
        raise ValueError("El nivel debe ser válido.")
    return int(valor)


def _fecha_formulario(campo: str, nombre: str) -> date:
    valor = request.form.get(campo, "").strip()
    try:
        fecha = date.fromisoformat(valor)
    except ValueError as error:
        raise ValueError(f"El campo {nombre} es obligatorio y debe ser una fecha válida.") from error
    if fecha.isoformat() != valor:
        raise ValueError(f"El campo {nombre} debe tener formato AAAA-MM-DD.")
    return fecha


def _id_consulta(valor: str | None) -> int | None:
    if valor is None or not re.fullmatch(r"[0-9]+", valor):
        return None
    return int(valor)

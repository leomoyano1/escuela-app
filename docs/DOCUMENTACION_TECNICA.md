# Documentación técnica integral

## Galileo Galilei — Sistema Integrado de Gestión Escolar (SIS)

**Estado del documento:** descripción del repositorio inspeccionado el 10 de noviembre de 2026.  
**Audiencia:** desarrollo, mantenimiento y revisión técnica. No es un manual operativo.  
**Criterio:** “Implementado” significa que existe código en la versión inspeccionada; no implica que la función esté disponible en una pantalla ni que se haya validado en producción. Las reglas planificadas, instrucciones del proyecto y comportamiento observable se identifican por separado.

## 1. Resumen ejecutivo

El repositorio contiene una aplicación local de escritorio con Flask, SQLAlchemy, SQLite y PyWebView. El servidor Flask se enlaza a `127.0.0.1:5000`; PyWebView presenta la interfaz local en una ventana nativa. El esquema se gestiona mediante Flask-Migrate/Alembic. Hay autenticación local, auditoría encadenada con SHA-256, calendario, catálogos académicos, mantenimiento de alumnos/tutores, registro de intentos de calificación, asistencia con justificación y alertas, y vistas para consultar la bitácora.

El proyecto está en evolución. La aplicación tiene 24 modelos persistentes y 8 revisiones Alembic hasta `df49b2a7c103`. No existe una operación web de cierre anual ni un servicio que calcule/autorice repitencia. Los servicios incluyen registro de aspirantes y generación de facturas, pero no hay rutas ni pantallas para esos flujos. El esquema conserva módulos financieros y de aspirantes que no forman parte del recorrido web actual.

### Estado funcional observado

| Área | Estado en el código inspeccionado |
|---|---|
| Inicio local con PyWebView y Flask | Implementado en `main.py` |
| Cuentas locales, login/logout y protección CSRF | Implementado |
| Bitácora append-only y consulta paginada | Implementado |
| Años lectivos, ciclos, niveles, asignaturas y grupos | Implementado en servicios/rutas |
| Mantenimiento de alumnos y tutores | Consulta y edición web; altas y bajas no están expuestas como rutas |
| Matrículas y cambios de división | Modelo e historial; cambio de grupo existe como servicio, sin pantalla identificada en rutas |
| Calificaciones | Alta de intentos inmutables y consulta; no calcula condición académica |
| Asistencia | Registro/edición diaria, justificación, contador y notificaciones internas |
| Aspirantes CRM | Modelo y servicios de alta/listado/baja; sin ruta/pantalla web |
| Facturación | Modelos y servicio de creación; sin rutas/pantallas de facturación o registro de pagos |
| Cierre anual y repitencia | Pendiente; no debe inferirse como implementado a partir del campo `Matricula.repitente` |
| Exportación, PDF, LMS, sincronización | Dependencias o requisitos pueden mencionarlos, pero no se identificó un flujo implementado en las rutas actuales |

## 2. Arquitectura y componentes

La aplicación sigue una separación práctica por módulo, no una arquitectura de servicios distribuidos. Todos los componentes se ejecutan localmente y comparten la sesión de base de datos Flask-SQLAlchemy.

**Diagrama:** `docs/diagramas/componentes.png` (`docs/diagramas/componentes.mermaid`).  
**Marcador exacto:** `[INSERTAR DIAGRAMA: docs/diagramas/componentes.png]`

**PNG pendiente de incorporar al repositorio:** `docs/diagramas/componentes.png`.

### Responsabilidades

| Componente | Responsabilidad observada |
|---|---|
| `main.py` | Crea la aplicación, prepara almacenamiento, ejecuta migraciones seguras, inicia servidor WSGI local en un hilo y abre la ventana PyWebView. |
| `app/__init__.py` | Fábrica `create_app`, configuración Flask, SQLAlchemy, Flask-Migrate, Flask-Login, registro del blueprint y comandos CLI. |
| `app/routes.py` | Blueprint HTTP `main`, autenticación, validación de formularios, token CSRF, llamadas a servicios y renderizado de plantillas. |
| `app/services.py` | Validaciones/reglas de dominio, persistencia transaccional, auditoría desde operaciones y funciones de consulta/escritura. |
| `app/models.py` | Modelos ORM, claves foráneas, restricciones, índices y relaciones. |
| `app/audit.py` | Creación/verificación de eventos y redacción de datos sensibles para visualización. |
| `app/database.py` | Instancia SQLAlchemy, guardas de borrado/modificación, catálogo inicial, respaldo/restauración y control de migraciones. |
| `app/config.py` | Rutas y variables de configuración y preparación de directorios locales. |
| `app/templates/` | Interfaz HTML Jinja para cada pantalla. No hay carpeta `static/` en el inventario inspeccionado. |
| `migrations/` | Configuración Alembic y revisiones versionadas del esquema. |
| `tests/` | Pruebas automatizadas `unittest` para modelos, servicios, rutas, auditoría y migraciones. |

### Diagrama de clases

El diagrama contiene las 24 clases ORM declaradas en `app/models.py`; muestra relaciones y no sustituye al diccionario de datos de la sección 5.

**Diagrama:** `docs/diagramas/modelo_clases.png` (`docs/diagramas/modelo_clases.mermaid`).  
**Marcador exacto:** `[INSERTAR DIAGRAMA: docs/diagramas/modelo_clases.png]`

**PNG pendiente de incorporar al repositorio:** `docs/diagramas/modelo_clases.png`.

## 3. Estructura del repositorio

```text
.
├── main.py
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── audit.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   └── templates/
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── docs/
│   ├── database-migrations.md
│   ├── DOCUMENTACION_TECNICA.md
│   └── diagramas/
├── tasks/
│   ├── plan.md
│   ├── todo.md
│   └── doc-plan.md
├── tests/
└── .github/
    ├── agents/arquitecto-sistemas-escolares.agent.md
    └── instructions/galileo-python.instructions.md
```

Los directorios `data/uploads/`, `exports/`, `backups/` y `logs/` se crean al iniciar, aunque no estén versionados. `.gitignore` excluye `.env`, bases locales (`data/*`), respaldos, exportaciones, logs, artefactos de build y cachés. No se encontró un README en la raíz ni manifiesto de dependencias de desarrollo separado.

### Plantillas de interfaz

| Plantilla | Uso |
|---|---|
| `dashboard.html` | Panel principal y navegación. |
| `base.html` | Estructura base común. |
| `setup.html` | Alta inicial de cuenta. |
| `login.html` | Inicio de sesión. |
| `accounts.html` | Alta/listado de cuentas. |
| `auditoria.html` | Consulta de eventos con filtros, paginación y resultado de integridad. |
| `calendar.html` | Administración de año lectivo y ciclo escolar. |
| `academico.html` | Administración de niveles, asignaturas y grupos/secciones. |
| `alumnos.html` | Listado de alumnos/tutores. |
| `editar_alumno.html` | Edición de datos de alumno. |
| `editar_tutor.html` | Edición de datos de tutor. |
| `calificaciones.html` | Consulta y carga de intentos por trimestre. |
| `asistencias.html` | Consulta/carga de asistencia, justificaciones y notificaciones. |

## 4. Ejecución, configuración y dependencias

### Dependencias declaradas

Las versiones fijadas en `requirements.txt` son:

| Paquete | Versión | Uso principal |
|---|---:|---|
| Flask | 3.1.0 | Aplicación web y CLI |
| Flask-Login | 0.6.3 | Sesiones/autenticación |
| Flask-Migrate | 4.1.0 | Integración Alembic |
| Flask-SQLAlchemy | 3.1.1 | ORM e integración Flask |
| SQLAlchemy | 2.0.36 | Persistencia ORM |
| pywebview | 4.4.1 | Ventana de escritorio |
| python-dotenv | 1.0.1 | Soporte para variables desde `.env` |
| reportlab | 4.2.5 | Generación de PDF disponible como dependencia |
| pandas | 2.2.3 | Manipulación tabular disponible como dependencia |
| openpyxl | 3.1.5 | Lectura/escritura XLSX disponible como dependencia |
| pyinstaller | 6.11.1 | Empaquetado disponible como dependencia |

La presencia de una dependencia no demuestra que la función asociada esté terminada o conectada a la interfaz. El repositorio no incluye archivo de lock ni define aquí la versión exacta de Python; las instrucciones de `.github/instructions/galileo-python.instructions.md` indican Python 3.11+.

### Configuración

`app/config.py` define:

| Variable | Valor/efecto |
|---|---|
| `SECRET_KEY` | Se lee del entorno. Si falta, `create_app` genera una clave aleatoria al iniciar; por ello no se conserva la validez de sesiones al reiniciar. |
| `DATABASE_URL` | Sobrescribe SQLite local. El valor predeterminado es `sqlite:///.../data/galileo.db`. |
| `UPLOAD_FOLDER` | `data/uploads/` bajo la raíz del proyecto. |
| `EXPORT_FOLDER` | `exports/`. |
| `BACKUP_FOLDER` | `backups/`. |
| `LOG_FOLDER` | `logs/`. |
| `MIGRATIONS_DIRECTORY` | `migrations/`. |

`SQLALCHEMY_TRACK_MODIFICATIONS` está desactivado. Las cookies de sesión se configuran `HttpOnly` y `SameSite=Lax`; el código no configura explícitamente `Secure`, apropiado para el servidor HTTP loopback actual, pero debe revisarse si cambia el modo de despliegue. La aplicación genera además un hash de contraseña ficticio al crear la app para que las rutas de login hagan una comprobación de hash comparable cuando la cuenta no existe o está inactiva.

### Inicio de escritorio

El punto de entrada es `python main.py`. `launch_desktop()`:

1. Construye la app mediante `create_app()`.
2. Crea los directorios locales con `Config.prepare_storage()`.
3. Ejecuta `migrar_esquema(app)` antes de atender solicitudes.
4. Inicia Werkzeug `make_server("127.0.0.1", 5000, app)` en un hilo daemon.
5. Abre PyWebView en `http://127.0.0.1:5000`, tamaño inicial 1400×900, redimensionable y con `debug=False`.

No se debe abrir el puerto a una interfaz de red externa sin una revisión de seguridad y despliegue. La ruta `/health` devuelve `{"status": "ok", "app": "Galileo Galilei"}` y no exige login.

### Comandos de desarrollo y operación

Ejecutar desde la raíz y con las dependencias del entorno instaladas:

```powershell
python main.py
python -m unittest discover tests
python -m flask --app app:create_app db-upgrade-safe
python -m flask --app app:create_app db-backup
python -m flask --app app:create_app db-restore "C:\ruta\al\respaldo.sqlite3"
python -m flask --app app:create_app audit-verify
python -m flask --app app:create_app db migrate -m "descripcion del cambio"
```

Para crear revisiones de esquema, revisar manualmente el archivo autogenerado antes de aplicarlo. El procedimiento completo de recuperación está en [database-migrations.md](database-migrations.md).

## 5. Persistencia y diccionario de datos

La base de datos es SQLite. Los tipos listados abajo corresponden a los modelos ORM actuales; las reglas e índices se resumen aparte. Cada tabla tiene `id` entero como clave primaria, salvo que se indique. `FK` significa clave foránea; `UK` significa unicidad. Las relaciones ORM facilitan navegación y no implican cascada de borrado.

### 5.1 Entidades de personas y acceso

| Tabla / modelo | Columnas |
|---|---|
| `tutor` / `Tutor` | `id`; `nombre` texto(200), obligatorio; `dni_cuit` texto(20), obligatorio, único; `email` texto(200), opcional; `telefono` texto(50), opcional; `direccion` texto(255), opcional. |
| `usuario` / `Usuario` | `id`; `username` texto(64), obligatorio, único; `password_hash` texto(255), obligatorio; `activo` booleano obligatorio, default true; `creado_en` datetime obligatorio. Implementa `UserMixin`, `set_password()` y `check_password()`. |
| `alumno` / `Alumno` | `id`; `id_tutor` FK→`tutor`, obligatorio; `nombre` texto(120), `apellido` texto(120), `dni` texto(20), obligatorios; `dni` único; `fecha_nacimiento` fecha opcional; `legajo` texto(50) opcional y único; `fecha_baja` fecha opcional; `motivo_baja` texto opcional. |
| `aspirante_crm` / `AspiranteCRM` | `id`; `id_alumno` FK→`alumno`, opcional y único; `id_anio` FK→`anio_lectivo`, opcional; `id_nivel` FK→`nivel_grado`, opcional; nombre, apellido, DNI y fecha de nacimiento obligatorios; legajo opcional; nombre/DNI-CUIT de tutor obligatorios; teléfono/WhatsApp, email, dirección, curso de interés, estado de entrevista y observaciones opcionales; `estado` obligatorio (el servicio de alta usa `En espera`); `fecha_registro` obligatoria; `fecha_baja`/`motivo_baja` opcionales; ocho flags documentales enteros obligatorios (0/1): partida, documento, certificado de primaria, pase, libre deuda, plan de estudio, libro matriz y materias adeudadas. |

### 5.2 Calendario, niveles y matrículas

| Tabla / modelo | Columnas |
|---|---|
| `anio_lectivo` / `AnioLectivo` | `id`; `numero_ciclo` entero obligatorio y único; `fecha_inicio`, `fecha_fin` obligatorias. CHECK `fecha_fin >= fecha_inicio`. |
| `nivel_grado` / `NivelGrado` | `id`; `nombre_nivel` texto(100) obligatorio; `grado_año` texto(100) obligatorio. |
| `ciclo_escolar` / `CicloEscolar` | `id`; `id_anio` FK obligatoria; `id_nivel` FK nullable; `fecha_apertura`, `fecha_cierre` obligatorias. CHECK de orden de fechas. Un ciclo por año/nivel; índice único parcial permite como máximo un ciclo global (`id_nivel IS NULL`) por año. |
| `grupo_seccion` / `GrupoSeccion` | `id`; `id_nivel` FK obligatoria; `seccion` texto(50) nullable; `capacidad_maxima` entero obligatorio, default 30. Unicidad por nivel/sección y un índice parcial para como máximo un grupo sin sección por nivel. |
| `descuento_tipo` / `DescuentoTipo` | `id`; `codigo` texto(50) obligatorio y único; `nombre` texto(120) obligatorio; `porcentaje` float obligatorio, default 0; `descripcion` texto opcional; `activo` booleano obligatorio. |
| `matricula` / `Matricula` | `id`; `id_alumno`, `id_anio`, `id_grupo` FK obligatorias; `id_descuento` FK opcional; `fecha_inscripcion` fecha obligatoria, default fecha actual; `estado` texto(50), default `Activa`; `fecha_baja` y `motivo_baja` opcionales; `repitente` entero obligatorio, default 0, CHECK 0/1. Unicidad `(id_alumno,id_anio)`, incluso si la matrícula está dada de baja. |
| `historial_grupo_matricula` / `HistorialGrupoMatricula` | `id`; `id_matricula`, `id_grupo` FK obligatorias; `fecha_desde` obligatoria; `fecha_hasta` nullable. CHECK de rango, índice único parcial de una asignación activa por matrícula y triggers que rechazan solapamientos y borrado. |

### 5.3 Asignaturas y trayectoria académica

| Tabla / modelo | Columnas |
|---|---|
| `asignatura` / `Asignatura` | `id`; `nombre_materia` texto(150) obligatorio; `carga_horaria` entero obligatorio, default 0. |
| `condicion_materia` / `CondicionMateria` | `id`; `codigo` texto(30) obligatorio y único; `nombre` texto(80) obligatorio; `activo` booleano obligatorio. El sembrado inicial fija IDs: 1 `APROBADO`, 2 `DESAPROBADO`, 3 `LIBRE`. |
| `inscripcion_materia` / `InscripcionMateria` | `id`; `id_matricula`, `id_asignatura` FK obligatorias; `id_condicion` FK nullable; unicidad `(id_matricula,id_asignatura)`. `NULL` se usa para la cursada sin condición establecida. |
| `docente` / `Docente` | `id`; `nombre` texto(180) obligatorio; `legajo_laboral` texto(50) obligatorio y único; `especialidad` texto(150) opcional. |
| `curso_direccion` / `CursoDireccion` | `id`; `id_docente`, `id_asignatura`, `id_grupo` FK obligatorias; `horario` texto(120) opcional. Es la asignación de docente/materia/grupo referenciada por las calificaciones legacy. |
| `calificacion` / `Calificacion` | `id`; `id_matricula`, `id_curso_dir` FK obligatorias; `diagnostico`, `parcial_1`, `parcial_2`, `eval_trimestral`, `recuperatorio`, `nota_final` texto(20) nullable; `periodo_evaluacion` texto(50) obligatorio, default `1° Trimestre`. Es el formato histórico; no se convierte automáticamente a intentos. |
| `intento_calificacion` / `IntentoCalificacion` | `id`; `id_inscripcion_materia` FK obligatoria e indexada; `trimestre` entero (1–3); `tipo_evaluacion` texto (catálogo validado por CHECK); `valor` texto (1–10 o `A`); `id_condicion_rendida` FK nullable; `actor_id` FK obligatoria; `registrado_en` datetime obligatorio. Triggers impiden editar/borrar intentos. |

### 5.4 Asistencia, certificados y cargos

| Tabla / modelo | Columnas |
|---|---|
| `asistencia` / `Asistencia` | `id`; `id_matricula` FK obligatoria; `fecha` fecha obligatoria, default fecha actual; `hora_llegada` texto(10) opcional; `valor_falta` float obligatorio, default 0; `justificada` booleano obligatorio, default false; `observaciones` texto opcional; `justificada_por_id` FK opcional→`usuario`; `justificada_en` datetime opcional. Unicidad matrícula/fecha y CHECK valor 0, 0.5 o 1. |
| `notificacion_asistencia` / `NotificacionAsistencia` | `id`; `id_asistencia` FK obligatoria e indexada; `faltas_injustificadas` numérico(6,1) obligatorio; `generado_en` datetime obligatorio; `actor_id` FK obligatorio. Protegida contra borrado ORM; no equivale a condición `LIBRE`. |
| `certificado_medico` / `CertificadoMedico` | `id`; `id_matricula` FK obligatoria; `fecha_emision`, `fecha_presentacion` fechas opcionales; `diagnostico_observacion` texto opcional. No hay en el código inspeccionado cálculo de cobertura del 66% ni flujo de reincorporación. |
| `factura` / `Factura` | `id`; `id_tutor` FK obligatorio; `fecha_emision` obligatoria, default fecha actual; `fecha_vencimiento` opcional; `total_pagar` float obligatorio, default 0; `metodo_pago` texto(30), default `Efectivo`; `estado_pago` texto(30), default `Pendiente`. |
| `detalle_factura` / `DetalleFactura` | `id`; `id_factura`, `id_matricula` FK obligatorias; `concepto` texto(120) obligatorio; `monto_base`, `descuento_aplicado`, `recargo_mora`, `monto_final` float obligatorios, default 0. |

### 5.5 Auditoría

| Tabla / modelo | Columnas |
|---|---|
| `evento_auditoria` / `EventoAuditoria` | `id`; `actor_id` FK nullable→`usuario` con `SET NULL`; `ocurrido_en` texto(32); `accion` texto(80); `entidad` texto(80); `entidad_id` texto(80) nullable; `resultado` texto(20); `detalles_json` texto; `hash_anterior` texto(64) nullable; `hash_evento` texto(64), obligatorio y único. Índices por actor/fecha y entidad/ID. |

### Relaciones principales

Un tutor puede asociarse a varios alumnos y facturas. Un alumno conserva matrículas anuales; cada matrícula se asocia a un año, grupo vigente y, opcionalmente, un descuento. Los períodos de pertenencia a grupos se guardan aparte en `HistorialGrupoMatricula`. Cada matrícula puede vincularse a asignaturas por `InscripcionMateria`; el historial nuevo de evaluaciones se guarda en `IntentoCalificacion`, mientras `Calificacion` mantiene datos legacy asociados a `CursoDireccion`. La asistencia, certificados, cargos y registros académicos se asocian a matrícula. La factura pertenece a un tutor y sus detalles asocian conceptos a matrículas.

**Diagrama ERD:** `docs/diagramas/er_esquema_actual.png` (`docs/diagramas/er_esquema_actual.mermaid`).  
**Marcador exacto:** `[INSERTAR DIAGRAMA: docs/diagramas/er_esquema_actual.png]`

**PNG pendiente de incorporar al repositorio:** `docs/diagramas/er_esquema_actual.png`.

## 6. Reglas y flujos de negocio

### 6.1 Autenticación y cuentas

- La configuración inicial `/setup` solo está habilitada desde una dirección loopback y mientras no exista una cuenta.
- Las cuentas posteriores se crean en `/accounts`; todas tienen los mismos permisos, sin roles.
- El username se recorta y normaliza a minúsculas; admite 3–64 caracteres entre letras ASCII minúsculas, dígitos, punto, guion y guion bajo.
- La contraseña exige al menos 12 caracteres y se almacena mediante `werkzeug.security.generate_password_hash`; no se guarda en texto plano.
- El login hace una comprobación ficticia de hash cuando usuario no existe o está inactivo para reducir diferencias de tiempo triviales. Las respuestas de credenciales incorrectas no distinguen usuario de contraseña.
- Formularios POST protegidos por token CSRF en sesión, comparado con `secrets.compare_digest`. Logout es POST y también valida CSRF.
- Flask-Login protege las rutas de aplicación salvo `/health`, `/setup` y `/login`.

### 6.2 Auditoría

`registrar_evento_auditoria()` agrega el evento a la sesión SQLAlchemy actual. La secuencia de evento incluye actor, instante UTC, acción, entidad, identificador, resultado, detalles JSON ordenados y hash anterior. El hash actual se calcula con SHA-256 sobre esos campos canónicos y el `hash_anterior`.

**Diagrama:** `docs/diagramas/flujo_auditoria.png` (`docs/diagramas/flujo_auditoria.mermaid`).  
**Marcador exacto:** `[INSERTAR DIAGRAMA: docs/diagramas/flujo_auditoria.png]`

**PNG pendiente de incorporar al repositorio:** `docs/diagramas/flujo_auditoria.png`.

Las entidades de negocio y eventos se confirman o revierten juntas en los servicios que hacen la escritura transaccional. `app/database.py` rechaza actualizaciones y borrados ORM/SQL masivos para tablas append-only y tablas históricas protegidas. La revisión de auditoría agrega triggers SQLite para impedir `UPDATE`/`DELETE` de eventos; los intentos de calificación y el historial de grupos también tienen triggers de inmutabilidad/no borrado.

`verificar_integridad_auditoria()` recorre eventos por ID, comprueba enlace con el hash anterior y recalcula cada hash. `/auditoria` ejecuta la verificación en cada consulta, muestra el resultado y registra la propia consulta. La vista redacta claves de contraseñas/tokens y campos personales/académicos sensibles, de forma recursiva. La redacción de vista no reemplaza la minimización al generar detalles.

**Límite:** una persona con acceso directo al archivo SQLite puede modificar la base, triggers y cadena. La cadena no es un anclaje externo ni una garantía contra el administrador del equipo. No se identificó un almacenamiento remoto de auditoría.

### 6.3 Calendario escolar

`AnioLectivo` y `CicloEscolar` son entidades distintas. El año guarda `numero_ciclo` y un rango institucional; el ciclo regular tiene fecha de apertura/cierre y puede asociarse a un nivel o ser global. El servicio valida fechas, límites del ciclo dentro del año y unicidad de ciclo por nivel/año (o un ciclo global). No infiere fechas por calendario civil ni aplica solapamiento entre ciclos diferentes.

### 6.4 Grupos y recorrido de matrícula

Se permite un grupo sin sección, representado con `seccion = NULL`. La base impone unicidad por nivel/sección y como máximo un grupo sin sección por nivel. Existe una sola matrícula por alumno/año lectivo, aun si fue dada de baja. Los cambios de división mantienen esa matrícula y registran períodos separados en `HistorialGrupoMatricula`; las fechas no pueden solaparse y debe existir una sola asignación activa.

El servicio `cambiar_grupo_matricula()` valida la matrícula, grupo, nivel y continuidad temporal. No se encontró una ruta web para invocarlo. Tampoco se encontró un servicio de alta web para matrículas o asignaturas inscritas.

### 6.5 Calificaciones e inscripción por materia

Los tipos de evaluación permitidos por el servicio son:

| Código | Etiqueta |
|---|---|
| `DIAGNOSTICO` | Diagnóstico |
| `PARCIAL_1` | 1° Parcial |
| `PARCIAL_2` | 2° Parcial |
| `EVALUACION_TRIMESTRAL` | Evaluación Trimestral |
| `RECUPERATORIO` | Recuperatorio |
| `NOTA_FINAL` | Nota Final |

El trimestre debe ser 1, 2 o 3. El valor debe ser entero del 1 al 10 o `A`. Cada llamada a `registrar_intento_calificacion()` crea un registro nuevo inmutable con actor y fecha; captura `id_condicion_rendida` según la condición actual y registra evento de auditoría. El servicio **no** calcula aprobación, no valida nota mínima y no modifica `InscripcionMateria.id_condicion`. Las notas legacy de `Calificacion` se conservan; no existe conversión automática por falta de correspondencia histórica inequívoca.

**Diagrama de estados/valores:** `docs/diagramas/flujo_academico.png` (`docs/diagramas/flujo_academico.mermaid`).  
**Marcador exacto:** `[INSERTAR DIAGRAMA: docs/diagramas/flujo_academico.png]`

**PNG pendiente de incorporar al repositorio:** `docs/diagramas/flujo_academico.png`.

El diagrama representa valores disponibles en el modelo/catálogo, no transiciones ejecutables: no se encontró un flujo actual que cambie automáticamente el estado de cursando a aprobado/desaprobado/libre. Las reglas institucionales propuestas sobre cierre regular, recuperatorios, libre y repitencia deben implementarse en una tarea futura y con nota mínima/criterios confirmados.

### 6.6 Asistencia y notificaciones

- Hay como máximo un registro por matrícula/fecha.
- `valor_falta` admite 0, 0.5 o 1. El formulario pide el valor explícitamente; la aplicación no lo deduce de la hora de llegada.
- La marca de justificación se valida explícitamente. Se guarda observación; al justificar/rejustificar se almacena quién y cuándo lo hizo.
- `contar_faltas_injustificadas()` suma unidades decimales excluyendo registros justificados.
- La constante del servicio fija `UMBRAL_FALTAS_INJUSTIFICADAS = 15`. Al registrar/editar una asistencia que aumenta el aporte injustificado, si el total llega o permanece por encima de 15, puede crear una notificación ligada a esa asistencia; no se cambia automáticamente estado de matrícula ni condición de materia.
- Las consultas retornan matrículas, hasta 100 asistencias, hasta 50 notificaciones y contadores por matrícula; se auditan filtros y cantidades.
- `hora_llegada` existe en el modelo, pero el flujo de ruta/servicio observado utiliza valor de falta explícito y no aplica los cortes horarios de 07:10/07:30 descritos en instrucciones del proyecto.
- `CertificadoMedico` no se integra a un cálculo de reincorporación; la regla de cobertura del 66% permanece pendiente.

### 6.7 Aspirantes (CRM) — modelo/servicios sin interfaz

`DatosAspirante` permite crear una ficha en espera, validar datos requeridos, nacimiento no futuro, referencias opcionales de año/nivel y flags 0/1. El servicio audita creación, lista aspirantes no dados de baja por estado, lista fichas archivadas y soporta baja lógica. Sin embargo, no hay ruta `/aspirantes`, vista ni conversión de aspirante por pago; el uso no está conectado al flujo web actual. `id_alumno` es una FK opcional única, pero no se encontró código que complete automáticamente la conversión.

### 6.8 Facturación — modelo/servicio parcial sin interfaz

`crear_factura()` recibe tutor y conceptos asociados a matrículas de ese mismo tutor. Rechaza lista vacía, matrículas de otro tutor, conceptos sin descripción, montos negativos/no finitos y descuentos inactivos o fuera de 0–100. Aplica porcentaje guardado en `DescuentoTipo` a cada concepto, redondea el descuento a centavos con `ROUND_HALF_UP`, suma mora recibida en el concepto y guarda detalle/total; la escritura se audita y confirma en transacción.

**Diferencias importantes con las reglas futuras documentadas en `.github/agents/arquitecto-sistemas-escolares.agent.md` y los planes:** la implementación actual no restringe el descuento a conceptos de cuota mensual, no calcula orden de hermanos, no aplica redondeo hacia arriba al peso entero, y acepta el recargo de mora como dato recibido sin definir fórmula. Usa columnas monetarias `Float` en los modelos. No se encontró ruta web de factura ni operación de pago; `estado_pago` inicia como `Pendiente`. No presentar este servicio como ERP listo.

## 7. Superficie HTTP

Todas las rutas pertenecen al blueprint Flask `main`.

| Método | Ruta | Acceso | Función |
|---|---|---|---|
| GET | `/` | Login requerido | Registra consulta del panel y muestra dashboard. |
| GET | `/health` | Público | Indicador básico de salud. |
| GET, POST | `/setup` | Público, loopback y solo sin usuarios | Alta de la primera cuenta. |
| GET, POST | `/login` | Público | Autenticación local y eventos de éxito/fallo. |
| POST | `/logout` | Login + CSRF | Registra cierre de sesión y limpia sesión. |
| GET, POST | `/accounts` | Login + CSRF al escribir | Alta/listado de cuentas. |
| GET, POST | `/calendario` | Login + CSRF al escribir | Crear/editar año lectivo y ciclo escolar. |
| GET, POST | `/academico` | Login + CSRF al escribir | Crear/editar niveles, asignaturas, grupos/secciones. |
| GET | `/alumnos` | Login | Lista alumnos activos y tutores. |
| GET, POST | `/calificaciones` | Login + CSRF al escribir | Consultar intentos y registrar intento nuevo. |
| GET, POST | `/asistencias` | Login + CSRF al escribir | Consultar y registrar/editar asistencia. |
| GET, POST | `/alumnos/<id>/editar` | Login + CSRF al escribir | Editar datos personales de alumno. |
| GET, POST | `/tutores/<id>/editar` | Login + CSRF al escribir | Editar datos de tutor. |
| GET | `/auditoria` | Login | Filtrar y paginar bitácora (50 por página), mostrar integridad. |

No se identificaron endpoints JSON de negocio; `/health` es la única ruta que devuelve JSON. No se identificaron rutas para CRUD de matrícula, cambio de grupo, aspirantes, factura/pagos, certificados o cierre anual.

## 8. Inventario de servicios

El módulo `app/services.py` contiene las siguientes operaciones públicas de dominio:

| Grupo | Funciones |
|---|---|
| Aspirantes y cuentas | `registrar_aspirante`, `listar_aspirantes`, `listar_aspirantes_archivados`, `listar_usuarios`, `crear_usuario` |
| Catálogos académicos | `crear_nivel_grado`, `editar_nivel_grado`, `crear_asignatura`, `editar_asignatura`, `crear_grupo_seccion`, `editar_grupo_seccion`, `listar_niveles_grados`, `listar_asignaturas`, `listar_grupos_secciones` |
| Calendario | `crear_anio_lectivo`, `listar_anios_lectivos`, `editar_anio_lectivo`, `crear_ciclo_escolar`, `listar_ciclos_escolares`, `editar_ciclo_escolar` |
| Datos personales | `listar_alumnos_mantenimiento`, `listar_tutores_mantenimiento`, `obtener_alumno_mantenimiento`, `obtener_tutor_mantenimiento`, `editar_alumno_existente`, `editar_tutor_existente` |
| Historial de grupos | `cambiar_grupo_matricula`, `listar_historial_grupo_matricula` |
| Calificaciones | `registrar_intento_calificacion`, `consultar_calificaciones` |
| Asistencia | `registrar_asistencia`, `contar_faltas_injustificadas`, `consultar_asistencias` |
| Bajas lógicas | `dar_de_baja_alumno`, `dar_de_baja_matricula`, `dar_de_baja_aspirante` |
| Facturación | `crear_factura` |

Las funciones que comienzan con `_` son helpers internos de validación, serialización, auditoría, rangos de fecha y persistencia. Los servicios financieros y de aspirantes aún no están conectados a rutas web observadas.

## 9. Migraciones y ciclo de esquema

La cadena única de revisiones identificada en `migrations/versions/` es:

| Revisión | Archivo / propósito |
|---|---|
| `29e41a582da5` | `*_initial_schema.py`: esquema inicial de calendario, personas, grupos, matrículas, calificaciones legacy, asistencia, certificados, facturas, detalles y aspirantes. |
| `6fd8b6a2c41e` | `*_soft_deactivation.py`: `fecha_baja` y `motivo_baja` para alumno, matrícula y aspirante. |
| `ab41d879c562` | `*_local_accounts_and_audit.py`: usuarios, eventos de auditoría, índices y triggers append-only. |
| `4a9e3cb713d1` | `*_configurable_school_calendar.py`: validación de rangos del calendario y límite de ciclo global. |
| `7c2d4a91e6b3` | `*_grade_groups_and_history.py`: división nullable, historial de grupo y sus protecciones/índices. |
| `81b5a7d209c4` | `*_unique_annual_enrollment.py`: unicidad alumno/año y preflight de duplicados. |
| `c51d7a2e9f04` | `*_append_only_grade_attempts.py`: catálogo estable de condiciones, intentos trimestrales inmutables e índices/triggers. |
| `df49b2a7c103` | `*_attendance_justifications_alerts.py`: justificación, actor/fecha, unicidad diaria, CHECK de faltas y notificaciones. |

`migrar_esquema()` compara heads con la versión instalada. Si hay upgrade, toma un respaldo previo cuando la base SQLite persistente existe. Si la base tiene tablas pero carece de revisión Alembic, la aplicación crea respaldo y detiene el arranque en vez de asumir equivalencia. Si la revisión falla, propaga un error y no restaura automáticamente. El procedimiento recomendado es detener la app y restaurar el respaldo con la app cerrada. La política y comandos están detallados en [database-migrations.md](database-migrations.md).

La app expone los comandos `db-upgrade-safe`, `db-backup`, `db-restore` y `audit-verify`. Las revisiones que contienen datos históricos relevantes rechazan `downgrade`; la restauración de respaldo es el rollback preferido. El esquema inicial y los modelos no deben actualizarse con `create_all()` sobre una base existente.

## 10. Pruebas y verificación

La suite usa `unittest` y está en `tests/`. Archivos:

| Archivo | Alcance principal según nombres/casos de prueba |
|---|---|
| `test_academico.py` | Catálogos, grupos opcionales, historial de cambios, transacciones y guardas. |
| `test_audit_viewer.py` | Filtros, redacción, integridad, acceso de solo lectura y respaldo/restauración desde el visor/servicios. |
| `test_auth_audit.py` | Cuenta inicial, login/logout, sesión, CSRF, cuentas y eventos de autenticación. |
| `test_calendar.py` | Rangos, unicidad, ciclo global/nivel, auditoría y restricciones de calendario. |
| `test_calificaciones.py` | Valores, intentos trimestrales, inmutabilidad, actor y condición rendida. |
| `test_database_migrations.py` | Respaldo/restauración, upgrade, esquema sin versión y preflight de migración. |
| `test_existing_features.py` | Regresiones de comportamiento y protecciones de historial existentes. |
| `test_tarea7.py` | Matrícula anual, baja lógica, conservación de historia y legajo. |
| `test_tarea9_asistencias.py` | Valores de falta, justificación, contador, umbral, notificaciones y auditoría. |

La última ejecución registrada durante esta revisión fue `python -m unittest discover tests`: **70 pruebas, OK**. El comando `pytest` no estuvo disponible en el terminal inspeccionado; no es el runner que declara el proyecto. La documentación no debe interpretar el resultado como validación de PyWebView nativo ni como cobertura de flujos que todavía no existen. En particular, no hay pruebas de Tarea 10 (cierre anual/repitencia) porque esa función no está implementada.

## 11. Diferencias, límites y trabajo pendiente

Esta sección evita confundir requisitos futuros con comportamiento actual:

1. **Cierre y repitencia:** `Matricula.repitente` existe, pero no se encontró servicio, ruta, pantalla, cálculo por materias ni confirmación auditada. La Tarea 10 de `tasks/todo.md` está sin completar.
2. **Criterio de aprobación:** no hay nota mínima confirmada ni automatización de condición. El catálogo 1/2/3 no equivale a flujo de transición.
3. **Reglas de hora de asistencia:** instrucciones del proyecto citan cortes, pero la ruta pide valor explícito y no calcula desde `hora_llegada`.
4. **Reincorporación médica:** existe modelo de certificado, pero no evaluación del 66% ni flujo de reincorporación.
5. **Aspirantes:** hay modelo y servicios, no una UI, ruta de pago confirmado ni alta automática del alumno.
6. **Finanzas:** hay modelos y servicio de factura, sin rutas ni cobro. La fórmula actual no cumple todas las reglas futuras de descuento por hermanos/redondeo; la mora la entrega quien llama al servicio.
7. **Matrícula y cambio de curso:** hay modelos, historial y operación de servicio de cambio, pero no un recorrido UI identificado para alta/mantenimiento de matrículas o inscripción a materias.
8. **Auditoría local:** la cadena y triggers detectan/impiden alteraciones a través de la aplicación y SQLite normal; no protegen contra edición directa del archivo o de los triggers por un administrador del equipo.
9. **Backups:** son locales, no están cifrados ni sincronizados automáticamente. Pueden contener DNI, notas, salud y otros datos personales.
10. **Documentación previa:** `docs/diagramas/der-esquema-actual.svg` y `der-propuesta-academica.svg` ya existían. La segunda está rotulada como propuesta no implementada; no debe confundirse con el esquema actual.
11. **Pruebas de escritorio:** se documentó prueba previa del flujo en navegador local en `tasks/todo.md`; no se asume que se haya validado la interacción dentro de la ventana PyWebView nativa.

Las reglas de desarrollo, decisiones de dominio y objetivos que exceden el comportamiento actual se conservan en [instrucciones Python](../.github/instructions/galileo-python.instructions.md), [agente de arquitectura](../.github/agents/arquitecto-sistemas-escolares.agent.md), [plan del proyecto](../tasks/plan.md) y [lista de tareas](../tasks/todo.md). Si difieren del código, esta documentación indica la diferencia y el código define el comportamiento ejecutable actual.

## 12. Diagramas y exportación editable

Los cinco PNG documentados deben acompañarse de sus fuentes Mermaid homónimas. Cada marcador de inserción anterior utiliza el nombre exacto de archivo. El proyecto también conserva los dos diagramas SVG existentes; no se reemplazan ni se presentan como PNG generados.

Las fuentes `.mermaid` se renderizaron correctamente durante esta revisión, pero los PNG no pudieron incorporarse al árbol del repositorio en esta ejecución. Por eso las referencias anteriores son marcadores de entrega y no imágenes incrustadas; consultar `tasks/doc-plan.md` para completar la generación en un entorno con permisos de escritura al repositorio.

### Exportación a DOCX

Desde la raíz del repositorio, instalar la dependencia específica del exportador y ejecutar:

```powershell
python -m pip install -r tasks/requirements-docx.txt
python tasks/export_docs.py
```

El script genera `docs/Galileo_Galilei_SIS_Doc.docx`, conserva encabezados, tablas, listas, bloques de código y enlaces, y agrega un índice actualizable en Word. Acepta una ruta Markdown opcional y `-o`/`--output` para indicar otro destino. Los diagramas se incrustan cuando existen; si falta un PNG, el script conserva un marcador y muestra una advertencia. El DOCX es editable en Microsoft Word o LibreOffice.

### Índice exacto de imágenes

| Marcador en el documento | Fuente Mermaid | Propósito |
|---|---|---|
| `docs/diagramas/componentes.png` | `docs/diagramas/componentes.mermaid` | Arquitectura local y dependencias entre componentes. |
| `docs/diagramas/modelo_clases.png` | `docs/diagramas/modelo_clases.mermaid` | Clases ORM y asociaciones. |
| `docs/diagramas/er_esquema_actual.png` | `docs/diagramas/er_esquema_actual.mermaid` | Entidades, claves y relaciones del esquema actual. |
| `docs/diagramas/flujo_auditoria.png` | `docs/diagramas/flujo_auditoria.mermaid` | Registro de negocio y evento en la misma transacción. |
| `docs/diagramas/flujo_academico.png` | `docs/diagramas/flujo_academico.mermaid` | Valores de condición y aclaración de que no hay transición automática. |

---

**Fuentes primarias consultadas:** `app/models.py`, `app/routes.py`, `app/services.py`, `app/audit.py`, `app/database.py`, `app/config.py`, `app/__init__.py`, `main.py`, `requirements.txt`, `migrations/versions/`, `tests/`, `docs/database-migrations.md`, `.github/instructions/galileo-python.instructions.md`, `.github/agents/arquitecto-sistemas-escolares.agent.md`, `tasks/plan.md` y `tasks/todo.md`.

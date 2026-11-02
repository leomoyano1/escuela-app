# Migraciones y recuperación de SQLite

El esquema se versiona con Flask-Migrate/Alembic. `db.create_all()` no se usa para
actualizar bases existentes: la aplicación de escritorio ejecuta las revisiones
pendientes al iniciar, después de preparar las carpetas locales. El comando
`db-upgrade-safe` ofrece el mismo flujo para una actualización manual.

## Crear y revisar una revisión

Después de cambiar modelos, generar una revisión y revisar su contenido antes de
aplicarla:

```powershell
python -m flask --app app:create_app db migrate -m "descripción del cambio"
```

La revisión aparece en `migrations/versions/`. Revisar especialmente las
operaciones de renombrado, cambios de tipo, índices y restricciones: Alembic
autogenera una propuesta y no puede inferir de forma segura toda transformación
de datos.

## Aplicar el esquema

Para respaldar la base y aplicar revisiones pendientes desde la CLI:

```powershell
python -m flask --app app:create_app db-upgrade-safe
```

Al abrir la aplicación de escritorio, `main.py` prepara las carpetas y aplica
este mismo proceso antes de iniciar Flask/PyWebView. Los comandos normales de
Flask-Migrate también ejecutan el respaldo desde `migrations/env.py` si detectan
una revisión pendiente; para operaciones de upgrade se recomienda el comando
seguro para que el resultado o el error informe la ruta del respaldo.

No usar `stamp head` para resolver un error de upgrade. Solo se permite cuando
se verificó que el esquema existente coincide exactamente con la revisión que
se va a marcar. Si una base no tiene `alembic_version` pero ya contiene tablas
de la aplicación, `db-upgrade-safe` crea un respaldo, no modifica el esquema y
se detiene. Si no coincide con la revisión inicial, primero hay que diseñar una
migración explícita de los datos existentes.

## Respaldo y restauración

Antes de una actualización pendiente se crea una copia consistente mediante el
mecanismo de respaldo online de SQLite. Se valida con `PRAGMA integrity_check`
y se guarda en la carpeta local `backups/` con fecha/hora UTC en el nombre. Una
base nueva sin tablas no genera una copia vacía. Los respaldos pueden contener
datos personales y académicos: proteger la carpeta con los controles locales
del equipo y no compartir esos archivos.

Si una migración falla, detener la aplicación y conservar tanto la base como el
respaldo para diagnóstico. No se restaura automáticamente. Para volver a la
copia previa, cerrar todas las instancias de Galileo y ejecutar desde el mismo
entorno/configuración de base de datos:

```powershell
python -m flask --app app:create_app db-restore "C:\ruta\al\respaldo.sqlite3"
```

El comando comprueba la integridad del respaldo y reemplaza el archivo de la
base mediante un archivo temporal en el mismo directorio. La restauración
requiere que ningún otro proceso tenga abierta la base. También puede llamarse
`restaurar_respaldo_sqlite` desde código operativo con la aplicación cerrada.

La restauración del respaldo es la estrategia de rollback recomendada, porque
revierte juntos el esquema y los datos. No ejecutar `flask db downgrade base` en
una base con datos: la revisión inicial elimina todas las tablas. Cada downgrade
futuro debe revisarse por separado y probarse en una copia antes de considerarlo
una alternativa segura.

La aplicación protege las operaciones normales, pero no puede garantizar la
integridad frente a la edición directa del archivo SQLite ni frente a otro
proceso que lo reemplace.

## Bajas lógicas e historial

Alumnos, matrículas y fichas de aspirantes usan `fecha_baja` y `motivo_baja` para
archivar el registro sin eliminarlo. La baja de una matrícula no cambia
`Matricula.estado`; tampoco modifica el estado de pago de facturas. Los servicios
`dar_de_baja_alumno`, `dar_de_baja_matricula` y `dar_de_baja_aspirante` validan
un motivo y conservan los registros vinculados.

El ORM rechaza tanto el borrado individual como el borrado masivo de entidades
académicas y financieras protegidas. Las relaciones ya no usan `delete-orphan`:
desvincular una matrícula cuyo vínculo es obligatorio falla en lugar de borrar
la matrícula o su historial. Las listas de aspirantes en espera excluyen las
fichas archivadas; `listar_aspirantes_archivados` permite consultarlas.

Las bajas lógicas se registran también en la bitácora con fecha y motivo
anterior/nuevo. La aplicación todavía no tiene pantallas CRUD para estas bajas.

## Cuentas locales y auditoría

La primera cuenta se crea desde `/setup`, disponible solo desde una conexión
loopback y únicamente mientras no exista otra cuenta. Las cuentas adicionales
se crean desde `/accounts`. Todas tienen los mismos permisos; el nombre de
usuario no distingue mayúsculas y minúsculas y la contraseña requiere al menos
12 caracteres. Las contraseñas se almacenan con hash, nunca en texto claro.
Los formularios de escritura requieren token CSRF y el cierre de sesión usa
POST.

Configurar `SECRET_KEY` como variable de entorno si se necesita conservar la
validez de las sesiones entre reinicios. Si no está definida, la aplicación
genera una clave aleatoria al iniciar.

La bitácora registra los accesos exitosos/fallidos, el cierre de sesión, la
consulta del panel y de listados disponibles, la creación de cuentas,
aspirantes y facturas, y las bajas lógicas. Los eventos guardan actor cuando
está autenticado, fecha UTC, operación, entidad, resultado y detalles acotados;
los cambios de baja incluyen valores anterior/nuevo. No se guardan contraseñas
ni tokens. Cada evento se encadena con SHA-256 al anterior, y la aplicación
rechaza su actualización o borrado tanto desde el ORM como mediante triggers
SQLite.

Verificar la continuidad e integridad local de la cadena:

```powershell
python -m flask --app app:create_app audit-verify
```

La cadena ayuda a detectar modificaciones dentro de la base, pero no sustituye
un registro externo de confianza: quien pueda modificar directamente el archivo
SQLite y sus triggers puede alterar la base. Proteger el archivo y sus respaldos
con los controles locales del equipo.

El panel abre **Bitácora de auditoría** (`/auditoria`) para cualquier cuenta
autenticada. El visor solo acepta `GET` y permite filtrar por usuario, rango de
fechas UTC, entidad y acción; muestra como máximo 50 eventos por página y
registra cada consulta con filtros y cantidad de resultados, no con el
contenido de los eventos. No ofrece operaciones de alta, edición ni borrado.
La verificación de integridad se presenta en cada consulta.

Los detalles se muestran en JSON legible, pero valores asociados a claves de
credenciales/tokens y a datos personales, de contacto, salud, observaciones,
calificaciones u otros campos sensibles se reemplazan por `[REDACTADO]`. Los
eventos solo deben guardar metadatos de lectura y cambios necesarios; la
redacción del visor no sustituye esa minimización al registrar. No se registran
contraseñas ni secretos. La política puede ampliarse en `detalles_auditoria_visibles`
si aparecen nuevos nombres de campos sensibles.

### Operación y respaldo local

La ubicación predeterminada de la base es `data/galileo.db` y la carpeta de
copias es `backups/`, ambas relativas a la instalación del proyecto. Si se
configura `DATABASE_URL`, consultar esa configuración: puede cambiar ambas
ubicaciones efectivas. Los respaldos y la base contienen información sensible;
restringir el acceso al usuario local del equipo y mantener copias en un medio
local seguro.

Para crear un respaldo consistente sin aplicar migraciones, cerrar las
operaciones administrativas que estén en curso y ejecutar desde el entorno
local de Galileo:

```powershell
python -m flask --app app:create_app db-backup
```

El comando usa la API de respaldo online de SQLite, comprueba
`PRAGMA integrity_check` y muestra la ruta creada. También se genera respaldo
automático antes de migraciones pendientes. Verificar periódicamente que el
comando finalice correctamente y que las copias existan; la aplicación no
sincroniza ni cifra copias automáticamente.

Para restaurar, cerrar Galileo/PyWebView y confirmar que no haya otra instancia
usando la base. Ejecutar con la misma configuración `DATABASE_URL` que utiliza
la aplicación:

```powershell
python -m flask --app app:create_app db-restore "C:\ruta\al\respaldo.sqlite3"
```

El comando valida la copia, reemplaza la base mediante un archivo temporal y
confirma el resultado. Volver a iniciar la aplicación y ejecutar
`python -m flask --app app:create_app audit-verify`; revisar también que el
calendario y los registros esperados estén disponibles. Conservar la base
previa al incidente hasta completar la revisión. No restaurar ni copiar el
archivo mientras la aplicación esté abierta.

La auditoría y sus triggers solo protegen frente a cambios realizados por los
flujos normales de la aplicación. El acceso directo al archivo SQLite, sus
triggers, los archivos de respaldo o la computadora permite eludir esas
garantías; ni la cadena hash ni el visor constituyen evidencia externa
inalterable.

## Administración del calendario escolar

Desde el panel, **Administrar calendario** permite crear y editar años lectivos
y ciclos escolares. `numero_ciclo` conserva su significado e identificador
institucional existente. La aplicación no completa fechas por defecto: el
personal debe ingresar inicio y fin del año y apertura y cierre del ciclo
regular. Los ciclos quedan dentro del rango de su año lectivo; no se aplica una
política de solapamiento entre años ni entre ciclos.

Se admite un ciclo asociado a un nivel por año lectivo y, opcionalmente, un
ciclo global sin nivel. Como SQLite permite repetir valores `NULL` en una
restricción `UNIQUE`, un índice único parcial limita a uno los ciclos globales
por año. Antes de aplicar esa migración se comprueban años con rangos
invertidos y ciclos globales duplicados; la revisión se detiene sin corregir ni
descartar datos si detecta alguno. Los años y ciclos no tienen opción de
borrado físico en la interfaz y el ORM también rechaza ese borrado.

Crear o editar un año/ciclo y su evento de auditoría se confirman en una misma
transacción. La bitácora guarda actor y cambios anterior/nuevo; las consultas
de listados guardan solo entidad y cantidad de resultados. La administración
se encuentra disponible para cualquier usuario autenticado, sin roles.

## Niveles, asignaturas y grupos/divisiones

Desde el panel, **Administrar niveles, asignaturas y grupos** abre `/academico`.
La pantalla permite crear y editar los catálogos con sesión autenticada y token
CSRF. No ofrece borrado físico ni carga datos institucionales predeterminados.
Una sección vacía se normaliza a `NULL`: el grupo representa un grado sin
subdivisiones. Dentro de un nivel no se permiten dos grupos con la misma
sección ni más de un grupo sin sección.

La revisión `7c2d4a91e6b3` primero comprueba duplicados que entrarían en
conflicto con esas restricciones y se detiene sin descartar registros si los
encuentra. Convierte solo las secciones vacías/espacios a `NULL`, conserva los
IDs de grupos y matrículas, permite `NULL` en `grupo_seccion.seccion` y crea
`historial_grupo_matricula`. Cada matrícula existente recibe un período inicial
con su grupo actual y `fecha_inscripcion`; no se crean matrículas ni se
modifican calificaciones. El historial tiene una única asignación activa por
matrícula, valida rangos y evita solapamientos en SQLite; su borrado físico se
rechaza desde ORM y por trigger.

El servicio `cambiar_grupo_matricula` exige un usuario local activo como actor y
cambia el grupo/división de una matrícula existente sin crear otra. La fecha efectiva
debe estar dentro del año lectivo y ser posterior al inicio del período activo;
el cambio conserva el nivel/grado. El período anterior termina el día previo y
el nuevo inicia en la fecha efectiva. La referencia vigente `Matricula.id_grupo`,
el historial y el evento de auditoría con actor se confirman juntos. Las
calificaciones y `CursoDireccion` no se reescriben. Aún no existe flujo UI para
alta/cambio de matrículas; el servicio y sus pruebas están disponibles para su
integración posterior, sin agregar un formulario de inscripción.

Un grupo que ya figure en matrículas o asignaciones `CursoDireccion` no puede
cambiar de nivel o sección: debe crearse otro grupo para conservar intacta la
referencia histórica. Se permite editar su capacidad.

Los registros anteriores de `grupo_seccion` duplicados por nivel/sección
requieren revisión manual de los datos antes de actualizar. El acceso directo
al archivo SQLite puede eludir las garantías de la aplicación.

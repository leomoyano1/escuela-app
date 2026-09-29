---
applyTo: "**/*.py"
---
# Instrucciones de desarrollo para Galileo Galilei

## Objetivo
Mantener el proyecto Python consistente, legible y fácil de mantener para una aplicación de escritorio escolar con Flask, SQLAlchemy y SQLite.

## Convenciones
- Usar Python 3.11+ compatible con la versión objetivo del proyecto.
- Mantener nombres descriptivos en español cuando se trate de dominio escolar, pero usar nomenclatura Python estándar (`snake_case` para funciones, variables, módulos; `PascalCase` para clases).
- Separar claramente responsabilidades entre:
  - `models.py` para entidades y relaciones ORM
  - `routes.py` para endpoints y flujo de negocio
  - `services.py` para lógica compleja de validación y cálculo
  - `utils.py` para helpers reutilizables
  - `templates/` para HTML, y `static/` para CSS/JS/imágenes
- Usar `SQLAlchemy` declarative model con `__tablename__` explícito y claves foráneas claras.
- Priorizar validaciones de negocio en servicios o funciones de dominio antes de persistir.
- Mantener cálculos de descuento, mora y asistencia como funciones deterministas y reutilizables.

## Reglas de negocio a respetar
- El módulo de aspirantes es obligatorio. Debe permitir preparar los datos del alumno y mantenerlo en espera; solo el pago confirmado de la matrícula lo convierte en alumno activo y formaliza su matriculación. Crear una factura pendiente no cuenta como pago.
- El alta debe ser sencilla para el personal administrativo: no exigir una conversión manual separada de aspirante a alumno. La confirmación del pago debe completar el flujo de forma consistente.
- Un alumno tiene un único tutor responsable de pago y comunicación; un tutor puede estar vinculado a varios alumnos. Para el responsable se requieren nombre, DNI/CUIT, teléfono/WhatsApp y domicilio.
- Para dar de alta al alumno se requieren nombre, apellido, DNI, fecha de nacimiento y legajo escolar. El legajo puede ingresarse manualmente o generarse mediante una función, y debe ser único. La generación debe respetar legajos históricos, incluso los que todavía no estén cargados en el sistema; no asumir que el máximo actual de la base representa todos los legajos asignados por la escuela.
- La escuela asigna el grupo. El descuento, si corresponde, se selecciona durante la matriculación.
- Registrar el checklist documental como flags enteros `0`/`1`: partida de nacimiento y DNI; certificado de primaria para ingreso a primer año; para ingreso desde un año posterior o durante primer año, además, pase, libre deuda, plan de estudio, libro matriz y materias adeudadas. Son documentos archivados físicamente: el checkbox registra la verificación del administrativo, no la validación del archivo digital.
- Mientras la persona sea aspirante, conservar el checklist en el registro de aspirante; al confirmar el pago y crear al alumno, trasladar esos flags a los campos documentales del alumno.
- Las bajas son lógicas: no borrar físicamente alumnos, aspirantes matriculados ni registros con historial financiero o académico. Distinguir archivo/baja del estado de matrícula y de pago.
- La migración inicial futura debe cargar primero en un esquema de staging, validar tipos, campos obligatorios y correlación entre registros, informar errores y promover al esquema de negocio únicamente los datos aprobados.
- Distinguir `AnioLectivo` del ciclo escolar: el año lectivo normalmente abarca marzo-febrero y contiene la cursada regular más las instancias de recuperación/mesas; el ciclo escolar representa el período regular de cursada. Las fechas de apertura y cierre del ciclo escolar deben ser configurables por un empleado, no inferirse como 31 de diciembre.
- Reutilizar `AnioLectivo`, `Alumno`, `Matricula`, `Asignatura` y `Calificacion` cuando corresponda. El modelo actual todavía no tiene `InscripcionMateria`; incorporarla como vínculo de una matrícula con una asignatura para guardar la condición del alumno en esa materia, sin usar `Calificacion` como sustituto de la inscripción.
- `InscripcionMateria.id_condicion` debe referenciar un catálogo con IDs estables: `1` aprobado, `2` desaprobado y `3` libre. Usar `NULL` mientras la materia esté cursándose; inicializar explícitamente los IDs del catálogo y no depender del autoincremento.
- La condición se evalúa respecto de la nota mínima aplicable al ciclo. No fijar una nota mínima no confirmada ni mezclarla con fechas de corte. Al cierre regular, quien no aprueba queda desaprobado (2); si no aprueba al cierre de recuperación/mesas, queda libre (3).
- Un examen rendido en condición de libre debe conservar esa condición en el registro histórico del intento y mostrarse así en el boletín. Si lo aprueba, la condición vigente de `InscripcionMateria` pasa a aprobado (1), sin borrar ni sobrescribir las notas o intentos previos.
- Si el alumno no aprueba durante la cursada regular, queda desaprobado (2) y dispone de dos instancias adicionales dentro del año lectivo para aprobar. Si llega al siguiente año lectivo sin aprobar, queda libre (3) y la asignatura se considera previa.
- No crear una tabla ni un campo separado para "previas": una `InscripcionMateria` con `id_condicion = 3` (`LIBRE`) ya representa una materia previa. Las consultas del alumno deben identificar sus previas filtrando por esa condición.
- Al finalizar el año lectivo, contar asignaturas distintas en condición desaprobado (2) o libre (3). Más de dos genera una alerta y revisión administrativa de repitencia; no cambiar automáticamente ni de forma destructiva el estado de `Matricula`.
- `Matricula.repitente` es un entero obligatorio con valores únicamente `0` o `1`. La decisión administrativa debe ser manual, transaccional y auditable; volver a calcular las previas al confirmar y conservar quién decidió, cuándo y sobre qué versión de notas. Las matrículas y calificaciones de ciclos cerrados son históricas. No usar terminología de promoción universitaria.
- Los descuentos por hermanos se calculan sobre el importe original de la cuota mensual.
- La matrícula es un registro histórico asociado al año lectivo y no debe reemplazar el registro base del alumno.
- La entidad financiera es el tutor; el alumno representa la prestación académica.
- El historial de docente/curso/grupo debe preservarse mediante `CURSO_DIRECCION` y no se debe reescribir calificaciones previas por cambios de asignación.
- Los cálculos de asistencia deben respetar los umbrales: presente, media falta y falta total.

## Estilo de código
- Documentar solo cuando la lógica no sea evidente.
- Evitar comentarios redundantes y no usar logs de datos sensibles.
- Usar `Decimal` cuando sea necesario para manejar importes monetarios con precisión.
- No introducir frameworks JavaScript pesados; preferir vanilla JS y TailwindCSS.
- No ocultar errores críticos: si falla una operación persistente, responder con un mensaje claro y mantener la transacción consistente.

## Validación antes de cerrar
- Ejecutar la comprobación más específica disponible para el módulo editado.
- Revalidar sintaxis y reglas de negocio afectadas antes de dar por terminado un cambio.
- Si una regla del negocio no está especificada con claridad, dejarla explícitamente documentada como decisión pendiente antes de implementarla.

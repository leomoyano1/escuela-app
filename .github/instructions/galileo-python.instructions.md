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

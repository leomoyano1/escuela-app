---
applyTo: "**/*.py"
---
# Instrucciones de desarrollo para Galileo Galilei

## Objetivo
Mantener el proyecto Python consistente, legible y fácil de mantener para una aplicación de escritorio escolar con Flask, SQLAlchemy y SQLite.

## Alcance y decisiones confirmadas
- La primera fase prioriza gestión educativa: calendario, alumnos/tutores, matrículas, grados/divisiones, historial de divisiones, notas, asistencia, alertas y repitencia. ERP, CRM de admisión, LMS, exportaciones y soporte IT quedan para etapas posteriores.
- No cambiar ahora la regla del legajo ni diseñar/modificar el formulario de inscripción; esperar indicaciones posteriores del comprador.
- El uso es local, en una computadora. Cada persona puede tener una cuenta individual; no habrá roles y todas las cuentas tendrán los mismos permisos. El usuario autenticado se registra como actor de cada evento.
- Implementar bajas lógicas, sin borrado físico de alumnos, matrículas ni historial. Evitar `delete-orphan` y otras cascadas destructivas en esas relaciones.
- La división puede ser nula cuando un grado no se subdivide. Guardar por separado el historial de divisiones con sus períodos, sin duplicar la matrícula anual.
- La auditoría es transversal desde el primer módulo; su visor se agrega al final. Registrar una entrada por acción de lectura (ficha, listado/búsqueda, impresión/exportación, autenticación exitosa/fallida) y por cambio. Para cambios guardar usuario, fecha, objeto, campo y valores anterior/nuevo; para lecturas, usuario, acción, objetos/filtros y resultado, sin copiar el contenido completo. No guardar contraseñas ni secretos. La bitácora será de solo anexado desde la aplicación y consultable por todos; nadie podrá crear, modificar o borrar eventos desde la app. Verificar localmente la integridad y documentar que editar directamente el archivo SQLite queda fuera de la garantía de la aplicación.
- Al finalizar `AnioLectivo`, con fechas configurables según el calendario oficial e incluyendo recuperaciones/mesas, calcular la propuesta de repitencia. Un usuario logueado debe confirmarla; no modificar el estado por sí solo. Auditar quién confirmó, cuándo y sobre qué versión de notas.
- Una inasistencia justificada se conserva pero no suma al contador de faltas injustificadas. Al llegar a 15 y por cada falta injustificada adicional, notificar sin cambiar automáticamente la situación del alumno. Registrar la marca, observaciones y usuario en auditoría. No confundirla con la condición de una materia.
- Futuro ERP: facturas de pago completo, sin pagos parciales; descuento de hermanos solo en cuotas mensuales. Calcular con precisión decimal, redondear cada concepto hacia arriba al peso entero y sumar los conceptos redondeados. No inventar fórmula de mora.

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
- Las bajas son lógicas: no borrar físicamente alumnos, aspirantes matriculados ni registros con historial financiero o académico. Distinguir archivo/baja del estado de matrícula y de pago; no configurar cascadas ORM que eliminen ese historial.
- La migración inicial futura debe cargar primero en un esquema de staging, validar tipos, campos obligatorios y correlación entre registros, informar errores y promover al esquema de negocio únicamente los datos aprobados.
- Distinguir `AnioLectivo` del ciclo escolar: el año lectivo normalmente abarca marzo-febrero y contiene la cursada regular más las instancias de recuperación/mesas; el ciclo escolar representa el período regular de cursada. Las fechas de apertura y cierre del ciclo escolar deben ser configurables por un empleado, no inferirse como 31 de diciembre.
- Reutilizar `AnioLectivo`, `Alumno`, `Matricula`, `Asignatura`, `Calificacion` e `InscripcionMateria`. `InscripcionMateria` ya existe como vínculo de matrícula y asignatura con condición; no recrearla ni usar `Calificacion` como sustituto. La regla evaluativa por ciclo y el historial de intentos siguen pendientes.
- `InscripcionMateria.id_condicion` debe referenciar un catálogo con IDs estables: `1` aprobado, `2` desaprobado y `3` libre. Usar `NULL` mientras la materia esté cursándose; inicializar explícitamente los IDs del catálogo y no depender del autoincremento.
- La condición se evalúa respecto de la nota mínima aplicable al ciclo. No fijar una nota mínima no confirmada ni mezclarla con fechas de corte. Al cierre regular, quien no aprueba queda desaprobado (2); si no aprueba al cierre de recuperación/mesas, queda libre (3).
- Un examen rendido en condición de libre debe conservar esa condición en el registro histórico del intento y mostrarse así en el boletín. Si lo aprueba, la condición vigente de `InscripcionMateria` pasa a aprobado (1), sin borrar ni sobrescribir las notas o intentos previos.
- Si el alumno no aprueba durante la cursada regular, queda desaprobado (2) y dispone de dos instancias adicionales dentro del año lectivo para aprobar. Si llega al siguiente año lectivo sin aprobar, queda libre (3) y la asignatura se considera previa.
- No crear una tabla ni un campo separado para "previas": una `InscripcionMateria` con `id_condicion = 3` (`LIBRE`) ya representa una materia previa. Las consultas del alumno deben identificar sus previas filtrando por esa condición.
- Al cierre configurable del año lectivo, después de recuperaciones/mesas, contar asignaturas distintas desaprobadas (2) o libres (3). Más de dos genera una propuesta de repitencia que requiere confirmación explícita de un usuario autenticado; no cambiar automáticamente el estado de `Matricula`.
- `Matricula.repitente` es un entero obligatorio con valores únicamente `0` o `1`. Guardar la decisión de forma transaccional y auditable: usuario, fecha y versión de notas. Las notas cerradas no se editan por el flujo normal; correcciones posteriores requieren una operación de soporte auditada, planificada para una fase posterior. No usar terminología de promoción universitaria.
- Los descuentos por hermanos se calculan sobre el importe original de la cuota mensual.
- La matrícula es un registro histórico asociado al año lectivo y no debe reemplazar el registro base del alumno.
- La entidad financiera es el tutor; el alumno representa la prestación académica.
- El historial de docente/curso/grupo debe preservarse mediante `CURSO_DIRECCION` y no se debe reescribir calificaciones previas por cambios de asignación.
- Los cálculos de asistencia deben respetar los umbrales: presente, media falta y falta total. Solo faltas injustificadas suman para el umbral de 15; notificar al alcanzar 15 y por cada falta injustificada adicional. La justificación y observación se auditan y no producen un cambio automático de situación académica.

## Estilo de código
- Documentar solo cuando la lógica no sea evidente.
- Evitar comentarios redundantes y datos sensibles en logs técnicos ordinarios. La bitácora de auditoría es un almacén separado y registra los valores anterior/nuevo de campos modificados según las decisiones confirmadas; nunca registrar contraseñas ni secretos.
- Usar `Decimal` cuando sea necesario para manejar importes monetarios con precisión.
- No introducir frameworks JavaScript pesados; preferir vanilla JS y TailwindCSS.
- No ocultar errores críticos: si falla una operación persistente, responder con un mensaje claro y mantener la transacción consistente.

## Validación antes de cerrar
- Ejecutar la comprobación más específica disponible para el módulo editado.
- Revalidar sintaxis y reglas de negocio afectadas antes de dar por terminado un cambio.
- Si una regla del negocio no está especificada con claridad, dejarla explícitamente documentada como decisión pendiente antes de implementarla.

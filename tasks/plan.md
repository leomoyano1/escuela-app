# Plan de implementación: gestión educativa Galileo Galilei

## Estado y alcance
Plan propuesto a partir de las decisiones confirmadas con el comprador. La primera entrega cubre el SIS local: calendario escolar, alumnos/tutores, matrículas, grados/divisiones, historial de divisiones, notas, asistencia, alertas y repitencia. No incluye ahora el formulario/flujo de aspirantes ni cambios al legajo. ERP/facturación, LMS, exportaciones y herramientas de soporte quedan para etapas posteriores.

## Situación de partida
- Aplicación local Flask + SQLAlchemy + SQLite con lanzamiento mediante PyWebView.
- Hay modelos académicos y financieros parciales, pero la única ruta publicada es `/`.
- El esquema está versionado con Flask-Migrate/Alembic; el arranque de escritorio aplica migraciones pendientes con respaldo previo. La revisión inicial crea el esquema y siembra las condiciones académicas estables.
- Las pruebas actuales usan `unittest` y cubren modelos/servicios básicos.
- `InscripcionMateria` y `CondicionMateria` ya existen; la regla de evaluación por ciclo y el historial de intentos todavía no están modelados.
- Hay relaciones ORM con `delete-orphan` que contradicen la conservación del historial. Deben corregirse antes de usar datos reales.

## Decisiones de arquitectura
- Toda la información y operación permanecen locales; no se incorporan servicios en la nube.
- Cuentas individuales con contraseñas seguras y sin roles. Todas las cuentas tienen los mismos permisos; el usuario autenticado se asocia a cada evento.
- Bajas lógicas con `fecha_baja`/`motivo_baja`, independientes del estado de matrícula o pago. La aplicación no borra físicamente alumnos, aspirantes matriculados ni historial financiero/académico; el ORM rechaza borrados individuales/masivos y las relaciones no cascaden eliminaciones.
- Grado/división: una división puede ser nula si el curso no se subdivide. Se conserva una sola matrícula por alumno/año lectivo; los cambios de división se registran aparte, con período de vigencia.
- Auditoría desde el primer módulo, con visor para una fase posterior. Un evento por acción de lectura o cambio; los cambios conservan campo y valores anterior/nuevo. Lecturas conservan actor, acción, filtros/objetos consultados y resultado, sin copiar todo el contenido. No registrar contraseñas ni secretos.
- La bitácora es de solo anexado y nadie puede editarla o borrarla desde la aplicación. Implementar una comprobación local de integridad y documentar el límite: el acceso directo al archivo SQLite queda fuera de las garantías de la aplicación.
- Inasistencia justificada: se conserva en el historial, con observaciones y usuario; no suma al contador de faltas injustificadas. Notificar al llegar a 15 y por cada falta injustificada adicional; no cambiar automáticamente la situación académica.
- Cierre de repitencia: fecha de fin de `AnioLectivo` configurable por calendario institucional/ministerial. Luego de recuperaciones/mesas, recalcular materias distintas en condición desaprobado/libre. Más de dos genera propuesta y requiere confirmación explícita de un usuario logueado; no cambia automáticamente notas ni matrícula. Guardar actor, fecha y versión de notas.
- Diseño financiero futuro: solo pago completo; descuento de hermanos exclusivamente en cuotas mensuales, calculado sobre la base original; calcular cada concepto con decimal, redondear hacia arriba al peso entero y sumar conceptos ya redondeados. No inventar fórmula de mora.

## Fases y dependencias

### Fase 0: proteger datos y permitir evolución del esquema
1. Registrar una línea base de tests y respaldar la base local antes de cambiar el esquema.
2. Incorporar migraciones versionadas y usar `create_all()` solo en fixtures de prueba, nunca para actualizar bases existentes.
3. Probar restauración y definir reversión de migraciones mediante recuperación desde respaldo. Una base con tablas pero sin versión se respalda y bloquea hasta verificar su compatibilidad.

### Fase 1: cuentas locales y auditoría transversal
1. Implementar cuentas locales, almacenamiento seguro de contraseñas, sesión/login/logout y alta inicial de la primera cuenta. Sin roles.
2. Incorporar el registro de auditoría append-only, actor autenticado, acción, fecha, objeto, antes/después y metadatos de lectura; excluir secretos.
3. Validar integridad local de la bitácora y fallos de autenticación; asegurar que la aplicación no exponga operaciones para modificar/borrar eventos.
4. Emitir eventos desde servicios/rutas en la misma transacción de cada cambio, evitando que un cambio de negocio quede sin evento.

### Fase 2: estructura y calendario académico
1. Administrar años lectivos y ciclos escolares con fechas configurables; mantenerlos como conceptos distintos.
2. Administrar niveles/grados, grupos/divisiones opcionales y asignaturas.
3. Añadir restricciones e índices para unicidad y relaciones; conservar `seccion = NULL` cuando el grado no se divide.

### Fase 3: alumnos, tutores, matrículas y recorrido por divisiones
1. Añadir mantenimiento administrativo básico de alumnos/tutores existentes, sin diseñar el formulario de admisión pospuesto.
2. Mantener una matrícula por alumno y año lectivo; proteger su unicidad y conservar historia por año.
3. Registrar traslados entre divisiones con fecha de inicio/fin, sin duplicar la matrícula anual ni alterar períodos cerrados.
4. Eliminar cascadas destructivas y cubrir bajas lógicas con pruebas de conservación de matrículas, notas, asistencia, certificados y auditoría.
5. No cambiar la regla del legajo acordada ni automatizar su generación en esta fase.

### Fase 4: calificaciones y condición por materia
1. Implementar carga y consulta de notas trimestrales, incluyendo enteros 1–10 y `A` (Ausente).
2. Completar el vínculo entre matrícula y materia con condiciones estables `1=Aprobado`, `2=Desaprobado`, `3=Libre`, manteniendo `NULL` mientras cursa.
3. Registrar intentos de evaluación sin sobrescribir resultados; soportar examen rendido libre y actualización de condición vigente.
4. Bloquear la regla automática de aprobación hasta que la institución confirme nota mínima y criterios por ciclo; no inventar valores.

### Fase 5: asistencia e inasistencias justificadas
1. Registrar presente/media falta/falta total conforme a horarios existentes.
2. Añadir marca booleana de justificación y observaciones; registrar qué usuario la marcó y auditar el cambio.
3. Calcular el umbral sobre faltas injustificadas; notificar en 15 y en cada valor posterior, sin alterar matrícula ni condición de materia.
4. Resolver antes de implementar reincorporaciones el denominador del 66% de certificados médicos y su relación con las inasistencias justificadas.

### Fase 6: cierre del año lectivo y repitencia
1. Al cierre configurable del año lectivo, incluir notas de recuperaciones/mesas y contar asignaturas distintas desaprobadas/libres.
2. Presentar una propuesta de repitencia cuando corresponda; exigir confirmación explícita de un usuario logueado.
3. Registrar la decisión, usuario, fecha y versión de notas en la auditoría; no cambiar notas ni matrícula automáticamente.
4. La corrección/reapertura posterior por soporte IT queda fuera de esta fase y deberá tener su propio flujo auditado.

### Fase 7: visor y verificación integral
1. Construir el visor de auditoría con búsqueda por usuario, fecha, entidad y tipo de acción; lectura solamente.
2. Verificar los flujos principales end-to-end, restauración de respaldo, auditoría de lecturas/cambios y operación local en PyWebView.
3. Documentar límites de seguridad del archivo SQLite y los procedimientos locales de respaldo/restauración.

## Bloqueos y riesgos
| Tema | Riesgo/impacto | Tratamiento |
|---|---|---|
| Cascadas ORM actuales | Pérdida irreversible de historial | Resolver en Fase 0/3 y probar eliminación lógica antes de usar datos reales |
| No hay migraciones versionadas | `create_all()` no modifica tablas existentes de forma segura | Elegir herramienta, respaldar y probar migración/restauración antes de expandir modelos |
| Nota mínima y criterios | Clasificación académica errónea | Mantener decisión abierta; no programar aprobación automática hasta confirmación institucional |
| Auditoría local | Un acceso directo al archivo SQLite puede alterar datos fuera de la aplicación | Bitácora append-only en app, mecanismo verificable y límites explícitos; validar estrategia local de integridad |
| Auditoría de datos sensibles | El antes/después puede duplicar PII | Guardar solo campos modificados, nunca secretos; diseñar almacenamiento local protegido y vistas sin contenido innecesario |
| Reincorporación médica | No está definido el denominador del 66% | Resolver antes del flujo de reincorporación |

## Fuera de alcance de la primera fase
- Cambios al legajo y formulario de inscripción/CRM de aspirantes.
- ERP, facturas, mora, pagos y recibos; sus reglas confirmadas quedan reservadas para esa etapa.
- LMS, exportaciones ministeriales, migración de datos de terceros y utilidades de soporte IT.
- Roles/permisos diferenciados.

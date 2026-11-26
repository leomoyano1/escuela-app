# Tareas: gestión educativa SIS

## Fase 0: datos y esquema

### Tarea 1: fijar línea base y estrategia de migración
- [x] Registrar estado inicial de tests y modelos; suite existente ampliada con regresión de configuración (11/11 pruebas pasaban al fijar la línea base).
- [x] Elegir Flask-Migrate/Alembic, compatible con Flask-SQLAlchemy/SQLite.
- [x] Añadir respaldo SQLite consistente previo a migraciones y probar restauración en una base temporal.
- [x] Definir rollback por restauración del respaldo; bloquear bases sin versión hasta verificar su esquema.
- [x] Verificación: 16 pruebas pasan; migración CLI temporal y `db check` confirman esquema alineado; restauración conserva datos y reemplaza el destino solo tras validar integridad.
- Dependencias: ninguna.

### Tarea 2: eliminar borrado físico accidental
- [x] Reemplazar `delete-orphan` destructivo para alumnos, matrículas y relaciones históricas.
- [x] Definir `fecha_baja`/`motivo_baja` en alumnos, matrículas y aspirantes, sin reutilizar el estado de matrícula o pago.
- [x] Añadir tests de baja lógica y conservación de notas, asistencia, certificados, matrículas, facturas y detalles.
- [x] Verificación: el ORM rechaza borrados individuales/masivos; la baja conserva el historial. La auditoría de actor queda para la Tarea 4.
- Dependencias: Tarea 1.

## Fase 1: identidad y auditoría transversal

### Tarea 3: cuentas locales sin roles
- [x] Crear cuenta inicial segura y cuentas individuales adicionales.
- [x] Guardar contraseñas con hash seguro; implementar login/logout local.
- [x] Mantener permisos iguales para todas las cuentas y asociar actor autenticado a cada operación disponible.
- Verificación: login válido/inválido, sesión, cierre de sesión y almacenamiento sin contraseña en claro.
- Dependencias: Tarea 1.

### Tarea 4: bitácora append-only e integridad
- [x] Crear evento de auditoría para las lecturas y cambios disponibles, bajas lógicas e intentos de autenticación.
- [x] Guardar actor, fecha, operación, entidad/registro, resultado y valores anterior/nuevo en las bajas.
- [x] Para lecturas guardar acción, entidad/filtros y resultado sin duplicar todo el contenido.
- [x] Excluir contraseñas, tokens y secretos; no exponer operaciones de edición/borrado de auditoría.
- [x] Implementar y probar verificación local de integridad; documentar límite de edición directa de SQLite.
- Verificación: tests de lectura/escritura, orden y actor; cambios de negocio y eventos se confirman/revierten juntos.
- Dependencias: Tarea 1; actor autenticado de Tarea 3 para eventos asociados a usuario.

## Fase 2: calendario y estructura académica

### Tarea 5: años lectivos y ciclos configurables
- [x] Administrar `AnioLectivo` y `CicloEscolar` como conceptos distintos.
- [x] Permitir configurar fechas de inicio/fin según calendario institucional; no asumir febrero ni 31 de diciembre.
- [x] Mantener restricciones de rango y unicidad por nivel/año donde corresponda.
- Verificación: 6 pruebas de calendario y 33 pruebas totales; migraciones SQLite aplicadas en una base temporal, `db check` sin diferencias y cambios auditados con actor.
- Dependencias: Tareas 1 y 4.

### Tarea 6: niveles, grupos y división opcional
- [x] Administrar niveles/grados, asignaturas y grupos.
- [x] Permitir división nula si el grado no se separa.
- [x] Registrar cambios de división por período sin crear matrículas anuales duplicadas.
- Verificación: 11 pruebas académicas específicas y 44 pruebas totales; migración y backfill validados, esquema SQLite sin diferencias y auditoría verificada.
- Dependencias: Tareas 1, 4 y 5.

## Fase 3: registros académicos

### Tarea 7: alumnos, tutores y matrícula anual
- [x] Implementar mantenimiento administrativo básico de alumnos/tutores ya existentes; no construir el formulario CRM de inscripción.
- [x] Garantizar una matrícula por alumno/año lectivo y preservar matrículas históricas.
- [x] Registrar el historial de división separado de la matrícula anual.
- [x] Mantener la regla actual del legajo sin automatizarla ni alterarla.
- Verificación: constraint SQLite de unicidad (incluidas matrículas dadas de baja), preservación de matrícula/historial/legajo y auditoría de cambios probadas; 5 pruebas de Tarea 7 y suite global de 49 pruebas pasan.
- Dependencias: Tareas 2, 5 y 6.

### Tarea 8: notas e inscripción por materia
- [x] Implementar carga/consulta trimestral de notas enteras 1–10 o `A`.
- [x] Usar `InscripcionMateria` existente con catálogo estable de condiciones 1/2/3 y unicidad matrícula/asignatura.
- [x] Registrar intentos de evaluación sin sobrescribir los previos; conservar la condición rendida, incluso `LIBRE`.
- [x] No fijar nota mínima ni aprobar automáticamente; las notas no cambian la condición vigente.
- Verificación: 9 pruebas focalizadas y 58 pruebas totales pasan; migración temporal conserva filas de `Calificacion`, el preflight rechaza inscripciones duplicadas, los intentos no se pueden editar/borrar, `flask db check` temporal no detecta diferencias y `git diff --check` pasa.
- Pendiente institucional: no hay nota mínima confirmada; por eso no se calcula ni cambia la condición académica. Las filas históricas de `Calificacion` se conservan sin conversión automática porque la correspondencia inequívoca a intentos trimestrales no está definida.
- Dependencias: Tareas 4, 5 y 7; definición institucional de nota mínima bloquea aprobación automática.

### Tarea 9: asistencia y justificaciones
- [x] Registrar asistencia por matrícula/fecha con selección explícita de 0/0.5/1; no deducir el valor por hora.
- [x] Añadir `justificada` y observaciones; conservar quién/cuándo validó la justificación y auditar cada cambio.
- [x] Excluir justificadas del contador de faltas injustificadas.
- [x] Generar aviso interno y evento auditado al alcanzar 15 y por cada falta injustificada adicional; no cambiar matrícula/condición.
- Verificación: 7 pruebas focalizadas cubren los tres valores, justificación/reversión, contador, avisos al llegar a 15 y en 16/17, lectura/auditoría, sesión/CSRF y preservación de asistencia legacy; suite global 65/65. `flask db upgrade` y `flask db check` en SQLite temporal, sin diferencias; `git diff --check` pasa.
- Pendiente institucional: los cortes horarios no fueron definidos; por eso el registro permite selección explícita, conserva el dato horario legado y no infiere asistencia por hora. La regla del 66% de certificados para reincorporación queda sin implementar hasta definir el denominador (todas las faltas o solo injustificadas); la reincorporación no forma parte de esta tarea.
- Dependencias: Tareas 4 y 7.

### Tarea 10: cierre anual y autorización de repitencia
- [ ] Al cerrar `AnioLectivo` en la fecha configurada, recalcular condiciones considerando recuperaciones/mesas.
- [ ] Contar materias distintas en condición desaprobado/libre; generar propuesta si son más de dos.
- [ ] Requerir confirmación explícita de cualquier usuario autenticado; no cambiar `Matricula.repitente` por cálculo automático.
- [ ] Auditar usuario, fecha, conteo y versión de notas usada para la confirmación.
- Verificación: casos con 2/3 materias, datos de cada instancia, confirmación/cancelación y repetición del cálculo sin sobrescritura.
- Dependencias: Tareas 4, 5, 7 y 8; confirmar criterios institucionales pendientes.

## Fase 4: visor y cierre

### Tarea 11: visor de auditoría y revisión integral
- [x] Crear visor de solo lectura con filtros por usuario, fecha, entidad y acción.
- [x] Mostrar detalles anteriores/nuevos según política de datos sensibles, sin credenciales.
- [ ] Verificar integridad de la bitácora, respaldo/restauración y flujos completos en PyWebView local.
- [x] Documentar límites de acceso al archivo SQLite y guía de operación/restauración local.
- Verificación global: suite completa 70/70 y `git diff --check`; tests del visor cubren sesión, filtros, redacción, auditoría de lectura, integridad, ausencia de mutaciones y creación/restauración de respaldos. Se inició `main.py` con almacenamiento temporal y se probó el flujo de cuenta inicial → panel → bitácora mediante el navegador local; queda pendiente confirmar la interacción dentro de la ventana nativa PyWebView.
- Dependencias: Tareas 3–9; Tarea 10 no bloquea esta superficie independiente.

## Fase 5: Evolución (CRM, Facturación y Reportes)

### Tarea 12: CRM de Aspirantes (Backend)
**Descripción:** Implementar la lógica y rutas para el manejo de aspirantes, utilizando el modelo existente `AspiranteCRM`.
**Criterios de aceptación:**
- [ ] CRUD funcional para aspirantes.
- [ ] Validación de checklist documental.
- [ ] Auditoría de cambios de estado.
**Dependencias:** Tarea 7 (Matrícula).
**Files:** `app/services.py`, `app/routes.py`.
**Sizing:** Medium.

### Tarea 13: Facturación y Pagos (Backend)
**Descripción:** Implementar servicios financieros para la gestión de cuotas y pagos.
**Criterios de aceptación:**
- [ ] Generación automática de cuotas.
- [ ] Registro de pagos.
- [ ] Auditoría financiera.
**Dependencias:** Tarea 12.
**Files:** `app/services.py`, `app/routes.py`.
**Sizing:** Medium.

### Tarea 14: Motor de Reportes PDF
**Descripción:** Implementar motor de reportes usando `reportlab` para boletines y constancias.
**Criterios de aceptación:**
- [ ] Generación PDF de boletín.
- [ ] Generación PDF de constancia.
**Dependencias:** Tarea 8.
**Files:** `app/services.py`.
**Sizing:** Small.

## Fase 6: Interfaz de Usuario (UI)

### Tarea 15: UI para CRM, Facturación y Reportes
**Descripción:** Implementar las vistas (templates) correspondientes para los nuevos módulos.
**Criterios de aceptación:**
- [ ] UI funcional para CRM de Aspirantes.
- [ ] UI funcional para Facturación.
- [ ] UI para descarga de reportes.
**Dependencias:** Tarea 12, 13, 14.
**Files:** `app/templates/*.html`.
**Sizing:** Large.

## Checkpoints
- [x] **Cimientos:** migración/backup probados, bajas lógicas no destruyen historial, cuentas locales y auditoría funcionan.
- [x] **SIS operativo:** año/ciclo, matrícula y división histórica integrados con notas y asistencia.
- [ ] **Cierre académico:** repitencia solo se registra con autorización y queda auditada.
- [ ] **Entrega:** visor en solo lectura, tests y restauración local verificados.

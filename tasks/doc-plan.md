# Estado: Documentación técnica SIS

## Objetivo
Mantener un dossier técnico verificable de Galileo Galilei SIS, sus diagramas y una ruta de exportación editable a DOCX. La documentación debe distinguir el comportamiento implementado de las reglas propuestas o pendientes.

## Estado de entrega

- **Documentación Markdown:** redactada en `docs/DOCUMENTACION_TECNICA.md`; incluye inventario, modelo de datos, rutas, servicios, reglas observadas, migraciones, pruebas, limitaciones y nombres exactos de los diagramas.
- **Fuentes Mermaid:** los cinco archivos `.mermaid` están en `docs/diagramas/`.
- **PNG:** los cinco diagramas están disponibles en `docs/diagramas/png/`. Sus marcadores del documento conservan las rutas `docs/diagramas/<nombre>.png`; el exportador también busca los archivos en la subcarpeta `png/`.
- **DOCX:** exportador Python disponible en `tasks/export_docs.py`; los PNG de los cinco diagramas siguen pendientes de incorporar.
- **Dependencia del exportador:** `python-docx`, declarada por separado en `tasks/requirements-docx.txt` para no agregarla a las dependencias de la aplicación.

## Tareas

- [x] Redactar la documentación técnica.
  - Aceptación: describir solo hechos respaldados por código, migraciones, pruebas y documentación del proyecto; señalar explícitamente lo que no está implementado.
  - Verificación: revisión del contenido y de los marcadores con nombres exactos.
  - Archivos: `docs/DOCUMENTACION_TECNICA.md`.
- [ ] Incorporar los cinco PNG al repositorio.
  - Aceptación: `componentes.png`, `modelo_clases.png`, `er_esquema_actual.png`, `flujo_auditoria.png` y `flujo_academico.png` existen en `docs/diagramas/`, se abren como PNG y corresponden a sus fuentes Mermaid homónimas.
  - Verificación sugerida desde la raíz en PowerShell:
    ```powershell
    $nombres = @('componentes', 'modelo_clases', 'er_esquema_actual', 'flujo_auditoria', 'flujo_academico')
    foreach ($nombre in $nombres) {
      npx.cmd --yes @mermaid-js/mermaid-cli -i "docs\diagramas\$nombre.mermaid" -o "docs\diagramas\$nombre.png"
      if ($LASTEXITCODE -ne 0) { throw "Falló el renderizado de $nombre" }
    }
    ```
- [ ] Generar y revisar el DOCX editable.
  - Aceptación: `docs/Galileo_Galilei_SIS_Doc.docx` abre en Word/LibreOffice, incluye los diagramas disponibles y conserva encabezados, tablas y enlaces.
  - Verificación: instalar `tasks/requirements-docx.txt`, ejecutar `python tasks/export_docs.py` y revisar el documento resultante. El script informa qué imágenes no pudo encontrar.

## Bloqueos actuales

No hay un bloqueo conocido para exportar el DOCX: verificar la salida en Word/LibreOffice y confirmar que los cinco PNG quedaron incrustados.

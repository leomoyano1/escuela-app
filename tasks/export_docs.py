#!/usr/bin/env python
"""Export the technical Markdown document to an editable Word document."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from docx import Document
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError as exc:
    raise SystemExit(
        "Falta python-docx. Instálalo con: "
        "python -m pip install -r tasks/requirements-docx.txt"
    ) from exc


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "docs" / "DOCUMENTACION_TECNICA.md"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "Galileo_Galilei_SIS_Doc.docx"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([^\s`]*)?.*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
DIAGRAM_RE = re.compile(r"\[INSERTAR DIAGRAMA:\s*([^\]]+)\]")
INLINE_RE = re.compile(
    r"(`[^`]+`|\*\*.+?\*\*|__.+?__|~~.+?~~|"
    r"(?<!\w)\*[^*]+\*(?!\w)|(?<!\w)_[^_]+_(?!\w)|"
    r"\[[^\]]+\]\([^)]+\)|\[INSERTAR DIAGRAMA:\s*[^\]]+\])"
)


def _set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _set_repeat_table_header(row) -> None:
    properties = row._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    properties.append(repeat)


def _add_field(paragraph, instruction: str, display_text: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction_node = OxmlElement("w:instrText")
    instruction_node.set(qn("xml:space"), "preserve")
    instruction_node.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    result = OxmlElement("w:t")
    result.text = display_text
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend((begin, instruction_node, separate, result, end))


def _add_hyperlink(paragraph, label: str, target: str) -> None:
    relationship_id = paragraph.part.relate_to(
        target,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.extend((color, underline))
    run.append(properties)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _resolve_image(source: Path, image_reference: str) -> Path | None:
    parsed = urlsplit(image_reference.strip())
    if parsed.scheme or not parsed.path:
        return None

    relative_path = Path(unquote(parsed.path.replace("\\", "/")))
    candidates = [source.parent / relative_path, REPOSITORY_ROOT / relative_path]
    if relative_path.parts[:2] == ("docs", "diagramas") and len(relative_path.parts) == 3:
        candidates.append(
            REPOSITORY_ROOT / "docs" / "diagramas" / "png" / relative_path.name
        )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def _add_image(paragraph, source: Path, reference: str, missing_images: set[str]) -> bool:
    image_path = _resolve_image(source, reference)
    if image_path is None:
        missing_images.add(reference)
        paragraph.add_run(f"[Imagen pendiente: {reference}]")
        return False

    paragraph.add_run().add_picture(str(image_path), width=Inches(6))
    return True


def _add_inline_text(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    monospace: bool = False,
    strike: bool = False,
) -> None:
    run = paragraph.add_run(html.unescape(text))
    run.bold = bold or None
    run.italic = italic or None
    run.font.strike = strike or None
    if monospace:
        run.font.name = "Consolas"
        run.font.size = Pt(9)


def _add_inline(paragraph, text: str, source: Path, missing_images: set[str]) -> None:
    cursor = 0
    for match in INLINE_RE.finditer(text):
        _add_inline_text(paragraph, text[cursor : match.start()])
        token = match.group()

        if token.startswith("**") or token.startswith("__"):
            _add_inline_text(paragraph, token[2:-2], bold=True)
        elif token.startswith("~~"):
            _add_inline_text(paragraph, token[2:-2], strike=True)
        elif token.startswith("`"):
            code_text = token[1:-1]
            diagram_match = DIAGRAM_RE.fullmatch(code_text)
            if diagram_match:
                _add_image(
                    paragraph,
                    source,
                    diagram_match.group(1).strip(),
                    missing_images,
                )
            else:
                _add_inline_text(paragraph, code_text, monospace=True)
        elif token.startswith("*") or token.startswith("_"):
            _add_inline_text(paragraph, token[1:-1], italic=True)
        elif token.startswith("[INSERTAR DIAGRAMA:"):
            image_reference = DIAGRAM_RE.fullmatch(token).group(1).strip()
            _add_image(paragraph, source, image_reference, missing_images)
        else:
            link_match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", token)
            if link_match:
                _add_hyperlink(paragraph, link_match.group(1), link_match.group(2))
            else:
                _add_inline_text(paragraph, token)
        cursor = match.end()

    _add_inline_text(paragraph, text[cursor:])


def _split_table_row(line: str) -> list[str]:
    content = line.strip()
    if content.startswith("|"):
        content = content[1:]
    if content.endswith("|"):
        content = content[:-1]
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", content)]


def _add_table(document, rows: list[list[str]], source: Path, missing_images: set[str]) -> None:
    if not rows:
        return
    column_count = max(map(len, rows))
    table = document.add_table(rows=0, cols=column_count)
    table.style = "Table Grid"
    table.autofit = True

    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for column_index, cell in enumerate(cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text = ""
            if column_index < len(values):
                _add_inline(cell.paragraphs[0], values[column_index], source, missing_images)
            if row_index == 0:
                _set_cell_shading(cell, "D9EAF7")
                for run in cell.paragraphs[0].runs:
                    run.bold = True

    if table.rows:
        _set_repeat_table_header(table.rows[0])


def _add_code_block(document, code: list[str], language: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.2)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(7)
    paragraph.paragraph_format.keep_together = True
    if language:
        label = paragraph.add_run(f"{language}\n")
        label.bold = True
        label.font.size = Pt(8)
        label.font.color.rgb = RGBColor(89, 89, 89)
    run = paragraph.add_run("\n".join(code))
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)


def _add_toc(document) -> None:
    document.add_paragraph("Contenido", style="Title")
    _add_field(
        document.add_paragraph(),
        'TOC \\o "1-3" \\h \\z \\u',
        "Actualice el índice en Word para mostrar las secciones.",
    )
    document.add_page_break()


def convert_markdown(source: Path, output: Path) -> set[str]:
    markdown = source.read_text(encoding="utf-8-sig")
    document = Document()
    document.core_properties.title = "Galileo Galilei SIS - Documentación técnica"
    document.core_properties.subject = "Documentación técnica exportada desde Markdown"
    _add_toc(document)

    missing_images: set[str] = set()
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            language = (fence_match.group(2) or "").strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith(fence):
                code.append(lines[index])
                index += 1
            if index == len(lines):
                raise ValueError(f"Bloque de código sin cierre iniciado en la línea {index - len(code)}.")
            _add_code_block(document, code, language)
            index += 1
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            paragraph = document.add_paragraph(style=f"Heading {level}")
            _add_inline(paragraph, heading_match.group(2), source, missing_images)
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[index + 1]):
            rows = [_split_table_row(line)]
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append(_split_table_row(lines[index]))
                index += 1
            _add_table(document, rows, source, missing_images)
            continue

        list_match = LIST_RE.match(line)
        if list_match:
            while index < len(lines):
                list_match = LIST_RE.match(lines[index])
                if not list_match:
                    break
                indent, marker, item_text = list_match.groups()
                style = "List Number" if marker[0].isdigit() else "List Bullet"
                paragraph = document.add_paragraph(style=style)
                paragraph.paragraph_format.left_indent = Inches(min(len(indent) // 2, 6) * 0.25)
                _add_inline(paragraph, item_text, source, missing_images)
                index += 1
            continue

        if stripped.startswith(">"):
            paragraph = document.add_paragraph(style="Quote")
            _add_inline(paragraph, stripped.lstrip("> ").strip(), source, missing_images)
            index += 1
            continue

        if re.fullmatch(r"(---+|___+|\*\*\*+)\s*", stripped):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(8)
            paragraph.add_run("-" * 36).font.color.rgb = RGBColor(150, 150, 150)
            index += 1
            continue

        image_match = IMAGE_RE.fullmatch(stripped)
        if image_match:
            paragraph = document.add_paragraph()
            _add_image(paragraph, source, image_match.group(2).split()[0], missing_images)
            index += 1
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if (
                not next_stripped
                or HEADING_RE.match(next_stripped)
                or FENCE_RE.match(next_line)
                or (next_line.startswith("|") and index + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[index + 1]))
                or LIST_RE.match(next_line)
                or next_stripped.startswith(">")
                or re.fullmatch(r"(---+|___+|\*\*\*+)\s*", next_stripped)
            ):
                break
            paragraph_lines.append(next_stripped)
            index += 1
        paragraph = document.add_paragraph()
        _add_inline(paragraph, " ".join(paragraph_lines), source, missing_images)

    settings = document.settings._element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        settings.append(update_fields)
    update_fields.set(qn("w:val"), "true")

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return missing_images


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte el Markdown de documentación técnica a un DOCX editable."
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Markdown de origen (predeterminado: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Documento DOCX de salida (predeterminado: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_file():
        print(f"No se encontró el archivo de entrada: {source}", file=sys.stderr)
        return 2
    if source == output:
        print("El archivo de salida no puede sobrescribir el Markdown de origen.", file=sys.stderr)
        return 2

    missing_images = convert_markdown(source, output)
    print(f"DOCX generado: {output}")
    if missing_images:
        print("Advertencia: no se encontraron estas imágenes; se dejaron marcadores en el DOCX:")
        for image in sorted(missing_images):
            print(f"  - {image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

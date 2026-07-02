#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import statistics
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc  # noqa: UP017 - keep the script runnable with the system Python 3.9.
TASK_FILE = ROOT / "data" / "tasks" / "mashup_benchmark.jsonl"
DEFAULT_RESULTS_DIR = ROOT / "eval_results"

TASK_TYPES = [
    ("event", "事件型"),
    ("character", "人物型"),
    ("emotion", "情绪型"),
    ("narrative", "叙事型"),
]
METRICS = ["IF", "BCS", "AEC", "VQ", "TC", "NC", "Quality"]
HEADERS = ["评测指标", "事件型", "人物型", "情绪型", "叙事型", "总平均分"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_tasks() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load_jsonl(TASK_FILE)}


def load_summary(eval_dir: Path) -> dict[str, Any]:
    path = eval_dir / "summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def metric_value(row: dict[str, Any], metric: str) -> float | None:
    scores = row.get("scores") or {}
    details = row.get("metric_details") or {}
    detail = details.get(metric) or {}
    if isinstance(detail, dict) and detail.get("normalized_score") is not None:
        return float(detail["normalized_score"])
    if scores.get(metric) is not None:
        return float(scores[metric])
    return None


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def build_table(records: list[dict[str, Any]], tasks: dict[str, dict[str, Any]]) -> list[list[str | float | None]]:
    by_type: dict[str, list[dict[str, Any]]] = {task_type: [] for task_type, _ in TASK_TYPES}
    all_success = []
    for row in records:
        if row.get("status") != "success":
            continue
        task = tasks.get(row.get("task_id"))
        if not task:
            continue
        task_type = task.get("task", {}).get("type")
        if task_type in by_type:
            by_type[task_type].append(row)
            all_success.append(row)

    table = []
    for metric in METRICS:
        output_row: list[str | float | None] = [metric]
        for task_type, _ in TASK_TYPES:
            values = [value for row in by_type[task_type] if (value := metric_value(row, metric)) is not None]
            output_row.append(mean_or_none(values))
        all_values = [value for row in all_success if (value := metric_value(row, metric)) is not None]
        output_row.append(mean_or_none(all_values))
        table.append(output_row)
    return table


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")
    return slug or "model"


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_ref(row: int, col: int) -> str:
    return f"{column_name(col)}{row}"


def inline_string_cell(row: int, col: int, value: str, style: int = 0) -> str:
    ref = cell_ref(row, col)
    return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{escape(value)}</t></is></c>'


def number_cell(row: int, col: int, value: float | None, style: int = 5) -> str:
    if value is None:
        return f'<c r="{cell_ref(row, col)}" s="{style}"/>'
    return f'<c r="{cell_ref(row, col)}" s="{style}"><v>{value:.6f}</v></c>'


def sheet_xml(model_name: str, evaluated_at: str, table: list[list[str | float | None]]) -> str:
    rows = [
        f'<row r="1" ht="24" customHeight="1">{inline_string_cell(1, 1, model_name, 1)}</row>',
        f'<row r="2" ht="20" customHeight="1">{inline_string_cell(2, 1, f"评测时间：{evaluated_at}", 2)}</row>',
    ]
    header_cells = "".join(inline_string_cell(3, idx, header, 3) for idx, header in enumerate(HEADERS, 1))
    rows.append(f'<row r="3" ht="20" customHeight="1">{header_cells}</row>')
    for row_idx, row_values in enumerate(table, 4):
        cells = [inline_string_cell(row_idx, 1, str(row_values[0]), 4)]
        cells.extend(number_cell(row_idx, col_idx, value) for col_idx, value in enumerate(row_values[1:], 2))
        rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="A1:F{len(table) + 3}"/>
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="1" max="1" width="16" customWidth="1"/>
    <col min="2" max="6" width="14" customWidth="1"/>
  </cols>
  <sheetData>
    {"".join(rows)}
  </sheetData>
  <mergeCells count="2"><mergeCell ref="A1:F1"/><mergeCell ref="A2:F2"/></mergeCells>
</worksheet>
"""


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="1"><numFmt numFmtId="164" formatCode="0.00"/></numFmts>
  <fonts count="4">
    <font><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="14"/><name val="Arial"/></font>
    <font><i/><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><name val="Arial"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE7EEF8"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


def write_xlsx(path: Path, model_name: str, evaluated_at: str, table: list[list[str | float | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).isoformat()
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Summary" sheetId="1" r:id="rId1"/></sheets>
</workbook>
""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
""",
        "xl/worksheets/sheet1.xml": sheet_xml(model_name, evaluated_at, table),
        "xl/styles.xml": styles_xml(),
        "docProps/core.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Mashup-Benchmark</dc:creator>
  <cp:lastModifiedBy>Mashup-Benchmark</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>
</cp:coreProperties>
""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Mashup-Benchmark</Application>
</Properties>
""",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)


def resolve_eval_dir(results_dir: Path, eval_id: str) -> Path:
    eval_dir = results_dir / eval_id
    if not eval_dir.exists():
        raise FileNotFoundError(f"Evaluation folder not found: {eval_dir}")
    return eval_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an evaluation result summary table to Excel.")
    parser.add_argument("--model-name", required=True, help="Model or method name shown in the first row.")
    parser.add_argument("--eval-id", required=True, help="Evaluation result folder name under eval_results/.")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Directory containing evaluation result folders.")
    parser.add_argument("--output", default=None, help="Output .xlsx path. Defaults to eval_results/<eval_id>/<eval_id>_<model>_summary.xlsx.")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = ROOT / results_dir
    eval_dir = resolve_eval_dir(results_dir, args.eval_id)
    scores_path = eval_dir / "evaluation_scores.jsonl"
    if not scores_path.exists():
        raise FileNotFoundError(f"Evaluation scores file not found: {scores_path}")

    summary = load_summary(eval_dir)
    evaluated_at = str(summary.get("created_at") or datetime.fromtimestamp(scores_path.stat().st_mtime).isoformat())
    records = load_jsonl(scores_path)
    table = build_table(records, load_tasks())

    output_path = Path(args.output) if args.output else eval_dir / f"{args.eval_id}_{slugify(args.model_name)}_summary.xlsx"
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    write_xlsx(output_path, args.model_name, evaluated_at, table)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

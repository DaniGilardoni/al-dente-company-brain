"""Artifact + deck generation: turn gathered tool data into downloadable files
(docx/pptx/pdf/xlsx) and self-contained HTML sales decks.

This is a leaf module — it has no dependency on the agent loop. The HTML deck
generator needs an LLM call, so the loop injects its `model` string and
`chat_with_deadline` callable rather than this module importing them (which would
create an import cycle)."""

import json
import os
import re
import time
import uuid

from openai import OpenAI

_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "files")

_HTML_DECK_PROMPT = """\
You are generating an HTML sales deck. Use ONLY the data provided below — do not invent any figures.
Produce a complete, self-contained HTML document with 4 slides using inline CSS.
Style: light background (#f4f7f6), dark slate text (#1e293b), Al Dente brand color #F54E00 for headings.
Each slide is a full-viewport section. Use real data only.

Data:
{data}

Return ONLY the raw HTML document (no markdown fences, no JSON wrapper).
"""


def _collect_tool_data(messages: list[dict]) -> str:
    """Join all tool results in the conversation into a single prompt-ready string
    (pretty JSON where parseable). Shared by the artifact + deck generators."""
    parts: list[str] = []
    for m in messages:
        if m.get("role") == "tool":
            try:
                parsed = json.loads(m["content"])
                parts.append(json.dumps(parsed, ensure_ascii=False, indent=2))
            except Exception:
                parts.append(m["content"])
    return "\n\n---\n\n".join(parts) or "No data gathered."


def _gathered_rows(messages: list[dict]) -> tuple[str, list[tuple[str, str]]]:
    """Extract a title + (label, value) fact rows from gathered tool results.
    Flattens scalars and one level of nested dicts; summarizes lists by count."""
    title = "Al Dente S.r.l."
    rows: list[tuple[str, str]] = []

    def _s(v: object) -> str:
        return str(v)[:160]

    for m in messages:
        if m.get("role") != "tool":
            continue
        try:
            data = json.loads(m["content"])
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        custs = data.get("customers")
        if title == "Al Dente S.r.l.":
            if isinstance(custs, list) and custs and isinstance(custs[0], dict) and custs[0].get("name"):
                title = custs[0]["name"]
            elif str(data.get("id", "")).startswith("CUST") and data.get("name"):
                title = data["name"]
        for k, v in data.items():
            label = k.replace("_", " ").title()
            if isinstance(v, (str, int, float, bool)) and v not in ("", None):
                rows.append((label, _s(v)))
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, (str, int, float, bool)) and sv not in ("", None):
                        rows.append((f"{label} · {sk}", _s(sv)))
            elif isinstance(v, list) and v:
                # Expand list items into real rows (the actual facts) instead of
                # collapsing to "N item(s)". Cap per list + overall below.
                rows.append((label, f"{len(v)} total"))
                for it in v[:12]:
                    if isinstance(it, dict):
                        key = (it.get("id") or it.get("sku") or it.get("raw_sku")
                               or it.get("call_id") or "•")
                        summary = _item_summary(it, skip=("id", "sku", "raw_sku", "call_id"))
                        if summary:
                            rows.append((f"  {key}", summary))
                    elif it not in ("", None):
                        rows.append(("  •", _s(it)))

    # De-dup, preserve order, cap
    seen: set = set()
    uniq: list[tuple[str, str]] = []
    for r in rows:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return title, uniq[:60]


# Notable fields to surface (priority order) when summarizing a list item, each
# with a formatter → readable, labelled values instead of bare numbers.
def _f_money(v):
    try:
        return f"€{int(v):,}"
    except (TypeError, ValueError):
        return f"€{v}"


_ITEM_FIELDS: tuple[tuple[str, object], ...] = (
    ("product_name", str), ("name", str), ("description", str), ("topic", str),
    ("stage", str), ("status", str), ("channel", str), ("type", str),
    ("outcome", str), ("category", str), ("quality_status", lambda v: f"quality {v}"),
    ("value_eur", _f_money), ("amount", _f_money), ("total", _f_money),
    ("qty_per_carton", lambda v: f"qty {v}"), ("planned_qty_kg", lambda v: f"{v} kg"),
    ("on_hand", lambda v: f"stock {v}"), ("min_stock", lambda v: f"min {v}"),
    ("below_min", lambda v: "BELOW MIN" if v else ""),
    ("progress_pct", lambda v: f"{v}% done"), ("unit", str),
    ("supplier_name", str), ("lead_time_days", lambda v: f"{v}d lead"),
    ("date", str), ("due_date", lambda v: f"due {v}"),
    ("linked_order_id", str), ("customer_id", str),
)


def _item_summary(item: dict, skip: tuple[str, ...] = ()) -> str:
    """Compact ' · '-joined summary of a record's notable fields (max 6)."""
    parts: list[str] = []
    for f, fmt in _ITEM_FIELDS:
        if f in skip:
            continue
        val = item.get(f)
        if val in (None, "", [], {}):
            continue
        rendered = fmt(val)
        if not rendered:  # e.g. below_min False → skip
            continue
        parts.append(rendered)
        if len(parts) >= 6:
            break
    return " · ".join(parts)[:200]


def _last_text(messages: list[dict]) -> str:
    """Best available textual content when no tool data was gathered this turn:
    the model's latest assistant prose, else the user message (which carries the
    folded conversation context on follow-ups)."""
    for m in reversed(messages):
        if m.get("role") == "assistant" and str(m.get("content", "")).strip():
            return str(m["content"])
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _rows_from_text(text: str, title: str) -> tuple[str, list[tuple[str, str]]]:
    """Turn a textual answer into artifact rows when there is no structured tool
    data — e.g. a follow-up file request the model answered from conversation
    context without re-calling a tool. Splits into sentences/lines and detects
    'Label: value' pairs so the file is never empty."""
    if title == "Al Dente S.r.l.":
        m = re.search(r"\bis\s+([A-Z][^,\n]{2,80})", text)
        if m:
            title = m.group(1).strip()
    chunks: list[str] = []
    for raw in re.split(r"[\n;]+", text):
        raw = raw.strip()
        if not raw:
            continue
        chunks.extend(re.split(r"(?<=[.!?])\s+(?=[A-Z])", raw))
    rows: list[tuple[str, str]] = []
    for ch in chunks:
        ln = ch.strip(" -•\t")
        if not ln:
            continue
        m = re.match(r"^([A-Za-z][\w /&'-]{1,40}?):\s+(.+)$", ln)
        if m:
            rows.append((m.group(1).strip().title(), m.group(2).strip()[:300]))
        else:
            rows.append(("", ln[:300]))
    return title, rows[:60]


# ── LLM-authored content path ───────────────────────────────────────────────
# The model writes content tailored to the request (Markdown for docx/pdf/pptx,
# JSON for xlsx); Python parses it and renders the file deterministically. This
# produces client-ready artifacts instead of a mechanical Field|Value dump. If
# the call times out / errors / returns junk, we fall back to the row-based
# writers below — so a file is never empty and never blows the 30s limit.

_MD_REPORT_PROMPT = """\
You are writing a business document for Al Dente S.r.l. (an Italian pasta maker).
Use ONLY the data provided below — do NOT invent, estimate, or extrapolate any figure.
Write a concise, client-ready document in GitHub-Flavored Markdown:
- a single `# Title`
- `## Section` headings to organize the content
- bullet lists for facts
- GFM tables for any tabular or numeric data (this is what makes it presentable)

Data:
{data}

Return ONLY the Markdown document — no code fences, no commentary.
"""

_MD_DECK_PROMPT = """\
You are writing slide content for Al Dente S.r.l. (an Italian pasta maker).
Use ONLY the data provided below — do NOT invent, estimate, or extrapolate any figure.
Write Markdown where the first `# Title` is the deck title and EACH `## Heading`
starts ONE slide. Keep each slide to a few short bullets or one small GFM table.

Data:
{data}

Return ONLY the Markdown — no code fences, no commentary.
"""

_XLSX_JSON_PROMPT = """\
You are producing an Excel workbook for Al Dente S.r.l. (an Italian pasta maker).
Use ONLY the data provided below — do NOT invent figures. Numbers must be JSON
numbers, not strings. Use ONE sheet per logical section.
Return ONLY JSON of exactly this shape (no commentary, no code fences):
{{"title": "...", "sheets": [{{"name": "Sheet name (<=31 chars)", "columns": ["Col A", "Col B"], "rows": [["v1", 2], ["v3", 4]]}}]}}

Data:
{data}

Return ONLY the JSON.
"""


def _artifact_prompt(fmt: str) -> str:
    return _MD_DECK_PROMPT if fmt == "pptx" else _MD_REPORT_PROMPT


def _extract_json(text: str) -> dict | None:
    """Lenient JSON extraction for the xlsx spec (fences, preamble tolerated)."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            return None
    return None


# ── Markdown → block model (via mistune AST) ────────────────────────────────
def _inline_runs(children: list | None, bold: bool = False) -> list[tuple[str, bool]]:
    """Flatten inline AST nodes to (text, bold) runs."""
    runs: list[tuple[str, bool]] = []
    for n in children or []:
        t = n.get("type")
        if t == "text":
            runs.append((n.get("raw", ""), bold))
        elif t == "strong":
            runs += _inline_runs(n.get("children"), True)
        elif t in ("emphasis", "link"):
            runs += _inline_runs(n.get("children"), bold)
        elif t == "codespan":
            runs.append((n.get("raw", ""), bold))
        elif t in ("linebreak", "softbreak"):
            runs.append((" ", bold))
        elif n.get("children"):
            runs += _inline_runs(n.get("children"), bold)
        elif n.get("raw"):
            runs.append((n.get("raw", ""), bold))
    return runs


def _runs_text(runs: list[tuple[str, bool]]) -> str:
    return "".join(t for t, _ in runs)


def _md_to_blocks(md_text: str) -> list[dict]:
    """Parse Markdown into a normalized block list the renderers consume:
    heading{level,text} · para{runs} · bullets{items} · table{header,rows}."""
    import mistune
    ast = mistune.create_markdown(renderer=None, plugins=["table"])(md_text)
    blocks: list[dict] = []
    for node in ast:
        t = node.get("type")
        if t == "heading":
            blocks.append({"type": "heading",
                           "level": node.get("attrs", {}).get("level", 1),
                           "text": _runs_text(_inline_runs(node.get("children")))})
        elif t == "paragraph":
            runs = _inline_runs(node.get("children"))
            if _runs_text(runs).strip():
                blocks.append({"type": "para", "runs": runs})
        elif t == "list":
            items: list[list[tuple[str, bool]]] = []
            for li in node.get("children", []):
                runs: list[tuple[str, bool]] = []
                for c in li.get("children", []):
                    runs += _inline_runs(c.get("children"))
                if _runs_text(runs).strip():
                    items.append(runs)
            if items:
                blocks.append({"type": "bullets", "items": items})
        elif t == "table":
            header: list[str] = []
            rows: list[list[str]] = []
            for part in node.get("children", []):
                if part.get("type") == "table_head":
                    header = [_runs_text(_inline_runs(c.get("children")))
                              for c in part.get("children", [])]
                elif part.get("type") == "table_body":
                    for tr in part.get("children", []):
                        rows.append([_runs_text(_inline_runs(c.get("children")))
                                     for c in tr.get("children", [])])
            if header or rows:
                blocks.append({"type": "table", "header": header, "rows": rows})
        elif t in ("block_code", "code"):
            code = node.get("raw", "")
            if code.strip():
                blocks.append({"type": "para", "runs": [(code, False)]})
    return blocks


def _split_title(blocks: list[dict], fallback: str) -> tuple[str, list[dict]]:
    """Pull a leading `# Title` out as the document title; return (title, body)."""
    if blocks and blocks[0]["type"] == "heading" and blocks[0]["level"] == 1:
        return (blocks[0]["text"] or fallback), blocks[1:]
    return fallback, blocks


# ── Renderers from the block model ──────────────────────────────────────────
def _render_docx(path: str, body: list[dict], title: str) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading(title, level=0)
    for b in body:
        if b["type"] == "heading":
            doc.add_heading(b["text"], level=min(max(b["level"], 1), 4))
        elif b["type"] == "para":
            p = doc.add_paragraph()
            for text, bold in b["runs"]:
                p.add_run(text).bold = bold
        elif b["type"] == "bullets":
            for item in b["items"]:
                p = doc.add_paragraph(style="List Bullet")
                for text, bold in item:
                    p.add_run(text).bold = bold
        elif b["type"] == "table":
            ncols = len(b["header"]) or (len(b["rows"][0]) if b["rows"] else 1)
            table = doc.add_table(rows=1, cols=ncols)
            try:
                table.style = "Light Grid Accent 1"
            except Exception:
                pass
            hdr = table.rows[0].cells
            for i, h in enumerate(b["header"][:ncols]):
                hdr[i].text = h
                for para in hdr[i].paragraphs:
                    for run in para.runs:
                        run.bold = True
            for row in b["rows"]:
                cells = table.add_row().cells
                for i, val in enumerate(row[:ncols]):
                    cells[i].text = str(val)
    doc.save(path)


def _render_pdf(path: str, body: list[dict], title: str) -> None:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    def _l(s: str) -> str:  # core fonts are latin-1 only
        return str(s).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(epw, 9, _l(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    for b in body:
        if b["type"] == "heading":
            size = {1: 15, 2: 13, 3: 12}.get(b["level"], 11)
            pdf.set_font("Helvetica", "B", size)
            pdf.multi_cell(epw, 7, _l(b["text"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif b["type"] == "para":
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(epw, 6, _l(_runs_text(b["runs"])),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif b["type"] == "bullets":
            pdf.set_font("Helvetica", size=11)
            for item in b["items"]:
                pdf.multi_cell(epw, 6, _l("•  " + _runs_text(item)),
                               new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif b["type"] == "table":
            ncols = len(b["header"]) or (len(b["rows"][0]) if b["rows"] else 1)
            data = ([b["header"]] if b["header"] else []) + b["rows"]
            if not data:
                continue
            pdf.set_font("Helvetica", size=9)
            with pdf.table(first_row_as_headings=bool(b["header"])) as table:
                for r in data:
                    row = table.row()
                    for c in list(r)[:ncols]:
                        row.cell(_l(str(c)))
            pdf.ln(2)
    pdf.output(path)


def _pptx_add_table(slide, tb: dict, top_in: float = 1.8) -> None:
    from pptx.util import Inches, Pt
    header, rows = tb["header"], tb["rows"][:12]
    ncols = len(header) or (len(rows[0]) if rows else 1)
    nrows = len(rows) + (1 if header else 0)
    if nrows == 0 or ncols == 0:
        return
    gf = slide.shapes.add_table(nrows, ncols, Inches(0.5), Inches(top_in),
                                Inches(9), Inches(min(0.4 * nrows, 5)))
    table = gf.table
    r0 = 0
    if header:
        for j, h in enumerate(header[:ncols]):
            cell = table.cell(0, j)
            cell.text = str(h)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.size = Pt(12)
        r0 = 1
    for i, row in enumerate(rows):
        for j, val in enumerate(list(row)[:ncols]):
            cell = table.cell(r0 + i, j)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(11)


def _render_pptx(path: str, body: list[dict], title: str) -> None:
    from pptx import Presentation
    from pptx.util import Pt
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    if len(s.placeholders) > 1:
        s.placeholders[1].text = "Al Dente S.r.l. — generated report"
    # Group body blocks into slides at each top-level heading.
    groups: list[dict] = []
    cur: dict | None = None
    for b in body:
        if b["type"] == "heading" and b["level"] <= 2:
            cur = {"title": b["text"] or "Details", "blocks": []}
            groups.append(cur)
        else:
            if cur is None:
                cur = {"title": "Overview", "blocks": []}
                groups.append(cur)
            cur["blocks"].append(b)
    if not groups:
        groups = [{"title": "Overview", "blocks": body}]
    for g in groups[:6]:
        tables = [b for b in g["blocks"] if b["type"] == "table"]
        texts = [b for b in g["blocks"] if b["type"] in ("para", "bullets")]
        if tables:
            slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
            slide.shapes.title.text = g["title"]
            _pptx_add_table(slide, tables[0])
        else:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = g["title"]
            tf = slide.placeholders[1].text_frame
            tf.clear()
            first = True
            for b in texts:
                lines = ([_runs_text(it) for it in b["items"]]
                         if b["type"] == "bullets" else [_runs_text(b["runs"])])
                for line in lines:
                    para = tf.paragraphs[0] if first else tf.add_paragraph()
                    first = False
                    para.text = line
                    para.font.size = Pt(16)
    prs.save(path)


def _render_xlsx(path: str, spec: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    sheets = spec.get("sheets") or []
    if not sheets:
        raise ValueError("xlsx spec has no sheets")
    wb = Workbook()
    first = True
    for sh in sheets:
        ws = wb.active if first else wb.create_sheet()
        ws.title = (str(sh.get("name") or "Sheet"))[:31]
        first = False
        cols = sh.get("columns") or []
        if cols:
            ws.append([str(c) for c in cols])
            for cell in ws[1]:
                cell.font = Font(bold=True)
            ws.freeze_panes = "A2"
        for row in sh.get("rows") or []:
            ws.append(list(row))
        for i, col in enumerate(ws.columns, 1):
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 50)
    wb.save(path)


def _xlsx_spec_to_text(spec: dict) -> str:
    """Textual rendering of an xlsx spec for the `answer` field."""
    lines = [str(spec.get("title") or "Al Dente S.r.l."), ""]
    for sh in spec.get("sheets", []):
        lines.append(f"## {sh.get('name', 'Sheet')}")
        cols = sh.get("columns") or []
        if cols:
            lines.append(" | ".join(str(c) for c in cols))
        for row in (sh.get("rows") or [])[:30]:
            lines.append(" | ".join(str(c) for c in row))
        lines.append("")
    return "\n".join(lines).strip()


# ── LLM calls (deadline-bounded; loop injects model + chat_with_deadline) ────
def _generate_markdown(client: OpenAI, question: str, messages: list[dict],
                       fmt: str, deadline: float, *, model: str,
                       chat_with_deadline) -> str | None:
    attempt_deadline = min(deadline, time.time() + 60.0)
    prompt = _artifact_prompt(fmt).format(data=_collect_tool_data(messages)[:8000])
    resp = chat_with_deadline(
        client, attempt_deadline, model=model,
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": question}],
        max_tokens=1400,  # a one-pager/sheet fits; lower → faster regolo completion
    )
    md = resp.choices[0].message.content or ""
    md = re.sub(r"^```(?:markdown|md)?\s*", "", md.strip())
    md = re.sub(r"\s*```$", "", md)
    return md.strip() or None


def _generate_xlsx_spec(client: OpenAI, question: str, messages: list[dict],
                        deadline: float, *, model: str,
                        chat_with_deadline) -> dict | None:
    attempt_deadline = min(deadline, time.time() + 60.0)
    prompt = _XLSX_JSON_PROMPT.format(data=_collect_tool_data(messages)[:8000])
    resp = chat_with_deadline(
        client, attempt_deadline, model=model,
        messages=[{"role": "system", "content": prompt},
                  {"role": "user", "content": question}],
        max_tokens=1400,  # a one-pager/sheet fits; lower → faster regolo completion
    )
    return _extract_json(resp.choices[0].message.content or "")


def make_artifact(question: str, messages: list[dict], fmt: str,
                  fallback_text: str | None = None, *, client: OpenAI | None = None,
                  model: str | None = None, chat_with_deadline=None,
                  deadline: float | None = None) -> tuple[str, str]:
    """Generate a docx/pptx/pdf/xlsx file and return (textual_answer, artifact_url).

    Primary path: an LLM authors task-tailored content (Markdown for docx/pdf/pptx,
    JSON for xlsx) which is parsed and rendered deterministically. Falls back to the
    row-based writers if the LLM handles are absent, time is up, or anything fails —
    so the file is never empty."""
    os.makedirs(_FILES_DIR, exist_ok=True)
    fname = f"aldente-{uuid.uuid4().hex[:12]}.{fmt}"
    path = os.path.join(_FILES_DIR, fname)

    answer_text: str | None = None
    produced = False
    if client and chat_with_deadline and deadline and (deadline - time.time() > 4):
        try:
            if fmt == "xlsx":
                spec = _generate_xlsx_spec(client, question, messages, deadline,
                                           model=model, chat_with_deadline=chat_with_deadline)
                if spec and spec.get("sheets"):
                    _render_xlsx(path, spec)
                    answer_text = _xlsx_spec_to_text(spec)
                    produced = True
            else:
                md = _generate_markdown(client, question, messages, fmt, deadline,
                                        model=model, chat_with_deadline=chat_with_deadline)
                blocks = _md_to_blocks(md) if md else []
                if blocks:
                    fallback_title, _ = _gathered_rows(messages)
                    title, bodyblocks = _split_title(blocks, fallback_title)
                    if fmt == "docx":
                        _render_docx(path, bodyblocks, title)
                    elif fmt == "pptx":
                        _render_pptx(path, bodyblocks, title)
                    else:  # pdf
                        _render_pdf(path, bodyblocks, title)
                    answer_text = md.strip()
                    produced = True
        except Exception:
            produced = False  # fall through to the deterministic row-based writer

    if not produced:
        title, rows = _gathered_rows(messages)
        if not rows:
            # No tool data this turn (e.g. a follow-up answered from context) → build
            # the file from the model's textual answer so it is never empty.
            text = (fallback_text or "").strip() or _last_text(messages)
            if text.strip():
                title, rows = _rows_from_text(text, title)
        if fmt == "docx":
            _write_docx(path, title, rows)
        elif fmt == "pptx":
            _write_pptx(path, title, rows)
        elif fmt == "xlsx":
            _write_xlsx(path, title, rows)
        else:  # pdf
            _write_pdf(path, title, rows)
        text_lines = [title, ""] + [f"- {k}: {v}" if k else f"- {v}" for k, v in rows]
        answer_text = "\n".join(text_lines)

    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    url = f"{base}/files/{fname}" if base else f"/files/{fname}"
    answer = f"{answer_text}\n\n[Downloadable {fmt.upper()}: {url}]"
    return answer, url


def _write_docx(path: str, title: str, rows: list[tuple[str, str]]) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading(title, level=0)
    for k, v in rows:
        p = doc.add_paragraph()
        if k:
            p.add_run(f"{k}: ").bold = True
        p.add_run(str(v))
    doc.save(path)


def _write_pptx(path: str, title: str, rows: list[tuple[str, str]]) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    # Title slide
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    if len(s.placeholders) > 1:
        s.placeholders[1].text = "Al Dente S.r.l. — generated report"
    # Up to 3 content slides, ~6 facts each
    chunks = [rows[i:i + 6] for i in range(0, len(rows), 6)][:3] or [[]]
    headings = ["Overview", "Key Figures", "Details"]
    for i, chunk in enumerate(chunks):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = headings[min(i, len(headings) - 1)]
        body = slide.placeholders[1].text_frame
        body.clear()
        for j, (k, v) in enumerate(chunk):
            para = body.paragraphs[0] if j == 0 else body.add_paragraph()
            para.text = f"{k}: {v}" if k else f"{v}"
            para.font.size = Pt(16)
    prs.save(path)


def _write_xlsx(path: str, title: str, rows: list[tuple[str, str]]) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31] or "Report"
    ws.append(["Field", "Value"])
    for k, v in rows:
        ws.append([k, str(v)])
    wb.save(path)


def _write_pdf(path: str, title: str, rows: list[tuple[str, str]]) -> None:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    def _latin1(s: str) -> str:  # core fonts are latin-1 only
        return str(s).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin  # explicit width (w=0 is unreliable)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(epw, 10, _latin1(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", size=11)
    for k, v in rows:
        pdf.multi_cell(epw, 7, _latin1(f"{k}: {v}" if k else f"{v}"),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.output(path)


def generate_html_deck(client: OpenAI, question: str, messages: list[dict],
                       deadline: float, *, model: str, chat_with_deadline) -> str:
    """Generate an HTML deck from gathered data. Falls back to a no-LLM templated
    deck if there is no time budget left or the model call fails — so a slow regolo
    moment never produces an error string (which scores wrong) past the 30s limit.

    `model` (the model id) and `chat_with_deadline` (the deadline-bounded chat
    completion callable) are injected by the loop to avoid an import cycle."""
    # Give the model room to finish (time is not the constraint); fall back to the
    # instant templated deck only if essentially no budget is left or the call fails.
    attempt_deadline = min(deadline, time.time() + 60.0)
    if attempt_deadline - time.time() < 5:
        return _template_deck(question, messages)

    prompt = _HTML_DECK_PROMPT.format(data=_collect_tool_data(messages)[:8000])  # cap context

    try:
        resp = chat_with_deadline(
            client,
            attempt_deadline,
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            max_tokens=2600,  # bound generation length → bound latency
        )
        html = resp.choices[0].message.content or ""
        # Strip markdown fences if present
        html = re.sub(r"^```(?:html)?\s*", "", html.strip())
        html = re.sub(r"\s*```$", "", html)
        if "<" not in html:  # model returned prose, not HTML
            return _template_deck(question, messages)
        return html
    except Exception:
        return _template_deck(question, messages)


def _template_deck(question: str, messages: list[dict]) -> str:
    """Build a self-contained 4-slide HTML deck from gathered tool data WITHOUT an
    LLM call. Real data only; used as the latency/timeout fallback."""
    import html as _h

    blocks: list[object] = []
    for m in messages:
        if m.get("role") == "tool":
            try:
                blocks.append(json.loads(m["content"]))
            except Exception:
                pass

    # Flatten gathered data into (label, value) rows; surface a title.
    title = "Al Dente S.r.l."
    rows: list[tuple[str, str]] = []

    def _scalar(v: object) -> str:
        return _h.escape(str(v))[:120]

    for data in blocks:
        if not isinstance(data, dict):
            continue
        # Title: first customer name we find
        custs = data.get("customers")
        if title == "Al Dente S.r.l.":
            if isinstance(custs, list) and custs and isinstance(custs[0], dict):
                title = custs[0].get("name", title)
            elif str(data.get("id", "")).startswith("CUST") and data.get("name"):
                title = data["name"]
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)) and v not in ("", None):
                rows.append((k.replace("_", " ").title(), _scalar(v)))

    # De-dup, cap, and split into 3 content slides
    seen: set = set()
    uniq: list[tuple[str, str]] = []
    for r in rows:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    uniq = uniq[:18]
    per = max(1, -(-len(uniq) // 3)) if uniq else 1
    chunks = [uniq[i:i + per] for i in range(0, len(uniq), per)] or [[]]
    headings = ["Overview", "Key Figures", "Details", "Summary"]

    def _slide(h: str, body: str) -> str:
        return (
            '<section style="min-height:100vh;background:#f4f7f6;color:#1e293b;'
            'padding:6vh 8vw;box-sizing:border-box;font-family:Helvetica,Arial,sans-serif">'
            f'<h1 style="color:#F54E00;font-size:2.4rem;margin:0 0 1.2rem">{h}</h1>{body}</section>'
        )

    slides = [_slide(_h.escape(title),
                     f'<p style="font-size:1.3rem;color:#64748b">{_h.escape(question)}</p>')]
    for i, chunk in enumerate(chunks[:3]):
        body = "".join(
            f'<div style="font-size:1.1rem;margin:.5rem 0">'
            f'<span style="color:#F54E00">{k}:</span> {v}</div>'
            for k, v in chunk
        ) or '<p style="color:#64748b">Data gathered from Al Dente sources.</p>'
        slides.append(_slide(headings[min(i + 1, len(headings) - 1)], body))

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>{_h.escape(title)}</title></head>'
        '<body style="margin:0">' + "".join(slides) + "</body></html>"
    )

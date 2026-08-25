from __future__ import annotations

import io
import json
import textwrap
import zipfile
from xml.sax.saxutils import escape

from .core import AREA_LABELS, AREAS, DIMENSION_LABELS, DIMENSIONS, audit_case, render_report


def _paragraph(value: str) -> str:
    return "<p>" + "<br>".join(escape(value).splitlines() or ["No narrative entered."]) + "</p>"


def _sources(source_ids) -> str:
    return "<div class=\"sources\"><b>Sources</b> " + (" · ".join(escape(item) for item in source_ids) if source_ids else "No source identifiers cited") + "</div>"


def html_report(data):
    audit = audit_case(data)
    metrics = audit["metrics"]
    title = escape(data["case_id"])
    summary = [
        ("Investigator", data.get("investigator") or "Not assigned"),
        ("Case stage", data.get("status", "intake").replace("_", " ").title()),
        ("Target completion", data.get("target_date") or "Not set"),
        ("Prepared", data.get("updated_at", "")[:10] or "Not recorded"),
    ]
    stat_cards = [("Areas complete", f"{metrics['areas_complete']} / {metrics['areas_total']}"), ("Open inquiries", str(metrics["open_inquiries"])), ("Open discrepancies", str(metrics["open_discrepancies"])), ("Registered sources", str(metrics["sources"]))]
    dimension_sections = "".join(f'<section id="dimension-{key}"><h2>{escape(DIMENSION_LABELS[key])}</h2>{_paragraph(data["dimensions"][key]["narrative"])}{_sources(data["dimensions"][key]["source_ids"])}</section>' for key in DIMENSIONS)
    area_sections = "".join(f'<section id="area-{key}"><div class="section-kicker">Required area · {escape(data["areas"][key]["status"].replace("_", " ").title())}</div><h2>{escape(AREA_LABELS[key])}</h2>{_paragraph(data["areas"][key]["narrative"])}{_sources(data["areas"][key]["source_ids"])}</section>' for key in AREAS)
    discrepancies = [item for item in data["discrepancies"] if item["status"] != "resolved"]
    discrepancy_html = "<p class=\"empty\">No unresolved matters recorded.</p>" if not discrepancies else "".join(f'<article class="matter"><h3>{escape(item["id"])} · {escape(item["title"])}</h3><dl><dt>Candidate account</dt><dd>{escape(item["candidate_statement"])}</dd><dt>Contrary information</dt><dd>{escape(item["contrary_information"])}</dd><dt>Current disposition</dt><dd>{escape(item["status"].replace("_", " ").title())}</dd></dl></article>' for item in discrepancies)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Background Investigation Report · {title}</title><style>
@page{{size:letter;margin:.58in}}*{{box-sizing:border-box}}body{{margin:0;background:#e9ece8;color:#18231d;font:11pt/1.65 Georgia,"Times New Roman",serif}}.page{{width:min(8.5in,calc(100% - 32px));margin:28px auto;background:#fff;box-shadow:0 14px 45px #24312622;padding:.72in .75in;min-height:10.4in}}.cover{{display:flex;min-height:10.4in;flex-direction:column;border-top:11px solid #1c5d43}}.badge,.section-kicker{{font:700 9px/1.2 Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#1c5d43}}h1{{font:500 37px/1.06 Georgia,serif;margin:28px 0 8px;letter-spacing:-.03em}}h2{{font:500 20px/1.2 Georgia,serif;margin:0 0 14px;color:#173b2b}}h3{{font:700 12px/1.35 Arial,sans-serif;margin:0 0 10px}}.subtitle{{color:#5d6b62;font-size:15px;margin:0}}.confidential{{margin-top:auto;background:#f5f0e5;border-left:3px solid #b47d25;padding:13px 15px;color:#5d4825;font:10px/1.45 Arial,sans-serif}}.meta{{margin-top:42px;border-top:1px solid #ced8d0}}.meta div{{display:grid;grid-template-columns:145px 1fr;padding:11px 0;border-bottom:1px solid #e2e8e3}}.meta b{{font:700 9px Arial,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:#68776d}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:22px 0 28px}}.stat{{border:1px solid #d7e1da;padding:13px;background:#fbfdfb}}.stat b{{display:block;font:700 9px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#68776d}}.stat strong{{display:block;font:500 24px Georgia,serif;margin-top:5px;color:#1c5d43}}.toc{{columns:2;gap:28px;border-top:1px solid #d8e0da;padding-top:15px}}.toc a{{display:block;padding:4px 0;color:#315244;text-decoration:none;font:10px/1.35 Arial,sans-serif}}section{{border-top:1px solid #d6dfd8;padding:25px 0;break-inside:avoid}}section p{{margin:0 0 13px;white-space:normal}}.sources{{font:9px/1.45 Arial,sans-serif;color:#637168;background:#f5f8f5;padding:9px 11px;border-left:2px solid #87a796}}.sources b{{text-transform:uppercase;letter-spacing:.08em;font-size:8px;margin-right:8px}}.matter{{border:1px solid #e0d8c6;background:#fffdf8;padding:15px;margin:10px 0;break-inside:avoid}}dl{{margin:0}}dt{{font:700 9px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#756142;margin-top:10px}}dd{{margin:2px 0 0}}.empty{{color:#68776d;font-style:italic}}.footer{{font:9px Arial,sans-serif;color:#6f7d74;margin-top:34px;padding-top:12px;border-top:1px solid #d6dfd8}}@media print{{body{{background:#fff}}.page{{width:auto;min-height:0;margin:0;box-shadow:none;padding:0;page-break-after:always}}.page:last-child{{page-break-after:auto}}}}@media(max-width:700px){{.page{{width:calc(100% - 20px);padding:28px 22px;min-height:0}}h1{{font-size:30px}}.stats{{grid-template-columns:repeat(2,1fr)}}.toc{{columns:1}}.meta div{{grid-template-columns:1fr;gap:3px}}}}
</style></head><body><article class="page cover"><div class="badge">Investigator Workbench · Case Report</div><h1>Background<br>Investigation Report</h1><p class="subtitle">Case {title}</p><div class="meta">{"".join(f'<div><b>{escape(label)}</b><span>{escape(value)}</span></div>' for label,value in summary)}</div><div class="confidential"><b>Working document.</b> Verify every statement against cited source material and controlling agency policy before reliance, submission, or distribution.</div></article><article class="page"><div class="badge">Case overview</div><h2>Review at a glance</h2><div class="stats">{"".join(f'<div class="stat"><b>{escape(label)}</b><strong>{escape(value)}</strong></div>' for label,value in stat_cards)}</div><div class="badge">Report map</div><nav class="toc"><a href="#unresolved">Unresolved matters</a>{"".join(f'<a href="#dimension-{key}">{escape(DIMENSION_LABELS[key])}</a>' for key in DIMENSIONS)}{"".join(f'<a href="#area-{key}">{escape(AREA_LABELS[key])}</a>' for key in AREAS)}</nav><div class="footer">Case {title} · Generated from Investigator Workbench</div></article><article class="page" id="unresolved"><div class="badge">Disposition review</div><h2>Unresolved matters</h2>{discrepancy_html}</article><article class="page"><div class="badge">POST suitability dimensions</div>{dimension_sections}</article><article class="page"><div class="badge">Bias assessment information</div><section><h2>Bias-Relevant Findings</h2>{_paragraph(data["bias_relevant_findings"]["narrative"])}{_sources(data["bias_relevant_findings"]["source_ids"])}</section><div class="badge">Required areas of investigation</div>{area_sections}<div class="footer">End of report · Case {title}</div></article></body></html>'''


def docx_export(data):
    def paragraph(text, style=None):
        properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f'<w:p>{properties}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'

    metrics = audit_case(data)["metrics"]
    paragraphs = [
        paragraph("INVESTIGATOR WORKBENCH · CASE REPORT", "Kicker"),
        paragraph("Background Investigation Report", "Title"),
        paragraph(f"Case {data['case_id']}", "Subtitle"),
        paragraph("Working document. Verify every statement against cited source material and controlling agency policy before reliance, submission, or distribution.", "Notice"),
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>',
        paragraph("Case Overview", "Heading1"),
        paragraph(f"Investigator: {data.get('investigator') or 'Not assigned'}"),
        paragraph(f"Case stage: {data.get('status', 'intake').replace('_', ' ').title()}"),
        paragraph(f"Target completion: {data.get('target_date') or 'Not set'}"),
        paragraph(f"Review status: {metrics['areas_complete']} of {metrics['areas_total']} required areas complete; {metrics['open_inquiries']} open inquiries; {metrics['open_discrepancies']} open discrepancies."),
    ]
    for line in render_report(data).splitlines():
        if line.startswith("# "):
            continue
        style = "Heading1" if line.startswith("## ") else "Heading2" if line.startswith("### ") else None
        text = line.lstrip("# ") if style else line
        paragraphs.append(paragraph(text, style))
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + "".join(paragraphs) + '<w:sectPr><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/></w:sectPr></w:body></w:document>'
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:spacing w:after="220"/></w:pPr><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:color w:val="173B2B"/><w:sz w:val="56"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:pPr><w:spacing w:after="440"/></w:pPr><w:rPr><w:color w:val="5D6B62"/><w:sz w:val="26"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Kicker"><w:name w:val="Kicker"/><w:pPr><w:spacing w:after="180"/></w:pPr><w:rPr><w:b/><w:color w:val="1C5D43"/><w:sz w:val="16"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Notice"><w:name w:val="Notice"/><w:pPr><w:shd w:fill="F5F0E5"/><w:spacing w:before="160" w:after="260"/></w:pPr><w:rPr><w:color w:val="5D4825"/><w:sz w:val="18"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:spacing w:before="300" w:after="160"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:color w:val="173B2B"/><w:sz w:val="32"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:spacing w:before="220" w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="1C5D43"/><w:sz w:val="24"/></w:rPr></w:style></w:styles>'''
    types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
    relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
    return output.getvalue()


def pdf_export(data):
    def pdf_text(value):
        return value.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = []
    for line in render_report(data).splitlines():
        level = 0
        if line.startswith("### "):
            level, line = 3, line[4:]
        elif line.startswith("## "):
            level, line = 2, line[3:]
        elif line.startswith("# "):
            level, line = 1, line[2:]
        body.extend((level, text) for text in (textwrap.wrap(line.lstrip("> "), 86) or [""]))
    chunks = [body[index:index + 43] for index in range(0, len(body), 43)] or [[]]
    cover = ["q 0.11 0.36 0.26 rg 0 742 612 50 re f Q", "BT /F2 9 Tf 50 706 Td 12 TL (INVESTIGATOR WORKBENCH  -  CASE REPORT) Tj ET", "BT /F2 30 Tf 50 624 Td 38 TL (Background Investigation) Tj T* (Report) Tj ET", f"BT /F1 16 Tf 50 550 Td (Case {pdf_text(data['case_id'])}) Tj ET", "BT /F2 10 Tf 50 455 Td 20 TL (WORKING DOCUMENT) Tj T* /F1 10 Tf (Verify every statement against cited source material and controlling) Tj T* (agency policy before reliance, submission, or distribution.) Tj ET"]
    pages = [cover]
    for page_number, chunk in enumerate(chunks, 2):
        commands = ["q 0.11 0.36 0.26 rg 0 760 612 32 re f Q", f"BT /F2 8 Tf 50 772 Td (BACKGROUND INVESTIGATION REPORT  -  CASE {pdf_text(data['case_id'])}) Tj ET", "BT 50 728 Td 15 TL"]
        for level, line in chunk:
            if not line:
                commands.append("T*")
                continue
            commands.append(f"/F{'2' if level else '1'} {'15' if level == 1 else '12' if level else '10'} Tf")
            commands.append(f"({pdf_text(line)}) Tj T*")
        commands.append("ET")
        commands.append(f"BT /F1 8 Tf 50 28 Td (Investigator Workbench  -  Working document  -  Page {page_number}) Tj ET")
        pages.append(commands)
    objects = []
    def add(value):
        objects.append(value)
        return len(objects)
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    pages_id = add(b"")
    page_ids, content_ids = [], []
    for commands in pages:
        stream = "\n".join(commands).encode("latin-1")
        content_ids.append(add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"))
        page_ids.append(add(b""))
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    for index, page_id in enumerate(page_ids):
        objects[page_id - 1] = f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R /F2 {bold_font_id} 0 R >> >> /Contents {content_ids[index]} 0 R >>".encode()
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    result.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    result.extend(f"trailer << /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def json_export(data):
    return json.dumps(data, indent=2, sort_keys=True).encode()

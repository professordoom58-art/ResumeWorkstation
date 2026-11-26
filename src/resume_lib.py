# -*- coding: utf-8 -*-
"""Resume generator: DOCX + PDF (via Word COM), to the layout in CLAUDE.md "Resume specification"."""
import docx, os, subprocess, sys
from docx.shared import Pt, Mm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT = "Helvetica"
EN = "\u2013"      # en dash
BULLET = "\u2022"
PIPE = "  |  "
DOT = "  \u2022  "

def _font(run, size, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    rPr = run._element.get_or_add_rPr()
    rf = rPr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rPr.append(rf)
    for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rf.set(qn(a), FONT)

def _para(doc, space_before=0, space_after=0, align=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = 1.0
    if align is not None:
        p.alignment = align
    return p

def _rule(p, width=8, space=2):
    """Thin black bottom border under a paragraph."""
    pPr = p._element.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    b = OxmlElement('w:bottom')
    b.set(qn('w:val'), 'single'); b.set(qn('w:sz'), str(width))
    b.set(qn('w:space'), str(space)); b.set(qn('w:color'), '000000')
    pbdr.append(b); pPr.append(pbdr)

def _hanging(p, left_in=0.375, hang_in=0.1875):
    pf = p.paragraph_format
    pf.left_indent = Inches(left_in)
    pf.first_line_indent = Inches(-hang_in)

def _hyperlink(paragraph, url, text, size):
    part = paragraph.part
    r_id = part.relate_to(url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    hl = OxmlElement('w:hyperlink'); hl.set(qn('r:id'), r_id)
    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    rf = OxmlElement('w:rFonts')
    for a in ('w:ascii', 'w:hAnsi', 'w:cs'):
        rf.set(qn(a), FONT)
    rPr.append(rf)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(int(size*2))); rPr.append(sz)
    c = OxmlElement('w:color'); c.set(qn('w:val'), '000000'); rPr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'none'); rPr.append(u)
    new_run.append(rPr)
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve')
    new_run.append(t); hl.append(new_run)
    paragraph._p.append(hl)

def build(spec, out_docx):
    doc = docx.Document()
    cp = doc.core_properties
    cp.author = cp.last_modified_by = spec['name'].title()
    cp.title = spec.get('doc_title', spec['name'].title() + "'s Resume")
    cp.subject = cp.keywords = cp.comments = ""
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Inches(0.75)
    sec.top_margin = sec.bottom_margin = Inches(0.69)
    st = doc.styles['Normal']
    st.font.name = FONT; st.font.size = Pt(10)
    st.paragraph_format.space_before = Pt(0)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.line_spacing = 1.0
    # remove docx default bullet-numbering weirdness by not using list styles
    content_w = sec.page_width - sec.left_margin - sec.right_margin

    # ---- NAME
    p = _para(doc, 0, 1, WD_ALIGN_PARAGRAPH.CENTER)
    _font(p.add_run(spec['name']), 15, True)

    # ---- TITLE LINE
    p = _para(doc, 0, 1, WD_ALIGN_PARAGRAPH.CENTER)
    _font(p.add_run(PIPE.join(spec['title_line'])), 10)

    # ---- CONTACT
    p = _para(doc, 0, 3, WD_ALIGN_PARAGRAPH.CENTER)
    c = spec['contact']
    _font(p.add_run(c['location'] + DOT), 9.5)
    _hyperlink(p, "mailto:" + c['email'], c['email'], 9.5)
    _font(p.add_run(DOT + c['phone']), 9.5)
    if c.get('linkedin_url'):
        _font(p.add_run(DOT), 9.5)
        _hyperlink(p, c['linkedin_url'], c.get('linkedin_text') or c['linkedin_url'], 9.5)

    # ---- SUMMARY
    def section(title):
        pp = _para(doc, 8, 3.5)
        _font(pp.add_run(title), 10.5, True)
        _rule(pp)

    section('PROFESSIONAL SUMMARY')
    for line in spec['summary']:
        p = _para(doc, 0, 0)
        _font(p.add_run(line), 10)

    # ---- EXPERIENCE
    section('PROFESSIONAL EXPERIENCE')
    for i, job in enumerate(spec['experience']):
        p = _para(doc, 0 if i == 0 else 5, 0)
        p.paragraph_format.tab_stops.add_tab_stop(content_w, WD_TAB_ALIGNMENT.RIGHT)
        _font(p.add_run(job['company'] + "\t" + job['location']), 10, True)
        p = _para(doc, 0, 0)
        p.paragraph_format.tab_stops.add_tab_stop(content_w, WD_TAB_ALIGNMENT.RIGHT)
        _font(p.add_run(job['title'] + "\t" + job['dates']), 10, True)
        for b in job['bullets']:
            p = _para(doc, 0, 0.5)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(0.375), WD_TAB_ALIGNMENT.LEFT)
            _hanging(p)
            _font(p.add_run(BULLET + "\t" + b), 10)

    # ---- EDUCATION
    section('EDUCATION')
    for i, e in enumerate(spec['education']):
        p = _para(doc, 0 if i == 0 else 5, 0)
        p.paragraph_format.tab_stops.add_tab_stop(content_w, WD_TAB_ALIGNMENT.RIGHT)
        _font(p.add_run(e['school'] + "\t" + e['location']), 10, True)
        p = _para(doc, 0, 0)
        p.paragraph_format.tab_stops.add_tab_stop(content_w, WD_TAB_ALIGNMENT.RIGHT)
        _font(p.add_run(e['degree']), 10, False)
        _font(p.add_run("\t" + e['years']), 10, True)

    # ---- ADDITIONAL INFORMATION
    section('ADDITIONAL INFORMATION')
    for label, text in spec['additional']:
        p = _para(doc, 0, 0.5)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(0.375), WD_TAB_ALIGNMENT.LEFT)
        _hanging(p)
        _font(p.add_run(BULLET + "\t"), 10)
        _font(p.add_run(label + ":"), 10, True)
        _font(p.add_run(" " + text), 10)

    os.makedirs(os.path.dirname(out_docx), exist_ok=True)
    doc.save(out_docx)
    return out_docx

PS = r'''param([string]$in,[string]$out)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $doc = $word.Documents.Open($in, $false, $true)
  $doc.SaveAs([ref]$out, [ref]17)
  $doc.Close([ref]0)
} finally { $word.Quit() }
'''

def to_pdf(docx_path, pdf_path):
    ps = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'w2p.ps1')
    with open(ps, 'w') as f: f.write(PS)
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', ps, '-in', os.path.abspath(docx_path),
                    '-out', os.path.abspath(pdf_path)],
                   check=True, capture_output=True)
    return pdf_path

def pages(pdf_path):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    d = fitz.open(pdf_path)
    return len(d), [len(p.get_text().strip()) for p in d]

"""
Generate downloadable study guides in PDF and DOCX formats from study plan data.
"""
from io import BytesIO
from datetime import datetime

# --- PDF Generation (reportlab) ---
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# ================================================================
# PDF Generation
# ================================================================
def generate_study_guide_pdf(study_plan: dict, course_name: str, assignments: list = None) -> bytes:
    """
    Generate a styled PDF study guide from study plan data.

    Args:
        study_plan: Dict with overview, weekly_schedule, study_tips, resource_recommendations
        course_name: Name of the course
        assignments: Optional list of assignment dicts with title, due_date, type

    Returns:
        PDF file as bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=60,
        leftMargin=60,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'GuideTitle',
        parent=styles['Title'],
        fontSize=26,
        textColor=HexColor('#1a102e'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    subtitle_style = ParagraphStyle(
        'GuideSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=HexColor('#5f5c74'),
        alignment=TA_CENTER,
        spaceAfter=20,
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=HexColor('#3d2b7a'),
        spaceBefore=18,
        spaceAfter=8,
        fontName='Helvetica-Bold',
    )

    body_style = ParagraphStyle(
        'GuideBody',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor('#333333'),
        leading=16,
        spaceAfter=6,
    )

    tip_style = ParagraphStyle(
        'GuideTip',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor('#333333'),
        leading=16,
        leftIndent=20,
        spaceAfter=4,
    )

    week_title_style = ParagraphStyle(
        'WeekTitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=HexColor('#ff5ae0'),
        fontName='Helvetica-Bold',
        spaceAfter=4,
    )

    elements = []

    # --- Title ---
    elements.append(Paragraph(f"Study Guide", title_style))
    elements.append(Paragraph(f"{course_name}", subtitle_style))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y')}",
        ParagraphStyle('DateLine', parent=subtitle_style, fontSize=10, spaceAfter=10)
    ))
    elements.append(HRFlowable(
        width="100%", thickness=2,
        color=HexColor('#ff5ae0'), spaceAfter=16
    ))

    # --- Assignments Table ---
    if assignments and len(assignments) > 0:
        elements.append(Paragraph("Upcoming Assignments & Deadlines", section_heading))
        table_data = [['Title', 'Due Date', 'Type']]
        for a in assignments:
            table_data.append([
                a.get('title', 'Untitled'),
                a.get('due_date', 'TBD'),
                a.get('type', 'assignment').capitalize()
            ])

        col_widths = [3.4 * inch, 1.5 * inch, 1.3 * inch]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3d2b7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#faf9ff')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#faf9ff'), HexColor('#f0eeff')]),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#d0cce6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 16))

    # --- Overview ---
    if study_plan.get('overview'):
        elements.append(Paragraph("Overview", section_heading))
        elements.append(Paragraph(study_plan['overview'], body_style))
        elements.append(Spacer(1, 8))

    # --- Weekly Schedule ---
    if study_plan.get('weekly_schedule') and isinstance(study_plan['weekly_schedule'], list):
        elements.append(Paragraph("Weekly Schedule", section_heading))
        for i, week in enumerate(study_plan['weekly_schedule']):
            elements.append(Paragraph(f"Week {i + 1}", week_title_style))
            elements.append(Paragraph(week, body_style))
            elements.append(Spacer(1, 6))

    # --- Study Tips ---
    if study_plan.get('study_tips') and isinstance(study_plan['study_tips'], list):
        elements.append(Paragraph("Study Tips", section_heading))
        tip_items = []
        for tip in study_plan['study_tips']:
            tip_items.append(ListItem(Paragraph(tip, tip_style), bulletColor=HexColor('#ff5ae0')))
        elements.append(ListFlowable(tip_items, bulletType='bullet', start=''))
        elements.append(Spacer(1, 8))

    # --- Resource Recommendations ---
    if study_plan.get('resource_recommendations'):
        elements.append(Paragraph("Resource Recommendations", section_heading))
        elements.append(Paragraph(study_plan['resource_recommendations'], body_style))

    # --- Footer ---
    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(
        width="100%", thickness=1,
        color=HexColor('#d0cce6'), spaceAfter=8
    ))
    elements.append(Paragraph(
        "Generated by CourseTrack — Your AI-powered academic companion",
        ParagraphStyle('Footer', parent=subtitle_style, fontSize=9, textColor=HexColor('#999999'))
    ))

    doc.build(elements)
    return buffer.getvalue()


# ================================================================
# DOCX Generation
# ================================================================
def generate_study_guide_docx(study_plan: dict, course_name: str, assignments: list = None) -> bytes:
    """
    Generate a styled DOCX study guide from study plan data.

    Args:
        study_plan: Dict with overview, weekly_schedule, study_tips, resource_recommendations
        course_name: Name of the course
        assignments: Optional list of assignment dicts with title, due_date, type

    Returns:
        DOCX file as bytes
    """
    doc = Document()

    # --- Styles ---
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # --- Title ---
    title = doc.add_heading('Study Guide', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1a, 0x10, 0x2e)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(course_name)
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)
    run.bold = True

    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date_para.add_run(f"Generated on {datetime.now().strftime('%B %d, %Y')}")
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x5f, 0x5c, 0x74)

    doc.add_paragraph('')  # spacer

    # --- Assignments Table ---
    if assignments and len(assignments) > 0:
        heading = doc.add_heading('Upcoming Assignments & Deadlines', level=1)
        for run in heading.runs:
            run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)

        table = doc.add_table(rows=1, cols=3)
        table.style = 'Light Grid Accent 1'
        table.autofit = True

        # Header
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Title'
        hdr_cells[1].text = 'Due Date'
        hdr_cells[2].text = 'Type'

        for cell in hdr_cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        for a in assignments:
            row_cells = table.add_row().cells
            row_cells[0].text = a.get('title', 'Untitled')
            row_cells[1].text = a.get('due_date', 'TBD')
            row_cells[2].text = a.get('type', 'assignment').capitalize()

        doc.add_paragraph('')  # spacer

    # --- Overview ---
    if study_plan.get('overview'):
        heading = doc.add_heading('Overview', level=1)
        for run in heading.runs:
            run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)
        doc.add_paragraph(study_plan['overview'])

    # --- Weekly Schedule ---
    if study_plan.get('weekly_schedule') and isinstance(study_plan['weekly_schedule'], list):
        heading = doc.add_heading('Weekly Schedule', level=1)
        for run in heading.runs:
            run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)

        for i, week in enumerate(study_plan['weekly_schedule']):
            week_heading = doc.add_heading(f'Week {i + 1}', level=2)
            for run in week_heading.runs:
                run.font.color.rgb = RGBColor(0xff, 0x5a, 0xe0)
            doc.add_paragraph(week)

    # --- Study Tips ---
    if study_plan.get('study_tips') and isinstance(study_plan['study_tips'], list):
        heading = doc.add_heading('Study Tips', level=1)
        for run in heading.runs:
            run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)

        for tip in study_plan['study_tips']:
            para = doc.add_paragraph(style='List Bullet')
            para.add_run(tip)

    # --- Resource Recommendations ---
    if study_plan.get('resource_recommendations'):
        heading = doc.add_heading('Resource Recommendations', level=1)
        for run in heading.runs:
            run.font.color.rgb = RGBColor(0x3d, 0x2b, 0x7a)
        doc.add_paragraph(study_plan['resource_recommendations'])

    # --- Footer ---
    doc.add_paragraph('')
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run('Generated by CourseTrack — Your AI-powered academic companion')
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.italic = True

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

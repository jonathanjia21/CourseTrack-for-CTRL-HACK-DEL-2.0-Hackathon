"""
Generate downloadable study guides in PDF format from study plan data.
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
from reportlab.lib.enums import TA_CENTER


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



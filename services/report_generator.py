from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DISCLAIMER = (
    "This score is an estimate produced by this application's documented rules. "
    "It is not an official score from a commercial Applicant Tracking System (ATS), "
    "and it does not predict a hiring decision."
)


def _paragraph(text, style):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def generate_pdf_report(report, resume, job_description):
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title="Resume ATS Analysis Report",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#183b56")))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], textColor=colors.HexColor("#183b56"), spaceBefore=10, spaceAfter=5))

    content = [
        _paragraph("Resume ATS Analysis Report", styles["ReportTitle"]),
        Spacer(1, 5 * mm),
        _paragraph(f"Analysis date: {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}", styles["BodyText"]),
        _paragraph(f"Job title: {job_description.job_title or 'Not provided'}", styles["BodyText"]),
        _paragraph(f"Company: {job_description.company_name or 'Not provided'}", styles["BodyText"]),
        _paragraph(f"Resume file: {resume.file_name}", styles["BodyText"]),
        _paragraph(f"ATS compatibility estimate: {report.ats_score}/100", styles["Heading1"]),
        _paragraph("Score breakdown", styles["SectionTitle"]),
    ]

    data = [["Component", "Weight", "Raw score", "Contribution"]]
    for item in report.get_list("score_breakdown"):
        data.append([
            item["name"],
            f'{item["weight"]}%',
            f'{item["raw_score"]}/100',
            f'{item["weighted_contribution"]} points',
        ])
    table = Table(data, colWidths=[72 * mm, 20 * mm, 32 * mm, 42 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183b56")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    content.append(table)

    sections = [
        ("Matched skills", report.get_list("matched_skills")),
        ("Missing skills", report.get_list("missing_skills")),
        ("Important matched keywords", report.get_list("matched_keywords")),
        ("Important missing keywords", report.get_list("missing_keywords")),
        ("Improvement suggestions", report.get_list("suggestions")),
    ]
    for title, items in sections:
        content.append(_paragraph(title, styles["SectionTitle"]))
        if items:
            content.extend(_paragraph(f"• {item}", styles["BodyText"]) for item in items)
        else:
            content.append(_paragraph("None identified.", styles["BodyText"]))
    content.extend([
        _paragraph("Analysis method", styles["SectionTitle"]),
        _paragraph(report.analysis_method, styles["BodyText"]),
        _paragraph(report.score_formula, styles["BodyText"]),
        _paragraph("Limitations", styles["SectionTitle"]),
        _paragraph(DISCLAIMER, styles["BodyText"]),
    ])
    document.build(content)
    output.seek(0)
    return output

import json
import logging
import math
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import (
    AnalysisReport, JobDescription, Resume, ResumeDraft, ResumeDraftVersion,
    UserProfile, db, utc_now,
)
from services.analyzer import analyze_resume, serialize_list
from services.product import PROFILE_GUIDANCE, RESUME_FIELDS, TEMPLATE_CATALOG, template_by_id
from services.report_generator import generate_pdf_report
from services.resume_export import generate_resume_export
from services.resume_parser import ALLOWED_EXTENSIONS, ResumeParseError, parse_resume


main_bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)
MAX_JOB_DESCRIPTION_LENGTH = 20000
MAX_RESUME_BYTES = 5 * 1024 * 1024
PROFILE_CATEGORIES = tuple(PROFILE_GUIDANCE)
PREMIUM_SCAN_SECONDS = 120


def _profile_for_current_user():
    profile = UserProfile.query.filter_by(user_id=current_user.user_id).first()
    if profile is None:
        profile = UserProfile(user_id=current_user.user_id)
        db.session.add(profile)
        db.session.commit()
    return profile


def _as_utc(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _premium_active(profile):
    expiry = _as_utc(profile.subscription_expires_at)
    return profile.plan == "premium" and expiry is not None and expiry > utc_now()


def _scanner_seconds_remaining(profile):
    expiry = _as_utc(profile.scanner_expires_at)
    if expiry is None:
        return 0
    return max(0, math.ceil((expiry - utc_now()).total_seconds()))


def _draft_for_current_user(draft_id):
    draft = ResumeDraft.query.filter_by(draft_id=draft_id, user_id=current_user.user_id).first()
    if draft is None:
        abort(404)
    return draft


def _draft_access_allowed(draft):
    template = template_by_id(draft.template_id)
    if template is None:
        abort(404)
    if template["tier"] == "premium" and not _premium_active(_profile_for_current_user()):
        flash("This resume uses a Premium template. Renew or upgrade your plan to continue.", "info")
        return False
    return True


def _report_for_current_user(report_id):
    report = AnalysisReport.query.filter_by(
        report_id=report_id, user_id=current_user.user_id
    ).first()
    if report is None:
        abort(404)
    return report


def _decode_report(report):
    return {
        field: json.loads(getattr(report, field))
        for field in (
        "score_breakdown", "matched_skills", "missing_skills",
        "matched_keywords", "missing_keywords", "structure_checks", "suggestions",
        "readability_checks",
        )
    }


@main_bp.get("/")
def home():
    return render_template("home.html")


@main_bp.get("/dashboard")
@login_required
def dashboard():
    recent_reports = (
        AnalysisReport.query.filter_by(user_id=current_user.user_id)
        .order_by(AnalysisReport.created_at.desc()).limit(5).all()
    )
    profile = _profile_for_current_user()
    average_score = db.session.query(func.avg(AnalysisReport.ats_score)).filter_by(
        user_id=current_user.user_id
    ).scalar()
    scan_count = AnalysisReport.query.filter_by(user_id=current_user.user_id).count()
    resumes = (
        ResumeDraft.query.filter_by(user_id=current_user.user_id)
        .order_by(ResumeDraft.updated_at.desc()).limit(5).all()
    )
    return render_template(
        "dashboard.html", recent_reports=recent_reports, scan_count=scan_count, profile=profile,
        average_score=round(average_score) if average_score is not None else None,
        saved_resumes=resumes,
        premium_active=_premium_active(profile),
        scanner_seconds=_scanner_seconds_remaining(profile),
        guidance=PROFILE_GUIDANCE.get(profile.category, PROFILE_GUIDANCE["Other Professional"]),
    )


@main_bp.post("/analyze")
@login_required
def analyze():
    uploaded_file = request.files.get("resume")
    job_title = request.form.get("job_title", "").strip()
    company_name = request.form.get("company_name", "").strip()
    job_description = request.form.get("job_description", "").strip()

    if uploaded_file is None or not uploaded_file.filename:
        flash("Choose a PDF or DOCX resume to continue.", "error")
        return redirect(url_for("main.dashboard"))
    safe_display_name = secure_filename(uploaded_file.filename)
    extension = Path(safe_display_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        flash("Only PDF and DOCX resumes are supported.", "error")
        return redirect(url_for("main.dashboard"))
    uploaded_file.stream.seek(0)
    if len(uploaded_file.stream.read(MAX_RESUME_BYTES + 1)) > MAX_RESUME_BYTES:
        flash("The resume is too large. Please choose a file no larger than 5 MB.", "error")
        return redirect(url_for("main.dashboard"))
    uploaded_file.stream.seek(0)
    if len(job_title) > 150 or len(company_name) > 150:
        flash("Job title and company name must each be 150 characters or fewer.", "error")
        return redirect(url_for("main.dashboard"))
    if len(job_description) > MAX_JOB_DESCRIPTION_LENGTH:
        flash("The job description is too long (maximum 20,000 characters).", "error")
        return redirect(url_for("main.dashboard"))
    if len(job_description) < 30:
        flash("Enter a job description with at least 30 characters.", "error")
        return redirect(url_for("main.dashboard"))

    user_folder = Path(current_app.config["UPLOAD_FOLDER"]) / str(current_user.user_id)
    user_folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    user_folder.chmod(0o700)
    internal_filename = f"{uuid.uuid4().hex}{extension}"
    stored_path = user_folder / internal_filename

    try:
        uploaded_file.save(stored_path)
        os_chmod_private(stored_path)
        extracted_text = parse_resume(stored_path)
    except ResumeParseError as error:
        stored_path.unlink(missing_ok=True)
        flash(str(error), "error")
        return redirect(url_for("main.dashboard"))
    except OSError:
        stored_path.unlink(missing_ok=True)
        logger.exception("Could not store uploaded resume for user_id=%s", current_user.user_id)
        flash("We could not safely store that file. Please try again.", "error")
        return redirect(url_for("main.dashboard"))

    result = analyze_resume(extracted_text, job_description)
    resume = Resume(
        user_id=current_user.user_id,
        file_name=(safe_display_name or f"resume{extension}")[:255],
        internal_filename=internal_filename,
        extracted_text=extracted_text,
    )
    job = JobDescription(
        user_id=current_user.user_id,
        job_title=job_title or None,
        company_name=company_name or None,
        description_text=job_description,
    )
    report = AnalysisReport(
        user_id=current_user.user_id,
        ats_score=result["ats_score"],
        score_breakdown=serialize_list(result["score_breakdown"]),
        matched_skills=serialize_list(result["matched_skills"]),
        missing_skills=serialize_list(result["missing_skills"]),
        matched_keywords=serialize_list(result["matched_keywords"]),
        missing_keywords=serialize_list(result["missing_keywords"]),
        structure_checks=serialize_list(result["structure_checks"]),
        readability_checks=serialize_list(result["readability_checks"]),
        suggestions=serialize_list(result["suggestions"]),
        analysis_method=result["analysis_method"],
        score_formula=result["score_formula"],
    )
    report.resume = resume
    report.job_description = job
    db.session.add(report)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        stored_path.unlink(missing_ok=True)
        logger.exception("Could not save resume analysis for user_id=%s", current_user.user_id)
        flash("We could not save this analysis. Please try again.", "error")
        return redirect(url_for("main.dashboard"))

    return redirect(url_for("main.report_detail", report_id=report.report_id))


@main_bp.get("/templates")
@login_required
def templates():
    profile = _profile_for_current_user()
    return render_template(
        "templates.html", templates=TEMPLATE_CATALOG, profile=profile,
        premium_active=_premium_active(profile),
        guidance=PROFILE_GUIDANCE.get(profile.category, PROFILE_GUIDANCE["Other Professional"]),
    )


@main_bp.get("/templates/<template_id>/select")
@login_required
def select_template(template_id):
    template = template_by_id(template_id)
    if template is None:
        abort(404)
    profile = _profile_for_current_user()
    if template["tier"] == "premium" and not _premium_active(profile):
        flash("Premium access is required for this template. Explore the plans to unlock it.", "info")
        return redirect(url_for("main.pricing"))

    data = {field: "" for field in RESUME_FIELDS}
    data.update({"full_name": current_user.name, "email": current_user.email})
    draft = ResumeDraft(
        user_id=current_user.user_id,
        template_id=template_id,
        title=f"{current_user.name}'s resume",
        data=json.dumps(data, ensure_ascii=False),
        version=1,
    )
    db.session.add(draft)
    db.session.flush()
    db.session.add(ResumeDraftVersion(
        draft_id=draft.draft_id, user_id=current_user.user_id,
        version=1, data=draft.data,
    ))
    db.session.commit()
    return redirect(url_for("main.resume_builder", draft_id=draft.draft_id))


@main_bp.get("/pricing")
def pricing():
    profile = _profile_for_current_user() if current_user.is_authenticated else None
    return render_template(
        "pricing.html", profile=profile,
        premium_active=_premium_active(profile) if profile else False,
    )


@main_bp.post("/pricing/demo-upgrade")
@login_required
def demo_upgrade():
    profile = _profile_for_current_user()
    profile.plan = "premium"
    profile.subscription_expires_at = utc_now() + timedelta(days=30)
    db.session.commit()
    flash("Demo Premium is active for 30 days. No payment was collected.", "success")
    return redirect(url_for("main.pricing"))


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile_settings():
    profile = _profile_for_current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        if not name or len(name) > 100:
            flash("Enter a name up to 100 characters.", "error")
        elif category not in PROFILE_CATEGORIES:
            flash("Select one of the listed profile categories.", "error")
        else:
            current_user.name = name
            profile.category = category
            db.session.commit()
            flash("Your profile was updated.", "success")
            return redirect(url_for("main.profile_settings"))
    return render_template(
        "profile.html", profile=profile, categories=PROFILE_CATEGORIES,
        premium_active=_premium_active(profile),
    )


@main_bp.get("/builder/<int:draft_id>")
@login_required
def resume_builder(draft_id):
    draft = _draft_for_current_user(draft_id)
    if not _draft_access_allowed(draft):
        return redirect(url_for("main.pricing"))
    template = template_by_id(draft.template_id)
    return render_template(
        "builder.html", draft=draft, resume_data=json.loads(draft.data),
        fields=RESUME_FIELDS, template=template,
    )


@main_bp.post("/builder/<int:draft_id>")
@login_required
def save_resume_draft(draft_id):
    draft = _draft_for_current_user(draft_id)
    if not _draft_access_allowed(draft):
        return redirect(url_for("main.pricing"))
    title = request.form.get("title", "").strip()
    data = {}
    errors = []
    if not title or len(title) > 120:
        errors.append("Enter a resume title up to 120 characters.")
    for field, (label, limit) in RESUME_FIELDS.items():
        value = request.form.get(field, "").strip()
        if len(value) > limit:
            errors.append(f"{label} must be {limit} characters or fewer.")
        data[field] = value
    if not data["full_name"]:
        errors.append("Your name is required.")
    if len(json.dumps(data, ensure_ascii=False)) > 35000:
        errors.append("The resume content is too long to save.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("main.resume_builder", draft_id=draft_id))

    serialized = json.dumps(data, ensure_ascii=False)
    if serialized != draft.data:
        draft.version += 1
        draft.data = serialized
        db.session.add(ResumeDraftVersion(
            draft_id=draft.draft_id, user_id=current_user.user_id,
            version=draft.version, data=serialized,
        ))
    draft.title = title
    db.session.commit()
    flash("Resume saved. A new version is available in your history.", "success")
    return redirect(url_for("main.resume_builder", draft_id=draft_id))


@main_bp.get("/builder/<int:draft_id>/export/<file_format>")
@login_required
def export_resume(draft_id, file_format):
    draft = _draft_for_current_user(draft_id)
    if not _draft_access_allowed(draft):
        return redirect(url_for("main.pricing"))
    if file_format not in {"pdf", "docx"}:
        abort(404)
    template = template_by_id(draft.template_id)
    if template is None:
        abort(404)
    output = generate_resume_export(json.loads(draft.data), template, file_format)
    return send_file(
        output,
        mimetype="application/pdf" if file_format == "pdf" else
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"{secure_filename(draft.title) or 'resume'}.{file_format}",
    )


@main_bp.get("/premium-scanner")
@login_required
def premium_scanner():
    profile = _profile_for_current_user()
    if not _premium_active(profile):
        flash("The premium scanner requires an active Premium plan.", "info")
        return redirect(url_for("main.pricing"))
    return render_template(
        "premium_scanner.html", profile=profile,
        scanner_seconds=_scanner_seconds_remaining(profile),
        premium_active=True,
    )


@main_bp.post("/premium-scanner/start")
@login_required
def start_premium_scanner():
    profile = _profile_for_current_user()
    if not _premium_active(profile):
        flash("The premium scanner requires an active Premium plan.", "error")
        return redirect(url_for("main.pricing"))
    if _scanner_seconds_remaining(profile) <= 0:
        profile.scanner_expires_at = utc_now() + timedelta(seconds=PREMIUM_SCAN_SECONDS)
        db.session.commit()
        flash("Your two-minute scanner session has started.", "success")
    else:
        flash("Your current scanner session is still active.", "info")
    return redirect(url_for("main.premium_scanner"))


@main_bp.post("/premium-scanner/analyze")
@login_required
def analyze_premium_session():
    profile = _profile_for_current_user()
    if not _premium_active(profile):
        flash("The premium scanner requires an active Premium plan.", "error")
        return redirect(url_for("main.pricing"))
    if _scanner_seconds_remaining(profile) <= 0:
        flash("Your scanner session has expired. Start a new session to scan again.", "error")
        return redirect(url_for("main.premium_scanner"))
    return analyze()


@main_bp.get("/builder/<int:draft_id>/versions")
@login_required
def resume_versions(draft_id):
    draft = _draft_for_current_user(draft_id)
    if not _draft_access_allowed(draft):
        return redirect(url_for("main.pricing"))
    versions = (
        ResumeDraftVersion.query.filter_by(draft_id=draft_id, user_id=current_user.user_id)
        .order_by(ResumeDraftVersion.version.desc()).all()
    )
    return render_template("resume_versions.html", draft=draft, versions=versions)


def os_chmod_private(path):
    path.chmod(0o600)


@main_bp.get("/history")
@login_required
def history():
    reports = (
        AnalysisReport.query.filter_by(user_id=current_user.user_id)
        .order_by(AnalysisReport.created_at.desc()).all()
    )
    return render_template("history.html", reports=reports)


@main_bp.get("/reports/<int:report_id>")
@login_required
def report_detail(report_id):
    report = _report_for_current_user(report_id)
    return render_template("results.html", report=report, report_data=_decode_report(report))


@main_bp.get("/reports/<int:report_id>/download")
@login_required
def download_report(report_id):
    report = _report_for_current_user(report_id)
    pdf = generate_pdf_report(report, report.resume, report.job_description)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"resume-analysis-{report.report_id}.pdf",
    )


@main_bp.post("/reports/<int:report_id>/delete")
@login_required
def delete_report(report_id):
    report = _report_for_current_user(report_id)
    resume = report.resume
    job = report.job_description
    upload_path = Path(current_app.config["UPLOAD_FOLDER"]) / str(current_user.user_id) / resume.internal_filename
    db.session.delete(report)
    db.session.flush()
    if AnalysisReport.query.filter_by(resume_id=resume.resume_id).count() == 0:
        db.session.delete(resume)
    if AnalysisReport.query.filter_by(jd_id=job.jd_id).count() == 0:
        db.session.delete(job)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Could not delete report_id=%s for user_id=%s", report_id, current_user.user_id)
        flash("We could not delete this report. Please try again.", "error")
        return redirect(url_for("main.history"))
    try:
        upload_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove private upload for deleted report_id=%s", report_id)
    flash("Analysis report deleted.", "success")
    return redirect(url_for("main.history"))

import hashlib
import hmac
import json
import logging
import math
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import (
    AnalysisReport, JobDescription, Resume, ResumeDraft, ResumeDraftVersion,
    UserProfile, db, utc_now,
)
from services.ai_assistant import build_ai_response, build_resume_context, provider_ready
from services.analyzer import analyze_resume, serialize_list
from services.product import (
    PRICING_PLANS,
    PROFILE_GUIDANCE,
    RESUME_FIELDS,
    TEMPLATE_CATALOG,
    template_by_id,
)
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


def _plan_active(profile, plan_name=None):
    if profile is None:
        return False
    expiry = _as_utc(profile.subscription_expires_at)
    if plan_name is None:
        plan_name = profile.plan
    if plan_name not in {"pro", "premium"}:
        return False
    return profile.plan == plan_name and expiry is not None and expiry > utc_now()


def _premium_active(profile):
    return _plan_active(profile, "premium")


def _pro_active(profile):
    return _plan_active(profile, "pro")


def _scanner_seconds_remaining(profile):
    expiry = _as_utc(profile.scanner_expires_at)
    if expiry is None:
        return 0
    return max(0, math.ceil((expiry - utc_now()).total_seconds()))


def _plan_details(plan_id):
    for plan in PRICING_PLANS:
        if plan["id"] == plan_id:
            return plan
    return None


def _razorpay_enabled():
    return bool(
        current_app.config.get("RAZORPAY_KEY_ID") and
        current_app.config.get("RAZORPAY_KEY_SECRET")
    )


def _razorpay_client():
    if not _razorpay_enabled():
        return None
    try:
        import razorpay
    except ImportError:
        return None
    return razorpay.Client(auth=(current_app.config["RAZORPAY_KEY_ID"], current_app.config["RAZORPAY_KEY_SECRET"]))


def _verify_razorpay_signature(order_id, payment_id, signature):
    if not _razorpay_enabled():
        return False
    secret = current_app.config.get("RAZORPAY_KEY_SECRET")
    generated = hmac.new(secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(generated, signature)


def _checkout_session_data():
    payload = session.get("checkout_data")
    if not payload:
        return {}
    return payload


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


@main_bp.route("/ai-assistant", methods=["GET", "POST"])
@main_bp.route("/resume-assistant", methods=["GET", "POST"])
@login_required
def ai_assistant():
    profile = _profile_for_current_user()
    latest_report = (
        AnalysisReport.query.filter_by(user_id=current_user.user_id)
        .order_by(AnalysisReport.created_at.desc()).first()
    )
    draft = (
        ResumeDraft.query.filter_by(user_id=current_user.user_id)
        .order_by(ResumeDraft.updated_at.desc()).first()
    )
    draft_data = json.loads(draft.data) if draft else {}
    report_data = {
        "job_title": latest_report.job_description.job_title,
        "company_name": latest_report.job_description.company_name,
        "job_description": latest_report.job_description.description_text,
        "resume_text": latest_report.resume.extracted_text,
    } if latest_report else {}
    result = None
    prompt = ""
    if request.method == "POST":
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            flash("Tell the AI assistant what you want to improve or rewrite.", "error")
            return redirect(url_for("main.ai_assistant"))
        context = build_resume_context(draft_data=draft_data, report_data=report_data)
        result = build_ai_response(prompt, context=context)
    return render_template(
        "ai_assistant.html",
        profile=profile,
        premium_active=_premium_active(profile),
        provider_ready=provider_ready(),
        latest_report=latest_report,
        draft=draft,
        result=result,
        prompt=prompt,
    )


@main_bp.route("/ai-analyzer", methods=["GET", "POST"])
@main_bp.route("/resume-analyzer", methods=["GET", "POST"])
@login_required
def ai_analyzer():
    profile = _profile_for_current_user()
    latest_report = (
        AnalysisReport.query.filter_by(user_id=current_user.user_id)
        .order_by(AnalysisReport.created_at.desc()).first()
    )
    prompt = ""
    result = None
    if request.method == "POST":
        prompt = request.form.get("prompt", "").strip()
        if not prompt:
            flash("Share the role or section you want the AI analyzer to review.", "error")
            return redirect(url_for("main.ai_analyzer"))
        context = build_resume_context(
            draft_data=(json.loads(ResumeDraft.query.filter_by(user_id=current_user.user_id).order_by(ResumeDraft.updated_at.desc()).first().data) if ResumeDraft.query.filter_by(user_id=current_user.user_id).order_by(ResumeDraft.updated_at.desc()).first() else {}),
            report_data={
                "job_title": latest_report.job_description.job_title if latest_report else "",
                "company_name": latest_report.job_description.company_name if latest_report else "",
                "job_description": latest_report.job_description.description_text if latest_report else "",
                "resume_text": latest_report.resume.extracted_text if latest_report else "",
            },
        )
        result = build_ai_response(prompt, context=context)
    return render_template(
        "ai_analyzer.html",
        profile=profile,
        premium_active=_premium_active(profile),
        provider_ready=provider_ready(),
        latest_report=latest_report,
        result=result,
        prompt=prompt,
    )


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
    current_plan = profile.plan if profile else "free"
    return render_template(
        "pricing.html",
        profile=profile,
        pricing_plans=PRICING_PLANS,
        premium_active=_premium_active(profile) if profile else False,
        pro_active=_pro_active(profile) if profile else False,
        current_plan=current_plan,
        payment_ready=_razorpay_enabled(),
    )


@main_bp.get("/pricing/checkout/<plan_id>")
@login_required
def checkout_plan(plan_id):
    plan = _plan_details(plan_id)
    if plan is None:
        flash("Select a valid plan to continue.", "error")
        return redirect(url_for("main.pricing"))
    if plan["id"] == "free":
        profile = _profile_for_current_user()
        profile.plan = "free"
        profile.subscription_expires_at = None
        profile.subscription_started_at = None
        profile.payment_provider = "none"
        profile.payment_status = "inactive"
        profile.payment_reference = None
        profile.payment_order_id = None
        db.session.commit()
        flash("Free Lifetime plan is active. You can continue using the free features without renewal.", "success")
        return redirect(url_for("main.pricing"))

    session["checkout_data"] = {
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "amount": int(plan["price"] * 100),
        "currency": "INR",
        "customer_name": current_user.name,
        "customer_email": current_user.email,
    }
    return render_template(
        "subscription_checkout.html",
        plan=plan,
        profile=_profile_for_current_user(),
        payment_ready=_razorpay_enabled(),
    )


@main_bp.post("/pricing/checkout/<plan_id>")
@login_required
def checkout_plan_submit(plan_id):
    plan = _plan_details(plan_id)
    if plan is None:
        flash("Select a valid plan to continue.", "error")
        return redirect(url_for("main.pricing"))
    if plan["id"] == "free":
        profile = _profile_for_current_user()
        profile.plan = "free"
        profile.subscription_expires_at = None
        profile.subscription_started_at = None
        profile.payment_provider = "none"
        profile.payment_status = "inactive"
        profile.payment_reference = None
        profile.payment_order_id = None
        db.session.commit()
        flash("Free Lifetime plan is active. You can continue using the free features without renewal.", "success")
        return redirect(url_for("main.pricing"))

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    if not full_name:
        flash("Enter your full name for billing.", "error")
        return redirect(url_for("main.checkout_plan", plan_id=plan_id))
    if not email:
        email = current_user.email
    try:
        from email_validator import EmailNotValidError, validate_email
        normalized_email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        flash("Enter a valid email address for billing.", "error")
        return redirect(url_for("main.checkout_plan", plan_id=plan_id))

    payload = {
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "amount": int(plan["price"] * 100),
        "currency": "INR",
        "customer_name": full_name or current_user.name,
        "customer_email": normalized_email,
    }
    session["checkout_data"] = payload
    if not _razorpay_enabled():
        flash("Razorpay is not configured in this deployment yet. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to enable hosted checkout in test or live mode.", "info")
        return render_template(
            "payment_checkout.html",
            plan=plan,
            profile=_profile_for_current_user(),
            payment_ready=False,
            checkout_data=payload,
            provider_name="Razorpay",
        )

    client = _razorpay_client()
    if client is None:
        flash("Razorpay checkout is unavailable right now. Please contact support or configure the provider keys first.", "info")
        return redirect(url_for("main.checkout_plan", plan_id=plan_id))

    order = client.order.create({
        "amount": payload["amount"],
        "currency": payload["currency"],
        "receipt": f"resume-lens-{current_user.user_id}-{plan['id']}",
        "payment_capture": 1,
        "notes": {
            "customer_name": payload["customer_name"],
            "customer_email": payload["customer_email"],
            "plan_id": payload["plan_id"],
        },
    })
    payload["order_id"] = order["id"]
    session["checkout_data"] = payload
    return render_template(
        "payment_checkout.html",
        plan=plan,
        profile=_profile_for_current_user(),
        payment_ready=True,
        checkout_data=payload,
        provider_name="Razorpay",
        key_id=current_app.config["RAZORPAY_KEY_ID"],
    )


@main_bp.post("/pricing/verify")
@login_required
def verify_payment():
    payload = _checkout_session_data()
    payment_id = request.form.get("payment_id", "").strip()
    order_id = request.form.get("order_id", "").strip()
    signature = request.form.get("signature", "").strip()
    plan_id = request.form.get("plan_id", payload.get("plan_id", "")).strip()
    plan = _plan_details(plan_id)
    if not plan or plan["id"] == "free":
        flash("A valid paid plan is required to complete the checkout.", "error")
        return redirect(url_for("main.pricing"))
    if not payment_id or not order_id or not signature:
        flash("The payment response was incomplete. No payment was activated.", "error")
        return redirect(url_for("main.pricing"))
    if not _verify_razorpay_signature(order_id, payment_id, signature):
        flash("Payment verification failed. We did not activate your subscription.", "error")
        return redirect(url_for("main.pricing"))

    profile = _profile_for_current_user()
    now = utc_now()
    profile.plan = plan_id
    profile.payment_provider = "razorpay"
    profile.payment_status = "paid"
    profile.payment_reference = payment_id
    profile.payment_order_id = order_id
    profile.subscription_started_at = now
    profile.subscription_expires_at = now + timedelta(days=30 if plan_id == "pro" else 365)
    db.session.commit()
    session.pop("checkout_data", None)
    flash("Payment verified successfully. Your subscription has been activated.", "success")
    return redirect(url_for("main.subscription_success"))


@main_bp.get("/billing/success")
@login_required
def subscription_success():
    profile = _profile_for_current_user()
    return render_template(
        "subscription_success.html",
        profile=profile,
        premium_active=_premium_active(profile),
        pro_active=_pro_active(profile),
        current_plan=profile.plan,
    )


@main_bp.get("/billing/manage")
@login_required
def subscription_manage():
    profile = _profile_for_current_user()
    return render_template(
        "billing_manage.html",
        profile=profile,
        premium_active=_premium_active(profile),
        pro_active=_pro_active(profile),
        current_plan=profile.plan,
        payment_ready=_razorpay_enabled(),
    )


@main_bp.post("/pricing/demo-upgrade")
@login_required
def demo_upgrade():
    profile = _profile_for_current_user()
    selected_plan = request.form.get("plan", "premium").lower()
    if selected_plan not in {"free", "pro", "premium"}:
        selected_plan = "premium"
    profile.plan = selected_plan
    profile.payment_provider = "demo"
    profile.payment_status = "demo"
    profile.payment_reference = "demo-upgrade"
    profile.payment_order_id = None
    if selected_plan == "free":
        profile.subscription_expires_at = None
        profile.subscription_started_at = None
        flash("Free Lifetime plan is active. You can continue using the free features without a renewal.", "success")
    elif selected_plan == "pro":
        profile.subscription_started_at = utc_now()
        profile.subscription_expires_at = utc_now() + timedelta(days=30)
        flash("Pro Monthly is active for 30 days. This is a demo subscription flow, not a live payment checkout.", "success")
    else:
        profile.subscription_started_at = utc_now()
        profile.subscription_expires_at = utc_now() + timedelta(days=365)
        flash("Premium Yearly is active for one year. This is a demo subscription flow, not a live payment checkout.", "success")
    db.session.commit()
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
        "premium_scanner.html",
        profile=profile,
        scanner_seconds=_scanner_seconds_remaining(profile),
        premium_active=True,
        pricing_plans=PRICING_PLANS,
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

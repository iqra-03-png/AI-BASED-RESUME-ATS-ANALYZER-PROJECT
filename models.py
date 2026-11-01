from datetime import datetime, timezone
import json

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user", server_default="user")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    reports = db.relationship("AnalysisReport", back_populates="user", cascade="all, delete-orphan")
    profile = db.relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def get_id(self):
        return str(self.user_id)

    @property
    def is_admin(self):
        return self.role == "admin"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Resume(db.Model):
    __tablename__ = "resumes"

    resume_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    internal_filename = db.Column(db.String(100), nullable=False)
    extracted_text = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    reports = db.relationship("AnalysisReport", back_populates="resume")


class JobDescription(db.Model):
    __tablename__ = "job_descriptions"

    jd_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    job_title = db.Column(db.String(150), nullable=True)
    company_name = db.Column(db.String(150), nullable=True)
    description_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    reports = db.relationship("AnalysisReport", back_populates="job_description")


class AnalysisReport(db.Model):
    __tablename__ = "analysis_reports"

    report_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.resume_id"), nullable=False)
    jd_id = db.Column(db.Integer, db.ForeignKey("job_descriptions.jd_id"), nullable=False)
    ats_score = db.Column(db.Integer, nullable=False)
    score_breakdown = db.Column(db.Text, nullable=False)
    matched_skills = db.Column(db.Text, nullable=False)
    missing_skills = db.Column(db.Text, nullable=False)
    matched_keywords = db.Column(db.Text, nullable=False)
    missing_keywords = db.Column(db.Text, nullable=False)
    structure_checks = db.Column(db.Text, nullable=False)
    readability_checks = db.Column(db.Text, nullable=False)
    suggestions = db.Column(db.Text, nullable=False)
    analysis_method = db.Column(db.String(100), nullable=False)
    score_formula = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = db.relationship("User", back_populates="reports")
    resume = db.relationship("Resume", back_populates="reports")
    job_description = db.relationship("JobDescription", back_populates="reports")

    def get_list(self, field_name):
        return json.loads(getattr(self, field_name))


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    profile_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, unique=True, index=True)
    category = db.Column(db.String(80), nullable=False, default="Other Professional")
    plan = db.Column(db.String(20), nullable=False, default="free")
    subscription_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    subscription_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    payment_provider = db.Column(db.String(30), nullable=False, default="none")
    payment_status = db.Column(db.String(30), nullable=False, default="inactive")
    payment_reference = db.Column(db.String(255), nullable=True)
    payment_order_id = db.Column(db.String(255), nullable=True)
    scanner_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="profile")


class ResumeDraft(db.Model):
    __tablename__ = "resume_drafts"

    draft_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    template_id = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    data = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    versions = db.relationship("ResumeDraftVersion", back_populates="draft", cascade="all, delete-orphan")


class ResumeDraftVersion(db.Model):
    __tablename__ = "resume_draft_versions"

    version_id = db.Column(db.Integer, primary_key=True)
    draft_id = db.Column(db.Integer, db.ForeignKey("resume_drafts.draft_id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    draft = db.relationship("ResumeDraft", back_populates="versions")

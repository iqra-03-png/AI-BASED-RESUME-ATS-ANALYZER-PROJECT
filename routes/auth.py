import hmac

from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from models import User, db


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    errors = {}
    form_data = {"name": "", "email": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        form_data.update(name=name, email=email)

        if not name or len(name) > 100:
            errors["name"] = "Enter your full name (up to 100 characters)."
        if len(email) > 254:
            errors["email"] = "Enter a valid email address."
        else:
            try:
                email = validate_email(email, check_deliverability=False).normalized.lower()
                form_data["email"] = email
            except EmailNotValidError:
                errors["email"] = "Enter a valid email address."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters long."
        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if not errors and User.query.filter_by(email=email).first():
            errors["email"] = "An account with that email already exists."

        if not errors:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["email"] = "An account with that email already exists."
            else:
                flash("Your account has been created. Please log in.", "success")
                return redirect(url_for("auth.login", role="user"))

    return render_template("register.html", errors=errors, form_data=form_data)


@auth_bp.route("/admin/register", methods=["GET", "POST"])
def admin_register():
    if current_user.is_authenticated:
        return redirect(
            url_for("main.admin_dashboard") if current_user.is_admin
            else url_for("main.dashboard")
        )

    errors = {}
    form_data = {"name": "", "email": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        registration_key = request.form.get("registration_key", "")
        form_data.update(name=name, email=email)

        configured_key = current_app.config.get("RESUNOVA_ADMIN_REGISTRATION_KEY")
        if (
            not isinstance(configured_key, str)
            or not configured_key
            or not registration_key
            or not hmac.compare_digest(
            registration_key, configured_key
            )
        ):
            errors["registration_key"] = "The admin registration key is invalid."
        if not name or len(name) > 100:
            errors["name"] = "Enter your full name (up to 100 characters)."
        if len(email) > 254:
            errors["email"] = "Enter a valid email address."
        else:
            try:
                email = validate_email(email, check_deliverability=False).normalized.lower()
                form_data["email"] = email
            except EmailNotValidError:
                errors["email"] = "Enter a valid email address."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters long."
        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if not errors and User.query.filter_by(email=email).first():
            errors["email"] = "An account with that email already exists."

        if not errors:
            admin = User(name=name, email=email, role="admin")
            admin.set_password(password)
            db.session.add(admin)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["email"] = "An account with that email already exists."
            else:
                flash("Admin account created. You can now log in.", "success")
                return redirect(url_for("auth.login", role="admin"))

    return render_template("admin_register.html", errors=errors, form_data=form_data)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if request.args.get("role") == "admin" and current_user.is_admin:
            return redirect(url_for("main.admin_dashboard"))
        return redirect(url_for("main.dashboard"))

    role = request.form.get("role", "user") if request.method == "POST" else request.args.get("role", "user")
    if role not in {"user", "admin"}:
        role = "user"

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        errors = {}
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            errors["email"] = "Enter a valid email address."
        if not password:
            errors["password"] = "Enter your password."
        if errors:
            return render_template(
                "login.html", role=role, errors=errors, email=request.form.get("email", "").strip()
            )

        user = User.query.filter_by(email=email).first()
        if user and user.role == role and user.check_password(password):
            login_user(user, remember=request.form.get("remember") == "1")
            if user.is_admin:
                return redirect(url_for("main.admin_dashboard"))
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))
        flash("Email or password is incorrect.", "error")

    return render_template("login.html", role=role, errors={}, email="")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("If that email is registered, a password reset link would be sent here.", "info")
        else:
            flash("Password reset emails are not configured for this local app yet. Add a trusted SMTP provider before enabling live resets.", "info")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))

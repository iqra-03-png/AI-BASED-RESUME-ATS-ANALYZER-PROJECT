from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from models import User, db


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or len(name) > 100:
            flash("Enter your name (up to 100 characters).", "error")
        elif len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 10 or len(password) > 128:
            flash("Your password must be between 10 and 128 characters.", "error")
        else:
            try:
                normalized_email = validate_email(email, check_deliverability=False).normalized.lower()
            except EmailNotValidError:
                flash("Enter a valid email address.", "error")
                return render_template("register.html")

            if User.query.filter_by(email=normalized_email).first():
                flash("An account with that email already exists.", "error")
            else:
                user = User(name=name, email=normalized_email)
                user.set_password(password)
                db.session.add(user)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("An account with that email already exists.", "error")
                else:
                    login_user(user)
                    flash("Your account is ready.", "success")
                    return redirect(url_for("main.dashboard"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))
        flash("Email or password is incorrect.", "error")

    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))

import os
from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url

from config import Config
from models import User, db
from routes.auth import auth_bp
from routes.main import main_bp


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def _ensure_user_role_column():
    columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
    if "role" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
            ))


def _provision_admin_account(app):
    email = app.config.get("RESUNOVA_ADMIN_EMAIL", "").strip()
    password = app.config.get("RESUNOVA_ADMIN_PASSWORD")
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError(
            "Set both RESUNOVA_ADMIN_EMAIL and RESUNOVA_ADMIN_PASSWORD to provision an admin account."
        )
    if len(password) < 10 or len(password) > 128:
        raise RuntimeError("RESUNOVA_ADMIN_PASSWORD must be between 10 and 128 characters.")
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise RuntimeError("RESUNOVA_ADMIN_EMAIL must be a valid email address.") from error

    admin = User.query.filter_by(email=email).first()
    if admin is None:
        admin = User(name="ResuNova Admin", email=email, role="admin")
        db.session.add(admin)
    else:
        admin.role = "admin"
    admin.set_password(password)
    db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True, mode=0o700)
    Path(app.instance_path).chmod(0o700)
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    upload_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    upload_root.chmod(0o700)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template("error.html", message="Your form session expired. Please try again."), 400

    @app.errorhandler(413)
    def file_too_large(_error):
        return render_template(
            "error.html", message="The upload is too large. Please choose a file smaller than 5 MB."
        ), 413

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", message="We could not find that page."), 404

    with app.app_context():
        db.create_all()
        _ensure_user_role_column()
        _provision_admin_account(app)
        database_name = make_url(app.config["SQLALCHEMY_DATABASE_URI"]).database
        if database_name and database_name != ":memory:":
            database_path = Path(database_name)
            if not database_path.is_absolute():
                database_path = Path(app.instance_path) / database_path
            if database_path.exists():
                database_path.chmod(0o600)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")

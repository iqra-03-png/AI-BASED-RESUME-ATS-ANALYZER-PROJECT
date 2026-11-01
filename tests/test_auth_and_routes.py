import io
import sqlite3

from app import create_app
from conftest import create_analysis, make_docx, register
from models import AnalysisReport, User, db
from services.report_generator import generate_pdf_report


def test_root_route_shows_shared_login_page_as_default(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'class="login-screen"' in response.data
    assert b'class="login-page"' in response.data
    assert b"Welcome back" in response.data
    assert b"Get your resume" in response.data
    assert b'<nav class="navbar' not in response.data
    assert b"Understand your resume match" not in response.data


def test_root_route_sends_authenticated_users_to_their_dashboard(client, app):
    register(client)
    user_response = client.get("/")
    assert user_response.status_code == 302
    assert user_response.headers["Location"].endswith("/dashboard")

    client.post("/auth/logout")
    with app.app_context():
        admin = User(name="ResuNova Admin", email="root-admin@example.com", role="admin")
        admin.set_password("root-admin-password-123")
        db.session.add(admin)
        db.session.commit()
    client.post("/auth/login", data={
        "email": "root-admin@example.com",
        "password": "root-admin-password-123",
        "role": "admin",
    })
    admin_response = client.get("/")
    assert admin_response.status_code == 302
    assert admin_response.headers["Location"].endswith("/admin/dashboard")


def test_registration_hashes_password_and_login_works(client, app):
    response = client.post("/auth/register", data={
        "name": "Jamie Student",
        "email": "jamie@example.com",
        "password": "UserPas8",
        "confirm_password": "UserPas8",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login?role=user")
    login_page = client.get(response.headers["Location"])
    assert b"Your account has been created. Please log in." in login_page.data
    with app.app_context():
        user = User.query.filter_by(email="jamie@example.com").one()
        assert user.password_hash != "UserPas8"
        assert user.check_password("UserPas8")
    response = client.post("/auth/login", data={
        "email": "jamie@example.com", "password": "UserPas8",
    }, follow_redirects=True)
    assert b"Analyze a resume" in response.data


def test_user_registration_uses_login_design_without_top_navigation(client):
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert b'class="login-screen"' in response.data
    assert b"login.css" in response.data
    assert b"Templates" not in response.data
    assert b"AI Assistant" not in response.data
    assert b"Premium Scanner" not in response.data
    assert b'class="nav-links"' not in response.data
    assert b'name="csrf_token"' in response.data
    assert b"Confirm Password" in response.data
    assert b"Already have an account?" in response.data
    assert b"Admin Registration Key" not in response.data
    assert b'href="/auth/login?role=user"' in response.data
    assert b'name="email"' in response.data
    assert b'name="password"' in response.data


def test_user_registration_requires_at_least_eight_matching_password_characters(client, app):
    form = {
        "name": "Jamie Student",
        "email": "eight-char@example.com",
        "password": "Short77",
        "confirm_password": "Short77",
    }
    too_short = client.post("/auth/register", data=form, follow_redirects=True)
    assert b"Password must be at least 8 characters long." in too_short.data
    with app.app_context():
        assert User.query.filter_by(email=form["email"]).first() is None

    form.update(password="PassWord", confirm_password="Mismatch")
    mismatch = client.post("/auth/register", data=form, follow_redirects=True)
    assert b"Passwords do not match." in mismatch.data
    with app.app_context():
        assert User.query.filter_by(email=form["email"]).first() is None

    form.update(password="LongerPass9", confirm_password="LongerPass9")
    created = client.post("/auth/register", data=form)
    assert created.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email=form["email"]).one()
        assert user.check_password("LongerPass9")
        assert user.password_hash != "LongerPass9"
    assert client.get("/dashboard").status_code == 302
    duplicate = client.post("/auth/register", data=form, follow_redirects=True)
    assert b"An account with that email already exists." in duplicate.data
    with app.app_context():
        assert User.query.filter_by(email=form["email"]).count() == 1


def test_invalid_login_is_rejected(client):
    register(client)
    client.post("/auth/logout")
    response = client.post("/auth/login", data={
        "email": "jamie@example.com", "password": "wrong-password",
    }, follow_redirects=True)
    assert b"Email or password is incorrect" in response.data


def test_login_role_routes_user_and_admin_separately(client, app):
    register(client)
    client.post("/auth/logout")
    user_login = client.post("/auth/login", data={
        "email": "jamie@example.com",
        "password": "UserPas8",
        "role": "user",
    })
    assert user_login.status_code == 302
    assert user_login.headers["Location"].endswith("/dashboard")
    assert client.get("/admin/dashboard").status_code == 403

    client.post("/auth/logout")
    rejected_admin_login = client.post("/auth/login", data={
        "email": "jamie@example.com",
        "password": "UserPas8",
        "role": "admin",
    }, follow_redirects=True)
    assert b"Email or password is incorrect" in rejected_admin_login.data

    with app.app_context():
        admin = User(name="ResuNova Admin", email="admin@example.com", role="admin")
        admin.set_password("an-admin-password-123")
        db.session.add(admin)
        db.session.commit()

    admin_login = client.post("/auth/login", data={
        "email": "admin@example.com",
        "password": "an-admin-password-123",
        "role": "admin",
    })
    assert admin_login.status_code == 302
    assert admin_login.headers["Location"].endswith("/admin/dashboard")
    assert client.get("/admin/dashboard").status_code == 200
    assert client.get("/templates").status_code == 200
    assert b"Open template" in client.get("/admin/dashboard").data


def test_admin_dashboard_sections_use_real_database_data(client, app):
    register(client)
    create_analysis(client)
    client.post("/auth/logout")
    with app.app_context():
        admin = User(name="ResuNova Admin", email="admin-sections@example.com", role="admin")
        admin.set_password("admin-test-password")
        db.session.add(admin)
        db.session.commit()
    client.post("/auth/login", data={
        "email": "admin-sections@example.com",
        "password": "admin-test-password",
        "role": "admin",
    })

    overview = client.get("/admin/dashboard")
    assert overview.status_code == 200
    assert b"Total Registered Users" in overview.data
    assert b"Resume Analysis Activity" in overview.data
    assert b"Recent Resume Reports" in overview.data
    for section in (
        "users", "analytics", "plans", "reports", "feedback",
        "notifications", "settings",
    ):
        response = client.get(f"/admin/dashboard?section={section}")
        assert response.status_code == 200, section
        assert b"admin-menu-link" in response.data

    users = client.get("/admin/dashboard?section=users")
    assert b"Jamie Student" in users.data
    assert b"jamie@example.com" in users.data
    reports = client.get("/admin/dashboard?section=reports")
    assert b"Jamie Student" in reports.data
    assert b"resume.docx" in reports.data
    search = client.get("/admin/dashboard?q=jamie")
    assert b"Search Results" in search.data
    assert b"Jamie Student" in search.data
    role_search = client.get("/admin/dashboard?q=admin")
    assert b"Administrator" in role_search.data
    assert b"Admin</span>" in role_search.data
    assert b"Database Connection" in client.get(
        "/admin/dashboard?section=settings"
    ).data
    assert b"No feedback records available" in client.get(
        "/admin/dashboard?section=feedback"
    ).data
    assert b"No notifications to display" in client.get(
        "/admin/dashboard?section=notifications"
    ).data


def test_admin_login_page_is_shared_but_role_specific(client):
    user_page = client.get("/auth/login")
    admin_page = client.get("/auth/login?role=admin")
    assert b"Welcome back" in user_page.data
    assert b"Log in as user" in user_page.data
    assert b"Admin panel" in admin_page.data
    assert b"Authorized admins only" in admin_page.data
    assert b"Log in as admin" in admin_page.data
    assert b"New to ResuNova? Create an account" not in admin_page.data
    assert b"New Admin?" in admin_page.data
    assert b"Create New Account" in admin_page.data
    assert b'href="/auth/admin/register"' in admin_page.data
    assert b'data-admin-register-link hidden' in user_page.data


def test_admin_registration_requires_valid_server_side_key(client, app):
    app.config["RESUNOVA_ADMIN_REGISTRATION_KEY"] = "server-only-invitation-secret"
    page = client.get("/auth/admin/register")
    assert page.status_code == 200
    assert b"Admin Registration Key" in page.data
    assert b"server-only-invitation-secret" not in page.data

    rejected = client.post("/auth/admin/register", data={
        "name": "Unauthorized Admin",
        "email": "unauthorized@example.com",
        "password": "UserPas8",
        "confirm_password": "UserPas8",
        "registration_key": "wrong-key",
    })
    assert rejected.status_code == 200
    assert b"The admin registration key is invalid." in rejected.data
    with app.app_context():
        assert User.query.filter_by(email="unauthorized@example.com").first() is None


def test_admin_registration_validates_fields_and_duplicate_email(client, app):
    app.config["RESUNOVA_ADMIN_REGISTRATION_KEY"] = "server-only-invitation-secret"
    invalid = client.post("/auth/admin/register", data={
        "name": "",
        "email": "not-an-email",
        "password": "Short77",
        "confirm_password": "different",
        "registration_key": "server-only-invitation-secret",
    })
    assert invalid.status_code == 200
    assert b"Enter your full name" in invalid.data
    assert b"Enter a valid email address." in invalid.data
    assert b"Password must be at least 8 characters long." in invalid.data
    assert b"Passwords do not match." in invalid.data

    longer_password = client.post("/auth/admin/register", data={
        "name": "Long Password Admin",
        "email": "long-password-admin@example.com",
        "password": "LongerPass9",
        "confirm_password": "LongerPass9",
        "registration_key": "server-only-invitation-secret",
    })
    assert longer_password.status_code == 302
    with app.app_context():
        admin = User.query.filter_by(email="long-password-admin@example.com").one()
        assert admin.is_admin
        assert admin.check_password("LongerPass9")

    form = {
        "name": "Authorized Admin",
        "email": "new-admin@example.com",
        "password": "Admin888",
        "confirm_password": "Admin888",
        "registration_key": "server-only-invitation-secret",
    }
    created = client.post("/auth/admin/register", data=form)
    assert created.status_code == 302
    assert created.headers["Location"].endswith("/auth/login?role=admin")
    assert b"Admin account created. You can now log in." in client.get(
        created.headers["Location"]
    ).data
    with app.app_context():
        admin = User.query.filter_by(email=form["email"]).one()
        assert admin.is_admin
        assert admin.password_hash != form["password"]
        assert admin.check_password(form["password"])

    duplicate = client.post("/auth/admin/register", data=form)
    assert duplicate.status_code == 200
    assert b"An account with that email already exists." in duplicate.data
    with app.app_context():
        assert User.query.filter_by(email=form["email"]).count() == 1


def test_registered_admin_can_login_access_dashboard_and_logout(client, app):
    app.config["RESUNOVA_ADMIN_REGISTRATION_KEY"] = "server-only-invitation-secret"
    created = client.post("/auth/admin/register", data={
        "name": "Authorized Admin",
        "email": "new-admin@example.com",
        "password": "Admin888",
        "confirm_password": "Admin888",
        "registration_key": "server-only-invitation-secret",
    })
    assert created.status_code == 302
    assert client.get("/admin/dashboard").status_code == 302

    login_response = client.post("/auth/login", data={
        "email": "new-admin@example.com",
        "password": "Admin888",
        "role": "admin",
    })
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/admin/dashboard")
    assert client.get("/admin/dashboard").status_code == 200

    client.post("/auth/logout")
    assert client.get("/admin/dashboard").status_code == 302


def test_login_validates_email_and_required_password_inline(client):
    response = client.post("/auth/login", data={
        "email": "not-an-email",
        "password": "",
        "role": "user",
    })
    assert b"Enter a valid email address." in response.data
    assert b"Enter your password." in response.data


def test_admin_credentials_from_config_create_admin_account(tmp_path):
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key-not-for-production",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "RESUNOVA_ADMIN_EMAIL": "ops@example.com",
        "RESUNOVA_ADMIN_PASSWORD": "provisioned-admin-password",
    })
    with application.app_context():
        admin = User.query.filter_by(email="ops@example.com").one()
        assert admin.is_admin
        assert admin.check_password("provisioned-admin-password")


def test_existing_user_table_is_migrated_with_user_role(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE users (user_id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
            "email VARCHAR(254) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )

    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key-not-for-production",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })
    with application.app_context():
        user = User(name="Legacy User", email="legacy@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()
        assert user.role == "user"


def test_analysis_requires_authentication(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    response = client.post("/analyze", data={"job_description": "A long enough job description."})
    assert response.status_code == 302


def test_upload_analyzes_saves_and_downloads_report(client, app):
    register(client)
    response = create_analysis(client)
    assert response.status_code == 302
    result = client.get(response.headers["Location"])
    assert result.status_code == 200
    assert b"Score breakdown" in result.data
    assert b"Preview extracted resume text" in result.data

    download = client.get(response.headers["Location"] + "/download")
    assert download.status_code == 200
    assert download.mimetype == "application/pdf"
    assert download.data.startswith(b"%PDF")
    with app.app_context():
        report = AnalysisReport.query.one()
        assert report.ats_score >= 0
        assert report.resume.internal_filename != report.resume.file_name
        stored = app.config["UPLOAD_FOLDER"] + f"/{report.user_id}/{report.resume.internal_filename}"
        with open(stored, "rb") as uploaded:
            assert uploaded.read(4) == b"PK\x03\x04"


def test_invalid_upload_and_empty_job_description_are_rejected(client):
    register(client)
    response = create_analysis(
        client, filename="resume.txt", content=make_docx(), job="Short"
    )
    assert response.status_code == 302
    assert "dashboard" in response.headers["Location"]
    response = client.get("/history")
    assert b"No saved analyses yet" in response.data


def test_oversized_resume_is_rejected(client):
    register(client)
    response = create_analysis(
        client,
        filename="large.pdf",
        content=io.BytesIO(b"%PDF-" + (b"x" * (5 * 1024 * 1024))),
    )
    assert response.status_code == 302
    response = client.get("/dashboard", follow_redirects=True)
    assert b"no larger than 5 MB" in response.data


def test_users_cannot_access_or_delete_another_users_report(client):
    register(client)
    response = create_analysis(client)
    report_path = response.headers["Location"]
    client.post("/auth/logout")
    register(client, email="other@example.com")
    assert client.get(report_path).status_code == 404
    assert client.get(report_path + "/download").status_code == 404
    assert client.post(report_path + "/delete").status_code == 404


def test_history_owner_can_delete_report(client, app):
    register(client)
    response = create_analysis(client)
    report_path = response.headers["Location"]
    assert client.get("/history").status_code == 200
    assert client.post(report_path + "/delete", follow_redirects=True).status_code == 200
    with app.app_context():
        assert AnalysisReport.query.count() == 0


def test_report_generator_returns_pdf(client, app):
    register(client)
    response = create_analysis(client)
    report_id = int(response.headers["Location"].rsplit("/", 1)[-1])
    with app.app_context():
        report = db.session.get(AnalysisReport, report_id)
        pdf = generate_pdf_report(report, report.resume, report.job_description)
        assert pdf.read(4) == b"%PDF"

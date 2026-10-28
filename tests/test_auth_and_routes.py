import io

from conftest import create_analysis, make_docx, register
from models import AnalysisReport, User, db
from services.report_generator import generate_pdf_report


def test_registration_hashes_password_and_login_works(client, app):
    response = register(client)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="jamie@example.com").one()
        assert user.password_hash != "a-safe-password-123"
        assert user.check_password("a-safe-password-123")
    client.post("/auth/logout")
    response = client.post("/auth/login", data={
        "email": "jamie@example.com", "password": "a-safe-password-123",
    }, follow_redirects=True)
    assert b"Analyze a resume" in response.data


def test_invalid_login_is_rejected(client):
    register(client)
    client.post("/auth/logout")
    response = client.post("/auth/login", data={
        "email": "jamie@example.com", "password": "wrong-password",
    }, follow_redirects=True)
    assert b"Email or password is incorrect" in response.data


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

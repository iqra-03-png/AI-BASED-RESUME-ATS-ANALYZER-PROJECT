import io

import pytest
from docx import Document
from reportlab.pdfgen import canvas

from app import create_app
from models import db


RESUME_TEXT = """Jamie Student
jamie.student@example.test | github.com/jamie
Education
B.Tech Information Technology, Example University, 2022-2026
Skills
Python, Flask, SQL, JavaScript, Git, Docker, machine learning, pandas
Projects
Resume analyzer built with Python, Flask, scikit-learn, SQLite and pytest.
Created a data analysis dashboard and REST API with unit testing.
Experience
Software engineering intern, Example Labs, 2025
Built a data pipeline and improved API response time by 20 percent.
"""

JOB_DESCRIPTION = """Junior software developer
We need a Python and Flask developer with SQL, JavaScript and Git skills.
Experience building REST API services, data analysis projects, Docker,
machine learning and unit testing is preferred. A bachelor's degree is required."""


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    upload_path = tmp_path / "uploads"
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key-not-for-production",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "UPLOAD_FOLDER": str(upload_path),
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def resume_text():
    return RESUME_TEXT


@pytest.fixture
def job_description():
    return JOB_DESCRIPTION


def make_docx(text=RESUME_TEXT):
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    output = io.BytesIO()
    document.save(output)
    output.seek(0)
    return output


def make_pdf(text=RESUME_TEXT):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for index, line in enumerate(text.splitlines()):
        pdf.drawString(40, 800 - (index * 18), line)
    pdf.save()
    output.seek(0)
    return output


def register(client, email="jamie@example.com", password="UserPas8"):
    response = client.post("/auth/register", data={
        "name": "Jamie Student",
        "email": email,
        "password": password,
        "confirm_password": password,
    }, follow_redirects=True)
    if b"Your account has been created. Please log in." in response.data:
        client.post("/auth/login", data={
            "email": email,
            "password": password,
            "role": "user",
        })
    return response


def create_analysis(client, filename="resume.docx", content=None, job=JOB_DESCRIPTION):
    if content is None:
        content = make_docx()
    return client.post("/analyze", data={
        "resume": (content, filename),
        "job_title": "Junior Developer",
        "company_name": "Example Labs",
        "job_description": job,
    }, content_type="multipart/form-data", follow_redirects=False)

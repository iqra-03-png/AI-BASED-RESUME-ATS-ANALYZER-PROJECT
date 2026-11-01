import json
from io import BytesIO
from datetime import timedelta, timezone

from conftest import make_docx, register
from docx import Document
from models import AnalysisReport, ResumeDraft, ResumeDraftVersion, User, UserProfile, db, utc_now
from services.product import RESUME_FIELDS, TEMPLATE_CATALOG


def test_template_catalog_and_backend_premium_gate(client, app):
    register(client)
    response = client.get("/templates")
    assert response.status_code == 200
    assert sum(template["tier"] == "free" for template in TEMPLATE_CATALOG) >= 3
    assert sum(template["tier"] == "premium" for template in TEMPLATE_CATALOG) >= 5

    free_template = next(item for item in TEMPLATE_CATALOG if item["tier"] == "free")
    premium_template = next(item for item in TEMPLATE_CATALOG if item["tier"] == "premium")
    created = client.get(f"/templates/{free_template['id']}/select")
    assert created.status_code == 302
    assert "/builder/" in created.headers["Location"]
    locked = client.get(f"/templates/{premium_template['id']}/select")
    assert locked.status_code == 302
    assert locked.headers["Location"].endswith("/templates")
    template_page = client.get("/templates")
    assert b"Upgrade to Premium to use this template." in template_page.data
    assert b"data-premium-template" in template_page.data
    with app.app_context():
        assert ResumeDraft.query.count() == 1
        assert ResumeDraft.query.one().template_id == free_template["id"]

    client.post("/pricing/demo-upgrade")
    unlocked = client.get(f"/templates/{premium_template['id']}/select")
    assert unlocked.status_code == 302
    with app.app_context():
        assert ResumeDraft.query.count() == 2


def test_admin_can_select_premium_template_without_a_subscription(client, app):
    with app.app_context():
        admin = User(name="ResuNova Admin", email="admin@example.com", role="admin")
        admin.set_password("an-admin-password-123")
        db.session.add(admin)
        db.session.commit()

    response = client.post("/auth/login", data={
        "email": "admin@example.com",
        "password": "an-admin-password-123",
        "role": "admin",
    })
    assert response.headers["Location"].endswith("/admin/dashboard")

    selected = client.get("/templates/premium-engineering/select")
    assert selected.status_code == 302
    assert "/builder/" in selected.headers["Location"]
    assert client.get(selected.headers["Location"]).status_code == 200


def test_demo_subscription_is_clear_and_persisted(client, app):
    register(client)
    pricing = client.get("/pricing")
    assert b"Demo subscription only" in pricing.data
    assert b"no payment is processed" in pricing.data
    client.post("/pricing/demo-upgrade")
    with app.app_context():
        profile = UserProfile.query.one()
        assert profile.plan == "premium"
        assert profile.subscription_expires_at.replace(tzinfo=timezone.utc) > utc_now()
    assert b"Premium is active" in client.get("/pricing").data


def test_premium_scanner_requires_entitlement_and_persists_expiry(client, app):
    register(client)
    blocked = client.post("/premium-scanner/start")
    assert blocked.status_code == 302
    assert blocked.headers["Location"].endswith("/pricing")

    client.post("/pricing/demo-upgrade")
    started = client.post("/premium-scanner/start")
    assert started.status_code == 302
    assert started.headers["Location"].endswith("/premium-scanner")
    scanner_page = client.get("/premium-scanner")
    assert scanner_page.status_code == 200
    assert b"Time left" in scanner_page.data
    assert b"02:00" in scanner_page.data
    with app.app_context():
        profile = UserProfile.query.one()
        original_expiry = profile.scanner_expires_at
        remaining = (original_expiry.replace(tzinfo=timezone.utc) - utc_now()).total_seconds()
        assert 118 <= remaining <= 120

    client.post("/premium-scanner/start")
    with app.app_context():
        assert UserProfile.query.one().scanner_expires_at == original_expiry

    completed_scan = client.post(
        "/premium-scanner/analyze",
        data={
            "resume": (make_docx(), "premium-resume.docx"),
            "job_description": "Python software engineering role requiring testing and project experience.",
        },
        content_type="multipart/form-data",
    )
    assert completed_scan.status_code == 302
    assert "/reports/" in completed_scan.headers["Location"]

    with app.app_context():
        profile = UserProfile.query.one()
        profile.scanner_expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()
    expired_page = client.get("/premium-scanner")
    assert b"Your two-minute scanner session has expired" in expired_page.data
    rejected = client.post("/premium-scanner/analyze", data={})
    assert rejected.status_code == 302
    with app.app_context():
        assert ResumeDraft.query.count() == 0
        assert AnalysisReport.query.count() == 1


def test_resume_builder_saves_versions_and_exports(client, app):
    register(client)
    selected = client.get("/templates/free-clean/select")
    draft_id = int(selected.headers["Location"].rsplit("/", 1)[-1])
    form = {"title": "Jamie software resume"}
    for field in RESUME_FIELDS:
        form[field] = ""
    form.update({
        "full_name": "Jamie Student",
        "headline": "Software engineering student",
        "email": "jamie@example.test",
        "education": "B.Tech, Example University",
        "projects": "Built a resume analyzer with Python and Flask.",
        "skills": "Python, Flask, SQL",
    })
    saved = client.post(f"/builder/{draft_id}", data=form)
    assert saved.status_code == 302
    assert client.get(f"/builder/{draft_id}").status_code == 200
    assert b"Jamie Student" in client.get(f"/builder/{draft_id}").data

    pdf = client.get(f"/builder/{draft_id}/export/pdf")
    docx = client.get(f"/builder/{draft_id}/export/docx")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    assert docx.status_code == 200 and docx.data.startswith(b"PK")
    headings = [
        paragraph.text for paragraph in Document(BytesIO(docx.data)).paragraphs
        if paragraph.style.name == "Heading 1"
    ]
    assert headings == ["Skills", "Projects", "Education"]
    versions_page = client.get(f"/builder/{draft_id}/versions")
    assert versions_page.status_code == 200
    assert b"Version 2" in versions_page.data
    with app.app_context():
        draft = db.session.get(ResumeDraft, draft_id)
        assert draft.version == 2
        assert json.loads(draft.data)["skills"] == "Python, Flask, SQL"
        assert ResumeDraftVersion.query.filter_by(draft_id=draft_id).count() == 2


def test_resume_draft_is_private_and_category_updates(client):
    register(client)
    selected = client.get("/templates/free-clean/select")
    draft_path = selected.headers["Location"]
    profile = client.post("/profile", data={"name": "Jamie", "category": "Student"}, follow_redirects=True)
    assert b"Your profile was updated" in profile.data
    assert b"Academic projects" in client.get("/dashboard").data

    client.post("/auth/logout")
    register(client, email="another@example.com")
    assert client.get(draft_path).status_code == 404


def test_premium_draft_is_relocked_after_subscription_expiry(client, app):
    register(client)
    client.post("/pricing/demo-upgrade")
    selected = client.get("/templates/premium-engineering/select")
    draft_path = selected.headers["Location"]
    assert client.get(draft_path).status_code == 200
    with app.app_context():
        profile = UserProfile.query.one()
        profile.subscription_expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()
    assert client.get(draft_path).status_code == 302
    assert client.get(draft_path + "/export/pdf").status_code == 302

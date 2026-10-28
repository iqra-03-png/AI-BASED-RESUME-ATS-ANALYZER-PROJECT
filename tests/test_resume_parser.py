from services.resume_parser import ResumeParseError, parse_resume

from conftest import make_docx, make_pdf


def test_parse_docx(tmp_path, resume_text):
    path = tmp_path / "resume.docx"
    path.write_bytes(make_docx(resume_text).getvalue())
    extracted = parse_resume(path)
    assert "Education" in extracted
    assert "Python" in extracted


def test_parse_pdf(tmp_path, resume_text):
    path = tmp_path / "resume.pdf"
    path.write_bytes(make_pdf(resume_text).getvalue())
    extracted = parse_resume(path)
    assert "Education" in extracted
    assert "Python" in extracted


def test_reject_invalid_and_empty_files(tmp_path):
    invalid = tmp_path / "resume.pdf"
    invalid.write_bytes(b"not a pdf")
    try:
        parse_resume(invalid)
    except ResumeParseError as error:
        assert "valid PDF" in str(error)
    else:
        raise AssertionError("Invalid PDF should be rejected")

    empty = tmp_path / "empty.docx"
    empty.write_bytes(make_docx("").getvalue())
    try:
        parse_resume(empty)
    except ResumeParseError as error:
        assert "No usable text" in str(error)
    else:
        raise AssertionError("A document without text should be rejected")


def test_reject_unsupported_extension(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("A resume in an unsupported format.")
    try:
        parse_resume(path)
    except ResumeParseError as error:
        assert "PDF or DOCX" in str(error)
    else:
        raise AssertionError("Unsupported extension should be rejected")

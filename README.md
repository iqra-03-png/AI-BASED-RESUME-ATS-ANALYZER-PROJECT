# ResumeLens — AI-Based Resume ATS Analyzer

ResumeLens is a local Flask mini project that compares a PDF or DOCX resume with a job description. It shows a reproducible compatibility estimate, score components, matched and missing terms, structure checks, and suggestions. It is an educational estimate—not an official score from a commercial Applicant Tracking System and not a prediction of a hiring decision.

Resume content is processed locally by this application. It is not sent to an external AI service. User accounts use password hashing, CSRF protection, private randomized upload paths, and user-scoped report queries.

## Features

- Registration, login, logout, and private per-account analysis history.
- PDF and DOCX text extraction. Encrypted, damaged, unsupported, or text-free files receive a friendly error. Scanned PDFs are not supported; OCR is not claimed.
- Local rule-based skills dictionary, TF-IDF and cosine similarity. spaCy tokenization is optional; the application falls back to regular-expression tokenization.
- Deterministic weighted ATS estimate and explainable component scores.
- Result dashboard with a safely escaped extracted-text preview, improvement ideas, and PDF report download.
- Three free ATS-friendly resume templates and five premium, industry-focused templates, with backend access checks.
- Editable resume builder with live preview, private version history, and PDF/DOCX export.
- Profile categories with local recommendations for relevant sections, skills, layouts, and example descriptions.
- Free and Premium plan pages. Premium activation is a clearly labeled local demo entitlement; payment processing is not configured.
- A Premium scanner session with a server-stored two-minute expiry, visible countdown, and server-side authorization. An analysis submitted before expiry is not cancelled.
- Dashboard summary with average saved ATS score, resume drafts, subscription state, and recent reports.
- SQLite persistence and responsive HTML/CSS/JavaScript interface.
- Pytest coverage for scoring, parsers, authentication, report generation, uploads, and ownership boundaries.

## Scoring formula

The final estimate is the sum of each component's raw percentage multiplied by its weight:

| Component | Weight | Raw component score |
|---|---:|---|
| Keyword matching | 40% | 70% coverage of up to 12 prominent job-description terms + 30% TF-IDF cosine similarity |
| Skills matching | 25% | Detected job-description skills found in the resume / all detected job-description skills |
| Resume structure | 15% | Count of six detected signals: contact details, education, experience, projects, skills, and certifications headings |
| Experience and education relevance | 10% | Four measurable section/term checks; job-requirement-specific checks are excluded from the denominator when not relevant |
| Readability | 10% | Four measurable checks for 150–1,800 words, average word length, separate lines, and unusual-symbol ratio |

Each raw score is between 0 and 100. Weighted contributions are summed and rounded to the nearest integer; the final estimate is bounded to 0–100. The component weights always total 100%.

The skills dictionary is intentionally inspectable and extendable in `services/analyzer.py`. It will miss skills not listed, may match a term without understanding its context, and should not be treated as an evaluator of a person's actual ability. Term ranking is a small-document TF-IDF heuristic, not a commercial ATS implementation. Section checks include contact, education, experience, projects, skills, and certifications; they are text signals rather than semantic document understanding.

## Templates, resume builder, and plans

The template gallery includes three free templates (Clear, Classic, and Compact) and five premium designs (Modern Executive, Engineering Portfolio, Leadership Profile, People & Culture, and Professional Impact). Premium selection, editing, export, and version-history requests are verified against the signed-in user's active subscription on the server. Templates keep a one-column text structure for readability, while varying section order and visual styling for their intended use.

The builder saves user-owned resume drafts and content snapshots in SQLite. Its preview updates as fields are edited; PDF and DOCX exports use the selected template's styling and section order. Profile categories personalize suggested sections, skills, and example descriptions. Recommendations and scan suggestions are generated locally from the selected category and existing rule-based analyzer; no external AI service or API key is configured.

Pricing currently uses a clearly identified demo flow rather than a payment gateway: activating or renewing the demo sets Premium access for 30 days, and no card details or payment are collected. A Premium scanner session lasts two minutes according to a database expiry timestamp. Refreshing or changing browser state does not extend it. Starting a scan is authorized server-side, and a request accepted before expiry is allowed to finish normally. An active subscriber may start another session after the current one expires.

## Prerequisites (macOS, Apple Silicon)

- Python 3.11 or 3.12 recommended (Python 3.9+ may work with dependency versions supported by that Python).
- VS Code and its Microsoft Python extension.
- Git is optional for running and needed for version-control/GitHub workflows.
- No MySQL server, paid API, or Sentence-BERT model is required.

On macOS, if Python or Git commands are missing, install Apple's Command Line Tools first:

```bash
xcode-select --install
```

Install a current Python 3 release from [python.org/downloads/macos](https://www.python.org/downloads/macos/) if needed. Open a new Terminal window and verify:

```bash
python3 --version
python3 -m pip --version
git --version
```

## Install and run

Run these commands from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Generate and set a private `SECRET_KEY` in `.env` before using the app beyond a local demo. One way to generate it on macOS is:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set `SECRET_KEY` to the printed value. Run:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). For development, `.env.example` sets `FLASK_DEBUG=true`; never expose the Flask development server to the public internet. If you want debug mode off, set `FLASK_DEBUG=false`.

In VS Code, open this folder, install the Microsoft Python extension if needed, press **Cmd+Shift+P**, choose **Python: Select Interpreter**, and select `.venv/bin/python`.

## Run tests

With the virtual environment active:

```bash
pytest
```

spaCy is optional because the baseline project works without a downloaded language model. To enable its tokenizer after installing the core requirements, install it separately in the virtual environment with `python -m pip install "spacy>=3.8,<4.0"`. The analysis page records whether spaCy or regex tokenization was used.

The test fixtures use fictional student and employer data and an isolated temporary SQLite database.

## Project structure

| Path | Purpose |
|---|---|
| `app.py` | Flask app factory, extensions, error handlers, and local entry point |
| `config.py` | Environment-based configuration and local file paths |
| `models.py` | SQLAlchemy models for users, profiles, resumes, drafts/versions, job descriptions, and reports |
| `routes/auth.py` | Registration, login, logout |
| `routes/main.py` | Analysis, history, template, profile, plan, scanner, builder, export, and ownership-checked routes |
| `services/resume_parser.py` | PDF/DOCX validation and local text extraction |
| `services/analyzer.py` | Skill dictionary, TF-IDF comparison, scoring, checks, and suggestions |
| `services/product.py` | Template catalog, editable resume fields, and profile recommendations |
| `services/resume_export.py` | Styled PDF and DOCX resume exports |
| `services/report_generator.py` | Escaped PDF analysis report generation |
| `templates/` | Jinja HTML pages |
| `static/css/`, `static/js/` | Responsive styling and small form interactions |
| `tests/` | Pytest test fixtures and automated tests |
| `instance/` | Local SQLite database (ignored by Git) |
| `uploads/` | Per-user randomized private uploaded documents (ignored by Git) |

## Demo checklist

1. Register using a fictional name and email.
2. Upload a text-based PDF or DOCX resume and paste a job description of at least 30 characters.
3. Confirm the results page shows the estimate, weighted breakdown, matched/missing terms, checks, suggestions, and extracted-text preview.
4. Download the PDF report and inspect its score and disclaimer.
5. Open **History**, reopen the result, and delete it.
6. Create a second account and verify the first account's report URL returns not found.
7. Try an unsupported file and a short job description to see validation feedback.
8. Browse all eight resume templates, verify a free account is redirected when selecting Premium, then activate the clearly marked demo plan and try a premium layout.
9. Save edits in the resume builder, inspect a version snapshot, and download both PDF and DOCX exports.
10. Start a Premium scanner session, confirm it begins at 02:00, and verify an expired session rejects new scans.

For a college presentation, useful screenshots are the landing page, analysis form, results/breakdown, history page, and downloaded report. Use fictional sample documents and do not show real contact details.

## Limitations and privacy

- Scanned/image-only PDFs require OCR and are rejected with an explanation.
- Skills are found using an editable dictionary, not deep contextual understanding.
- TF-IDF measures word overlap and does not understand meaning like a human reviewer.
- Section and readability checks use simple text rules; complex multi-column designs may extract poorly.
- Resume files and extracted text are retained in the local SQLite database/upload directory until their report is deleted. This prototype is intended for local demonstrations; do not use it to make hiring decisions.
- Resume drafts and their version snapshots are retained in the local SQLite database; the prototype does not yet include draft deletion or automatic retention periods.
- Premium activation is a demo entitlement, not a paid subscription. The demo has no payment processor, webhook, or real billing renewal.
- Configure a strong secret key and use a production WSGI server and HTTPS before any deployment. The included development server and setup are for local use only.

import json
import re
import unicodedata

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    import spacy

    _SPACY_TOKENIZER = spacy.blank("en")
except ImportError:
    _SPACY_TOKENIZER = None


SKILL_DICTIONARY = {
    "python": ("python",),
    "java": ("java",),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "c++": ("c++",),
    "c#": ("c#", "c sharp"),
    "go": ("golang",),
    "rust": ("rust",),
    "sql": ("sql",),
    "html": ("html",),
    "css": ("css",),
    "react": ("react", "react.js"),
    "angular": ("angular",),
    "vue": ("vue", "vue.js"),
    "node.js": ("node.js", "nodejs"),
    "flask": ("flask",),
    "django": ("django",),
    "fastapi": ("fastapi",),
    "spring": ("spring boot", "spring framework"),
    "rest api": ("rest api", "restful api",),
    "graphql": ("graphql",),
    "git": ("git", "github"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "google cloud": ("google cloud", "gcp"),
    "linux": ("linux",),
    "machine learning": ("machine learning", "ml"),
    "deep learning": ("deep learning",),
    "natural language processing": ("natural language processing", "nlp"),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch",),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "mongodb": ("mongodb",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "sqlite": ("sqlite",),
    "redis": ("redis",),
    "data analysis": ("data analysis", "data analytics"),
    "data visualization": ("data visualization",),
    "tableau": ("tableau",),
    "power bi": ("power bi",),
    "excel": ("excel", "microsoft excel"),
    "agile": ("agile",),
    "scrum": ("scrum",),
    "unit testing": ("unit testing",),
    "pytest": ("pytest",),
    "communication": ("communication",),
    "project management": ("project management",),
}

STOP_WORDS = {
    "about", "after", "also", "and", "are", "for", "from", "have", "into", "its",
    "our", "the", "their", "this", "that", "with", "will", "you", "your", "years",
    "year", "work", "working", "role", "team", "candidate", "required", "preferred",
}

STRUCTURE_LABELS = {
    "Contact information": re.compile(r"\b(email|phone|linkedin|github|contact)\b", re.I),
    "Education section": re.compile(r"\b(education|academic|degree|university|college)\b", re.I),
    "Experience section": re.compile(r"\b(experience|employment|internship|work history|professional history)\b", re.I),
    "Projects section": re.compile(r"\bprojects?\b", re.I),
    "Skills section": re.compile(r"\b(skills|technical skills|technologies)\b", re.I),
    "Certifications section": re.compile(r"\b(certifications?|licenses?)\b", re.I),
}

EDUCATION_TERMS = {"degree", "bachelor", "master", "education", "graduate", "academic", "qualification"}
EXPERIENCE_TERMS = {"experience", "internship", "project", "years", "employment", "professional"}


def clean_text(text):
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", normalized)
    normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
    normalized = re.sub(r"\n[ \t]*\n+", "\n", normalized)
    return normalized.strip()


def _tokenize_for_comparison(text):
    if _SPACY_TOKENIZER is None:
        return text
    return " ".join(token.text for token in _SPACY_TOKENIZER.make_doc(text))


def _contains_phrase(text, phrase):
    escaped = re.escape(phrase.strip()).replace(r"\ ", r"\s+")
    return re.search(r"(?<!\w)" + escaped + r"(?!\w)", text, flags=re.IGNORECASE) is not None


def extract_skills(text):
    normalized = clean_text(text).casefold()
    return sorted(
        skill for skill, aliases in SKILL_DICTIONARY.items()
        if any(_contains_phrase(normalized, alias.casefold()) for alias in aliases)
    )


def _important_keywords(job_description, resume_text, excluded_skills):
    vectorizer = TfidfVectorizer(
        stop_words="english", ngram_range=(1, 2), max_features=80, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.-]{1,}\b"
    )
    try:
        matrix = vectorizer.fit_transform([
            _tokenize_for_comparison(job_description),
            _tokenize_for_comparison(resume_text),
        ])
    except ValueError:
        return [], [], 0.0
    features = vectorizer.get_feature_names_out()
    jd_row = matrix[0].toarray().ravel()
    resume_terms = set(features[matrix[1].toarray().ravel() > 0])
    ranked = sorted(
        ((str(features[index]), float(jd_row[index])) for index in range(len(features))),
        key=lambda item: (-item[1], item[0]),
    )
    selected = []
    for term, _weight in ranked:
        if any(_contains_phrase(term, skill) for skill in excluded_skills):
            continue
        if len(term) < 3 or term in STOP_WORDS:
            continue
        if term not in selected:
            selected.append(term)
        if len(selected) == 12:
            break
    matched = [term for term in selected if term in resume_terms or _contains_phrase(resume_text, term)]
    missing = [term for term in selected if term not in matched]
    coverage = len(matched) / len(selected) if selected else 0.0
    similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    return matched, missing, (0.7 * coverage) + (0.3 * similarity)


def _structure_checks(resume_text):
    checks = [
        {"label": label, "passed": bool(pattern.search(resume_text))}
        for label, pattern in STRUCTURE_LABELS.items()
    ]
    return checks, sum(check["passed"] for check in checks) / len(checks)


def _relevance_score(resume_text, job_description):
    resume_lower = resume_text.casefold()
    jd_terms = set(re.findall(r"[a-zA-Z]+", job_description.casefold()))
    criteria = [
        (bool(re.search(r"\b(education|academic|degree)\b", resume_lower)), True),
        (bool(re.search(r"\b(experience|employment|internship|projects?)\b", resume_lower)), True),
        (
            any(term in resume_lower for term in EDUCATION_TERMS),
            bool(jd_terms & EDUCATION_TERMS),
        ),
        (
            any(term in resume_lower for term in EXPERIENCE_TERMS),
            bool(jd_terms & EXPERIENCE_TERMS),
        ),
    ]
    applicable = [passed for passed, is_applicable in criteria if is_applicable]
    return sum(applicable) / len(applicable) if applicable else 0.0


def _readability_score(resume_text):
    words = re.findall(r"\b[\w+#.-]+\b", resume_text)
    word_count = len(words)
    word_count_ok = 150 <= word_count <= 1800
    average_word_length = sum(len(word) for word in words) / word_count if word_count else 0
    word_length_ok = 2.5 <= average_word_length <= 12
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    has_layout_breaks = len(lines) >= 4
    unusual_ratio = (
        sum(1 for char in resume_text if not (char.isalnum() or char.isspace() or char in ".,;:()[]{}@+/#&-'"))
        / max(len(resume_text), 1)
    )
    checks = [
        {"label": "Resume has 150–1,800 words", "passed": word_count_ok},
        {"label": "Average word length is 2.5–12 characters", "passed": word_length_ok},
        {"label": "Text contains at least four separate lines", "passed": has_layout_breaks},
        {"label": "Unusual-symbol ratio is at most 10%", "passed": bool(resume_text) and unusual_ratio <= 0.10},
    ]
    return sum(check["passed"] for check in checks) / len(checks), checks


def _suggestions(missing_skills, missing_keywords, structure_checks, readability_checks, word_count):
    suggestions = []
    if missing_skills:
        names = ", ".join(missing_skills[:5])
        suggestions.append(
            "The job description mentions these skills that were not detected: "
            f"{names}. Add them only if you genuinely have the experience, and support them with evidence."
        )
    if missing_keywords:
        suggestions.append(
            "Consider addressing relevant job-description terms such as "
            f"{', '.join(missing_keywords[:5])} in truthful project or experience details."
        )
    for check in structure_checks:
        if not check["passed"]:
            suggestions.append(f"Add a clearly labeled {check['label'].replace(' section', '').lower()} section if relevant.")
    failed_readability = [check["label"] for check in readability_checks if not check["passed"]]
    if word_count < 150:
        suggestions.append("The extracted resume is quite short. Add concise, relevant details about projects, coursework, or experience.")
    elif word_count > 1800:
        suggestions.append("Consider trimming repeated or less relevant details so the most relevant evidence is easy to find.")
    if failed_readability and not any("short" in item.lower() or "trimming" in item.lower() for item in suggestions):
        suggestions.append("Improve text readability with clear headings, concise bullets, and a simple document layout.")
    if not suggestions:
        suggestions.append("Keep the resume truthful and tailor its examples to the role; this estimate cannot replace a human review.")
    return suggestions


def analyze_resume(resume_text, job_description):
    resume = clean_text(resume_text)
    job = clean_text(job_description)
    resume_skills = set(extract_skills(resume))
    job_skills = set(extract_skills(job))
    matched_skills = sorted(resume_skills & job_skills)
    missing_skills = sorted(job_skills - resume_skills)
    matched_keywords, missing_keywords, keyword_raw = _important_keywords(
        job, resume, excluded_skills=job_skills
    )
    structure_checks, structure_raw = _structure_checks(resume)
    relevance_raw = _relevance_score(resume, job)
    readability_raw, readability_checks = _readability_score(resume)
    skills_raw = len(matched_skills) / len(job_skills) if job_skills else 0.0

    raw_scores = [
        ("Keyword matching", 40, keyword_raw),
        ("Skills matching", 25, skills_raw),
        ("Resume structure", 15, structure_raw),
        ("Experience and education relevance", 10, relevance_raw),
        ("Readability", 10, readability_raw),
    ]
    breakdown = [
        {
            "name": name,
            "weight": weight,
            "raw_score": round(max(0.0, min(100.0, raw * 100)), 1),
            "weighted_contribution": round(weight * max(0.0, min(1.0, raw)), 2),
        }
        for name, weight, raw in raw_scores
    ]
    score = max(0, min(100, round(sum(item["weighted_contribution"] for item in breakdown))))
    resume_word_count = len(re.findall(r"\b[\w+#.-]+\b", resume))
    suggestions = _suggestions(
        missing_skills, missing_keywords, structure_checks, readability_checks, resume_word_count
    )
    return {
        "ats_score": score,
        "score_breakdown": breakdown,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "structure_checks": structure_checks,
        "readability_checks": readability_checks,
        "suggestions": suggestions,
        "analysis_method": (
            ("spaCy tokenization + " if _SPACY_TOKENIZER is not None else "Regex tokenization + ")
            + "TF-IDF cosine similarity + configurable rule-based skill dictionary"
        ),
        "resume_word_count": resume_word_count,
        "score_formula": (
            "Overall estimate = sum(component raw score × component weight). "
            "Keyword raw score blends 70% coverage of the top job-description terms and "
            "30% TF-IDF cosine similarity. Other components use measurable checklist/coverage rules."
        ),
    }


def serialize_list(value):
    return json.dumps(value, ensure_ascii=False)


def deserialize_list(value):
    return json.loads(value)

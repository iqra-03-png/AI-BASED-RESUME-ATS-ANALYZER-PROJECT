from services.analyzer import analyze_resume, extract_skills


def test_skill_extraction_matches_dictionary_terms(resume_text):
    skills = extract_skills(resume_text)
    assert "python" in skills
    assert "flask" in skills
    assert "sql" in skills


def test_analysis_is_deterministic_and_scores_have_fixed_weights(resume_text, job_description):
    first = analyze_resume(resume_text, job_description)
    second = analyze_resume(resume_text, job_description)
    assert first == second
    assert 0 <= first["ats_score"] <= 100
    assert sum(item["weight"] for item in first["score_breakdown"]) == 100
    assert all(0 <= item["raw_score"] <= 100 for item in first["score_breakdown"])
    assert sum(item["weighted_contribution"] for item in first["score_breakdown"]) <= 100
    assert first["ats_score"] == round(
        sum(item["weighted_contribution"] for item in first["score_breakdown"])
    )


def test_analysis_reports_real_matches_and_missing_terms(resume_text):
    result = analyze_resume(resume_text, "Python, SQL, Kubernetes, cloud infrastructure and security.")
    assert "python" in result["matched_skills"]
    assert "sql" in result["matched_skills"]
    assert "kubernetes" in result["missing_skills"]
    assert result["missing_keywords"]


def test_extreme_inputs_stay_in_score_bounds():
    empty_resume = analyze_resume("", "Python developer role with SQL and cloud experience.")
    matching = analyze_resume(
        "Python SQL cloud developer Python SQL cloud developer. " * 80,
        "Python developer role with SQL and cloud experience.",
    )
    assert empty_resume["ats_score"] == 0
    assert matching["ats_score"] <= 100

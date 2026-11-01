import os


AI_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
)


def provider_ready():
    return any((os.getenv(key) or "").strip() for key in AI_PROVIDER_KEYS)


def _fallback_suggestions(prompt, context):
    prompt_lower = (prompt or "").lower()
    suggestions = [
        "Lead with measurable impact and match the job description's core requirements.",
        "Keep bullet points concise and action-focused, with clear results where possible.",
        "Double-check the resume includes the job-relevant skills, tools, and keywords mentioned in the role.",
    ]
    if "summary" in prompt_lower or "profile" in prompt_lower:
        suggestions = [
            "Open with a short value proposition tied to the role you are targeting.",
            "Mention 2-3 strengths and the business value they create.",
            "Keep the summary specific to the target job rather than listing generic strengths.",
        ]
    if "bullet" in prompt_lower or "experience" in prompt_lower:
        suggestions = [
            "Start each bullet with an action verb and end with a measurable result.",
            "Emphasize scope, tools, and outcomes rather than responsibilities alone.",
            "Translate routine work into impact, such as speed, quality, cost, or user benefit.",
        ]
    if context:
        suggestions.insert(0, f"Use the resume context below as the source of truth: {context[:180]}...")
    return suggestions


def build_resume_context(draft_data=None, report_data=None):
    items = []
    if draft_data:
        for key, value in draft_data.items():
            if isinstance(value, str) and value.strip():
                items.append(f"{key}: {value.strip()}")
    if report_data:
        for key, value in report_data.items():
            if isinstance(value, str) and value.strip():
                items.append(f"{key}: {value.strip()}")
    return "\n".join(items)[:2000]


def build_ai_response(prompt, context=None):
    message = (prompt or "").strip()
    summary = "This app is currently running in local-only mode. Connect a supported AI provider to enable live model responses."
    if provider_ready():
        summary = "Provider settings are present. The app is ready for a real model integration. Until a provider call is configured, the assistant uses the local resume context as a safe, explainable fallback."
    suggestions = _fallback_suggestions(message, context)
    return {
        "status": "provider_ready" if provider_ready() else "local_only",
        "summary": summary,
        "suggestions": suggestions,
        "prompt": message,
    }

TEMPLATE_CATALOG = [
    {
        "id": "free-clean",
        "name": "Clear",
        "tier": "free",
        "industry": "All industries",
        "description": "A clean, single-column layout with conventional headings.",
        "features": ["ATS-friendly", "Single column", "Simple typography"],
        "accent": "blue",
    },
    {
        "id": "free-classic",
        "name": "Classic",
        "tier": "free",
        "industry": "Business & operations",
        "description": "A traditional resume format that prioritizes experience.",
        "features": ["ATS-friendly", "Experience first", "Print-ready"],
        "accent": "green",
    },
    {
        "id": "free-compact",
        "name": "Compact",
        "tier": "free",
        "industry": "Students & early career",
        "description": "A space-efficient format for projects, education, and skills.",
        "features": ["ATS-friendly", "Project focused", "Compact sections"],
        "accent": "slate",
    },
    {
        "id": "premium-modern",
        "name": "Modern Executive",
        "tier": "premium",
        "industry": "Leadership",
        "description": "A polished, executive-style hierarchy for impact and leadership.",
        "features": ["Premium layout", "Leadership highlights", "Impact summary"],
        "accent": "violet",
    },
    {
        "id": "premium-engineering",
        "name": "Engineering Portfolio",
        "tier": "premium",
        "industry": "Software & engineering",
        "description": "Spotlights technical strengths, project outcomes, and experience.",
        "features": ["Technical skills", "Project highlights", "Role-focused"],
        "accent": "cyan",
    },
    {
        "id": "premium-leadership",
        "name": "Leadership Profile",
        "tier": "premium",
        "industry": "Experienced professionals",
        "description": "Emphasizes measurable outcomes, scope, and strategic ownership.",
        "features": ["Achievement-led", "Leadership summary", "Premium layout"],
        "accent": "gold",
    },
    {
        "id": "premium-hr",
        "name": "People & Culture",
        "tier": "premium",
        "industry": "Human resources",
        "description": "Highlights talent, people operations, and HR systems expertise.",
        "features": ["HR-focused", "People operations", "Systems & outcomes"],
        "accent": "rose",
    },
    {
        "id": "premium-creative",
        "name": "Professional Impact",
        "tier": "premium",
        "industry": "Cross-functional professionals",
        "description": "Balances a distinctive visual hierarchy with readable sections.",
        "features": ["Premium layout", "Skill-forward", "Clear hierarchy"],
        "accent": "indigo",
    },
]

PROFILE_GUIDANCE = {
    "Student": {
        "templates": ["Clear", "Compact"],
        "skills": ["Technical skills", "Research", "Communication"],
        "sections": ["Education", "Academic projects", "Internships", "Technical skills"],
        "example": "Built a course project that [result], using [tools] to solve [problem].",
    },
    "Beginner / Fresher": {
        "templates": ["Compact", "Engineering Portfolio"],
        "skills": ["Role-specific tools", "Communication", "Problem solving"],
        "sections": ["Projects", "Certifications", "Internships", "Achievements"],
        "example": "Delivered [project outcome] by applying [skill/tool]; validated the result with [evidence].",
    },
    "Software Engineer": {
        "templates": ["Engineering Portfolio", "Clear"],
        "skills": ["Programming languages", "Frameworks", "Testing", "Cloud"],
        "sections": ["Technical skills", "Experience", "Selected projects", "Education"],
        "example": "Improved [service/process] by [measurable result] using [language/framework].",
    },
    "Experienced Professional": {
        "templates": ["Leadership Profile", "Modern Executive"],
        "skills": ["Leadership", "Strategy", "Role-specific expertise"],
        "sections": ["Professional experience", "Selected achievements", "Skills", "Education"],
        "example": "Led [initiative] across [scope], improving [metric] by [result].",
    },
    "Senior Engineer": {
        "templates": ["Engineering Portfolio", "Leadership Profile"],
        "skills": ["System design", "Technical leadership", "Mentoring", "Reliability"],
        "sections": ["Technical leadership", "Architecture", "Impact", "Experience"],
        "example": "Designed [system] for [scale], reducing [cost/latency] by [measured result].",
    },
    "HR Professional": {
        "templates": ["People & Culture", "Modern Executive"],
        "skills": ["Recruitment", "Employee relations", "HR systems", "People analytics"],
        "sections": ["People operations", "Recruitment", "HR systems", "Employee experience"],
        "example": "Improved [people metric] by [result] through [program/process] across [team size].",
    },
    "Manager": {
        "templates": ["Modern Executive", "Leadership Profile"],
        "skills": ["People management", "Planning", "Delivery", "Stakeholder communication"],
        "sections": ["Leadership experience", "Team outcomes", "Strategy", "Core skills"],
        "example": "Managed [team/scope] to deliver [business outcome] within [timeframe].",
    },
    "Other Professional": {
        "templates": ["Clear", "Modern Executive"],
        "skills": ["Role-specific expertise", "Communication", "Measurable impact"],
        "sections": ["Summary", "Professional experience", "Skills", "Education"],
        "example": "Applied [expertise] to [challenge], achieving [specific outcome].",
    },
}

RESUME_FIELDS = {
    "full_name": ("Full name", 100),
    "email": ("Email", 254),
    "phone": ("Phone", 40),
    "location": ("Location", 120),
    "headline": ("Professional headline", 160),
    "summary": ("Professional summary", 3000),
    "skills": ("Skills", 3000),
    "experience": ("Experience", 8000),
    "education": ("Education", 5000),
    "projects": ("Projects", 6000),
    "certifications": ("Certifications", 3000),
    "achievements": ("Achievements", 3000),
}


def template_by_id(template_id):
    return next((template for template in TEMPLATE_CATALOG if template["id"] == template_id), None)


TEMPLATE_SECTION_ORDER = {
    "free-clean": ["summary", "skills", "experience", "projects", "education", "certifications", "achievements"],
    "free-classic": ["summary", "experience", "education", "skills", "projects", "certifications", "achievements"],
    "free-compact": ["education", "skills", "projects", "experience", "certifications", "achievements", "summary"],
    "premium-modern": ["summary", "achievements", "experience", "skills", "education", "projects", "certifications"],
    "premium-engineering": ["skills", "projects", "experience", "education", "certifications", "achievements", "summary"],
    "premium-leadership": ["summary", "achievements", "experience", "education", "skills", "projects", "certifications"],
    "premium-hr": ["summary", "experience", "skills", "achievements", "education", "certifications", "projects"],
    "premium-creative": ["summary", "projects", "skills", "experience", "education", "achievements", "certifications"],
}

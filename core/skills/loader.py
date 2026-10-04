from pathlib import Path


SKILLS_DIR = Path("/home/bruno/local-agent/skills")


SKILL_KEYWORDS = {
    "development": [
        "desenvolvimento",
        "specs",
        "projeto.md",
        "checklist",
        "continue",
        "harness",
        "etapa",
    ],
    "environment": [
        "ambiente",
        "ferramentas",
        "instalar",
        "dependências",
        "dependencias",
    ],
    "linux": [
        "linux",
        "fedora",
        "sistema",
        "dnf",
        "rpm",
        "kernel",
        "vram",
        "memória",
        "memoria",
    ],
    "github": [
        "github",
        "repositório",
        "repositorio",
        "release",
        "releases",
        "git",
    ],
    "models": [
        "modelo",
        "modelos",
        "smart",
        "candidato",
        "seleção de modelo",
        "selecionar modelo",
        "quantiz",
        "ollama",
        "llama",
        "gguf",
        "benchmark",
        "model registry",
        "registry",
    ],
}


def list_skills() -> list[str]:
    if not SKILLS_DIR.exists():
        return []

    return sorted(
        path.name
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    )


def load_skill(name: str) -> dict:
    skill_path = SKILLS_DIR / name / "SKILL.md"

    if not skill_path.exists():
        return {
            "success": False,
            "error": f"Skill não encontrada: {name}",
        }

    try:
        content = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao ler Skill '{name}': {e}",
        }

    return {
        "success": True,
        "name": name,
        "path": str(skill_path),
        "content": content,
    }


def load_skills(names: list[str]) -> dict:
    skills = []

    for name in names:
        result = load_skill(name)

        if not result["success"]:
            return result

        skills.append(result)

    return {
        "success": True,
        "skills": skills,
    }


def match_skills(
    prompt: str,
    current_phase: str | None = None,
    next_action: str | None = None,
) -> list[str]:
    """
    Identifica automaticamente quais Skills são relevantes para um prompt,
    fase atual do projeto ou pendência imediata.
    """
    combined_parts = [prompt]
    if current_phase:
        combined_parts.append(current_phase)
    if next_action:
        combined_parts.append(next_action)

    text = " ".join(combined_parts).lower()
    matched = set()

    for skill_name, keywords in SKILL_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.add(skill_name)

    available = set(list_skills())
    return sorted(list(matched.intersection(available)))


def format_skills_context(skills: list[dict]) -> str:
    """
    Formata o conteúdo de múltiplas Skills para inserção no contexto do modelo.
    """
    if not skills:
        return ""

    blocks = []
    for s in skills:
        blocks.append(f"""
=========================================================
SKILL: {s['name'].upper()}
=========================================================
{s['content']}
=========================================================
FIM DA SKILL: {s['name'].upper()}
=========================================================
""")
    return "\n".join(blocks)

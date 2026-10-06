import re
from pathlib import Path

from core.paths import SKILLS_DIR
from core.skills.frontmatter import parse_frontmatter

# Orçamento de caracteres de Skills no prompt do sistema (~2,3k tokens).
# O que passar disso entra só como índice; o modelo lê o resto com load_skill.
SKILLS_BUDGET_CHARS = 7000

SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,60}$")



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
    "windows": [
        "windows",
        "powershell",
        "winget",
        "choco",
        "scoop",
        "systeminfo",
        "win32",
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


def all_skill_keywords() -> dict[str, list[str]]:
    """Gatilhos fixos das Skills nativas + gatilhos declarados no cabeçalho das demais."""

    keywords = {name: list(words) for name, words in SKILL_KEYWORDS.items()}

    if not SKILLS_DIR.exists():
        return keywords

    for path in SKILLS_DIR.iterdir():
        skill_file = path / "SKILL.md"

        if not path.is_dir() or not skill_file.exists():
            continue

        try:
            meta, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        declared = [t.lower() for t in meta.get("triggers", [])]

        if declared:
            keywords.setdefault(path.name, [])
            keywords[path.name] = sorted(set(keywords[path.name]) | set(declared))

    return keywords


def describe_skill(name: str, content: str) -> str:
    """Descrição curta: campo 'description' do cabeçalho ou o primeiro título."""

    meta, body = parse_frontmatter(content)

    if meta.get("description"):
        return meta["description"]

    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()

    return name


def list_skills() -> list[str]:
    if not SKILLS_DIR.exists():
        return []

    return sorted(
        path.name
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    )


def load_skill(name: str) -> dict:
    if not isinstance(name, str) or not SKILL_NAME_PATTERN.match(name):
        return {
            "success": False,
            "error": f"Nome de Skill inválido: {name}",
        }

    skill_path = SKILLS_DIR / name / "SKILL.md"

    if not skill_path.exists():
        return {
            "success": False,
            "error": f"Skill não encontrada: {name}",
        }

    try:
        raw = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao ler Skill '{name}': {e}",
        }

    meta, body = parse_frontmatter(raw)

    return {
        "success": True,
        "name": name,
        "path": str(skill_path),
        "description": describe_skill(name, raw),
        "content": body if meta else raw,
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

    for skill_name, keywords in all_skill_keywords().items():
        if any(kw in text for kw in keywords):
            matched.add(skill_name)

    available = set(list_skills())
    return sorted(list(matched.intersection(available)))


def format_skills_context(skills: list[dict], budget_chars: int | None = None) -> str:
    """
    Formata o conteúdo de múltiplas Skills para inserção no contexto do modelo.

    Com budget_chars, as Skills são incluídas por inteiro enquanto couberem; as
    demais entram só como uma linha de índice (nome e descrição) e o modelo pode
    ler o texto completo com a ferramenta load_skill.
    """
    if not skills:
        return ""

    blocks = []
    index_lines = []
    used = 0

    for s in skills:
        size = len(s["content"])

        if budget_chars is not None and used + size > budget_chars:
            index_lines.append(
                f"- {s['name']}: {s.get('description') or s['name']} "
                f"(use a ferramenta load_skill com name=\"{s['name']}\" para ler)"
            )
            continue

        used += size

        blocks.append(f"""
=========================================================
SKILL: {s['name'].upper()}
=========================================================
{s['content']}
=========================================================
FIM DA SKILL: {s['name'].upper()}
=========================================================
""")

    if index_lines:
        blocks.append(
            "\nSKILLS DISPONÍVEIS SOB DEMANDA (não carregadas para poupar contexto):\n"
            + "\n".join(index_lines)
            + "\n"
        )

    return "\n".join(blocks)

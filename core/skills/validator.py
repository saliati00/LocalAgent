"""Validação determinística de Skills propostas pelo agente."""

import re

from core.skills.frontmatter import parse_frontmatter

MAX_SKILL_CHARS = 2400
MAX_DESCRIPTION_CHARS = 160
MAX_TRIGGERS = 12

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")

REQUIRED_SECTIONS = (
    "## Quando usar",
    "## Passos",
    "## Como validar",
    "## Limites",
)

ALLOWED_ORIGINS = {"agent", "human"}

# Trechos que tentam enfraquecer as regras do Harness. Uma Skill é instrução
# persistente: não pode mandar o modelo ignorar permissões ou restrições.
# O segundo valor indica se a frase pode ser aceita quando for negada
# ("Não baixa nada sem confirmação" é uma restrição, não uma brecha).
FORBIDDEN_PATTERNS = (
    (r"ignor\w*\s+(todas\s+)?(as\s+)?(regras|restri[cç][õo]es|instru[cç][õo]es|permiss[õo]es)", True),
    (r"ignore\s+(all\s+|any\s+)?(previous|prior|above|the)\s+(rules|instructions|restrictions)", True),
    (r"disregard", True),
    (r"desativ\w*\s+(a\s+|o\s+)?(confirma[cç][aã]o|permission|permiss[aã]o|seguran[cç]a)", True),
    (r"sem\s+(pedir\s+)?confirma[cç][aã]o", True),
    (r"burl\w+", True),
    (r"contorn\w+\s+(o\s+|a\s+)?(permission|permiss|restri|harness|bloqueio)", True),
    (r"allow_install|allow_system_changes|allow_destructive", False),
    (r"sudo\s+sem", True),
    (r"system\s+prompt", False),
    (r"\|\s*(sh|bash|powershell|pwsh|iex)\b", False),
    (r"invoke-expression|\biex\b", False),
)

# Caracteres invisíveis usados para esconder instruções (zero-width, bidi, tags Unicode).
INVISIBLE_CHARS = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
)
BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)

NEGATIONS = re.compile(r"\b(n[aã]o|nunca|jamais|nem|never|don't|do not)\b")


def _is_negated(text: str, match_start: int) -> bool:
    """True se há uma negação antes do trecho, na mesma frase/linha."""

    sentence_start = max(
        text.rfind(".", 0, match_start),
        text.rfind("\n", 0, match_start),
        text.rfind(";", 0, match_start),
    ) + 1

    return bool(NEGATIONS.search(text[sentence_start:match_start]))


def validate_skill_text(name: str, text: str, known_tools: set[str] | None = None) -> tuple[bool, list[str]]:
    """
    Retorna (ok, erros). Não avalia a qualidade do conteúdo, só a forma e
    os limites de segurança.
    """

    errors: list[str] = []

    if not NAME_PATTERN.match(name or ""):
        errors.append("Nome inválido: use minúsculas, números e hífen (2 a 41 caracteres).")

    if len(text) > MAX_SKILL_CHARS:
        errors.append(f"Skill grande demais: {len(text)} caracteres (máximo {MAX_SKILL_CHARS}).")

    meta, body = parse_frontmatter(text)

    if not meta:
        errors.append("Cabeçalho (--- ... ---) ausente.")
        return False, errors

    if meta.get("name") != name:
        errors.append(f"O campo 'name' do cabeçalho deve ser '{name}'.")

    description = meta.get("description", "")
    if not description:
        errors.append("Campo 'description' obrigatório.")
    elif len(description) > MAX_DESCRIPTION_CHARS:
        errors.append(f"'description' acima de {MAX_DESCRIPTION_CHARS} caracteres.")

    triggers = meta.get("triggers") or []
    if not triggers:
        errors.append("Informe ao menos um gatilho em 'triggers'.")
    elif len(triggers) > MAX_TRIGGERS:
        errors.append(f"No máximo {MAX_TRIGGERS} gatilhos.")
    elif any(len(t) < 3 for t in triggers):
        errors.append("Cada gatilho precisa ter ao menos 3 caracteres.")

    if meta.get("origin") not in ALLOWED_ORIGINS:
        errors.append("Campo 'origin' deve ser 'agent' ou 'human'.")

    if known_tools is not None:
        unknown = [t for t in (meta.get("tools") or []) if t not in known_tools]
        if unknown:
            errors.append(f"Tools inexistentes em 'tools': {unknown}")

    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"Seção obrigatória ausente: '{section}'.")

    # O BOM inicial é tolerado; qualquer outro caractere invisível não.
    if INVISIBLE_CHARS.search(text.lstrip("\ufeff")):
        errors.append("Caracteres invisíveis (Unicode oculto) não são permitidos em Skills.")

    if BASE64_BLOB.search(text):
        errors.append("Trecho que parece base64/codificado (40+ caracteres seguidos) não é permitido.")

    if URL_PATTERN.search(text):
        errors.append("URLs não são permitidas em rascunhos de Skills; o usuário pode adicioná-las após revisar.")

    lowered = text.lower()
    for pattern, negatable in FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, lowered):
            if negatable and _is_negated(lowered, match.start()):
                continue

            errors.append(f"Trecho proibido (tenta enfraquecer regras do Harness): '{match.group(0)}'.")
            break

    return not errors, errors

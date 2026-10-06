"""
Ciclo de vida de Skills criadas pelo agente: rascunho -> revisão humana -> ativa.

O agente só consegue gravar em skills_pending/ (via propose_skill). Mover uma
Skill para skills/ (promover) é uma ação humana, feita por scripts/promote_skill.py.
skills/ e skills_pending/ são protegidos contra write_file/replace_in_file.
"""

import shutil
from datetime import datetime
from pathlib import Path

from core.paths import SKILLS_DIR, SKILLS_PENDING_DIR
from core.skills.frontmatter import parse_frontmatter, render_frontmatter
from core.skills.validator import validate_skill_text

REJECTED_DIRNAME = "_rejected"


def _known_tools() -> set[str]:
    from tools.manager import TOOLS

    return set(TOOLS)


def _as_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        value = [v for v in value.replace(";", ",").split(",")]

    return [str(item).strip() for item in value if str(item).strip()]


def build_skill_text(
    name: str,
    description: str,
    triggers,
    when_to_use: str,
    steps,
    validation: str,
    limits: str,
    tools=None,
    used_web: bool = False,
    source_task: str = "",
) -> str:
    meta = {
        "name": name,
        "description": " ".join(str(description).split()),
        "triggers": _as_list(triggers),
        "tools": _as_list(tools),
        "origin": "agent",
        "status": "pending",
        "used_web": bool(used_web),
        "source_task": " ".join(str(source_task).split())[:120],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    numbered = "\n".join(
        f"{index}. {' '.join(str(step).split())}"
        for index, step in enumerate(_as_list(steps), start=1)
    )

    body = (
        f"# Skill: {name}\n\n"
        f"## Quando usar\n{str(when_to_use).strip()}\n\n"
        f"## Passos\n{numbered}\n\n"
        f"## Como validar\n{str(validation).strip()}\n\n"
        f"## Limites\n{str(limits).strip()}\n"
    )

    return render_frontmatter(meta) + "\n" + body


def propose_skill(
    name: str,
    description: str,
    triggers,
    when_to_use: str,
    steps,
    validation: str,
    limits: str,
    tools=None,
    used_web: bool = False,
    source_task: str = "",
) -> dict:
    """Grava uma Skill como RASCUNHO em skills_pending/. Não a ativa."""

    name = (name or "").strip()

    text = build_skill_text(
        name, description, triggers, when_to_use, steps, validation, limits,
        tools=tools, used_web=used_web, source_task=source_task,
    )

    ok, errors = validate_skill_text(name, text, known_tools=_known_tools())

    if not ok:
        return {
            "success": False,
            "error": "Skill recusada pelo validador: " + " ".join(errors),
            "validation_errors": errors,
        }

    if (SKILLS_DIR / name).exists():
        return {
            "success": False,
            "error": f"Já existe uma Skill ativa chamada '{name}'. Proponha outro nome (ex.: '{name}-v2').",
        }

    target_dir = SKILLS_PENDING_DIR / name

    if target_dir.exists():
        return {
            "success": False,
            "error": f"Já existe um rascunho chamado '{name}' aguardando revisão.",
        }

    target_dir.mkdir(parents=True)
    (target_dir / "SKILL.md").write_text(text, encoding="utf-8")

    return {
        "success": True,
        "path": str(target_dir / "SKILL.md"),
        "status": "pending",
        "used_web": bool(used_web),
        "notice": (
            "Skill gravada como rascunho. Ela só entra em uso depois que o usuário a revisar "
            "e promover (python scripts/promote_skill.py promote " + name + ")."
        ),
    }


def list_pending() -> list[dict]:
    if not SKILLS_PENDING_DIR.exists():
        return []

    items = []

    for path in sorted(SKILLS_PENDING_DIR.iterdir()):
        skill_file = path / "SKILL.md"

        if not path.is_dir() or path.name.startswith("_") or not skill_file.exists():
            continue

        meta, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))

        items.append({
            "name": path.name,
            "description": meta.get("description", ""),
            "used_web": bool(meta.get("used_web", False)),
            "created_at": meta.get("created_at", ""),
        })

    return items


def read_pending(name: str) -> dict:
    skill_file = SKILLS_PENDING_DIR / name / "SKILL.md"

    if not skill_file.exists():
        return {"success": False, "error": f"Rascunho não encontrado: {name}"}

    text = skill_file.read_text(encoding="utf-8")
    ok, errors = validate_skill_text(name, text, known_tools=_known_tools())
    meta, _ = parse_frontmatter(text)

    return {
        "success": True,
        "name": name,
        "text": text,
        "valid": ok,
        "errors": errors,
        "used_web": bool(meta.get("used_web", False)),
    }


def promote_skill(name: str) -> dict:
    """
    Move skills_pending/<name> para skills/<name> e marca como ativa.

    Chamada somente pelo script humano; revalida antes de promover.
    """

    info = read_pending(name)

    if not info["success"]:
        return info

    if not info["valid"]:
        return {
            "success": False,
            "error": "O rascunho não passa mais na validação: " + " ".join(info["errors"]),
        }

    if (SKILLS_DIR / name).exists():
        return {"success": False, "error": f"Já existe uma Skill ativa chamada '{name}'."}

    meta, body = parse_frontmatter(info["text"])
    meta["status"] = "active"
    meta["promoted_at"] = datetime.now().isoformat(timespec="seconds")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    destination = SKILLS_DIR / name
    destination.mkdir()
    (destination / "SKILL.md").write_text(render_frontmatter(meta) + "\n" + body, encoding="utf-8")

    shutil.rmtree(SKILLS_PENDING_DIR / name)

    return {"success": True, "path": str(destination / "SKILL.md")}


def reject_skill(name: str) -> dict:
    """Move o rascunho para skills_pending/_rejected/ (não apaga)."""

    source = SKILLS_PENDING_DIR / name

    if not (source / "SKILL.md").exists():
        return {"success": False, "error": f"Rascunho não encontrado: {name}"}

    rejected_root = SKILLS_PENDING_DIR / REJECTED_DIRNAME
    rejected_root.mkdir(parents=True, exist_ok=True)

    destination = rejected_root / f"{name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.move(str(source), str(destination))

    return {"success": True, "path": str(destination)}

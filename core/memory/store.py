import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MEMORY_DIR = Path("/home/bruno/local-agent/memory")
DEFAULT_MEMORY_FILE = DEFAULT_MEMORY_DIR / "store.json"


class MemoryStore:
    """
    Sistema de Memória Persistente do Harness.

    Permite registrar e consultar fatos verificados sobre:
    - environment: ferramentas instaladas, caminhos, versões e hardware;
    - decisions: decisões arquiteturais e operacionais consolidadas;
    - progress: marcos e etapas concluídas pelo agente;
    - notes: notas contextuais e lembretes para tarefas longas.
    """

    def __init__(self, file_path: Path | str | None = None):
        if file_path is None:
            self.file_path = DEFAULT_MEMORY_FILE
        else:
            self.file_path = Path(file_path).expanduser().resolve()

        self._data: dict[str, dict[str, dict[str, Any]]] = self._load()

    def _load(self) -> dict:
        if not self.file_path.exists():
            return {
                "environment": {},
                "decisions": {},
                "progress": {},
                "notes": {},
            }

        try:
            content = self.file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            for cat in ["environment", "decisions", "progress", "notes"]:
                if cat not in data:
                    data[cat] = {}
            return data
        except Exception:
            return {
                "environment": {},
                "decisions": {},
                "progress": {},
                "notes": {},
            }

    def save(self) -> bool:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def set(
        self,
        category: str,
        key: str,
        value: Any,
        description: str = "",
    ) -> dict:
        cat_key = category.strip().lower()
        if cat_key not in self._data:
            self._data[cat_key] = {}

        now = datetime.now().isoformat()
        entry = {
            "key": key.strip(),
            "value": value,
            "description": description.strip(),
            "updated_at": now,
        }

        self._data[cat_key][key.strip()] = entry
        self.save()
        return {
            "success": True,
            "category": cat_key,
            "key": key.strip(),
            "entry": entry,
        }

    def get(self, category: str, key: str, default: Any = None) -> Any:
        cat_key = category.strip().lower()
        entry = self._data.get(cat_key, {}).get(key.strip())
        if entry is not None:
            return entry.get("value")
        return default

    def get_entry(self, category: str, key: str) -> dict | None:
        cat_key = category.strip().lower()
        return self._data.get(cat_key, {}).get(key.strip())

    def get_category(self, category: str) -> dict:
        cat_key = category.strip().lower()
        return self._data.get(cat_key, {})

    def get_all(self) -> dict:
        return self._data

    def delete(self, category: str, key: str) -> bool:
        cat_key = category.strip().lower()
        if cat_key in self._data and key.strip() in self._data[cat_key]:
            del self._data[cat_key][key.strip()]
            self.save()
            return True
        return False

    def clear_category(self, category: str) -> bool:
        cat_key = category.strip().lower()
        if cat_key in self._data:
            self._data[cat_key] = {}
            self.save()
            return True
        return False

    def format_context(self, categories: list[str] | None = None) -> str:
        """
        Formata memórias persistentes em um resumo conciso para injeção no prompt do sistema.
        """
        cats_to_include = categories or ["environment", "decisions", "progress"]
        sections = []

        for cat in cats_to_include:
            entries = self._data.get(cat, {})
            if not entries:
                continue

            lines = [f"[{cat.upper()}]:"]
            for k, item in entries.items():
                val = item.get("value")
                desc = item.get("description")
                if desc:
                    lines.append(f"- {k}: {val} ({desc})")
                else:
                    lines.append(f"- {k}: {val}")

            sections.append("\n".join(lines))

        if not sections:
            return ""

        body = "\n\n".join(sections)
        return f"""
=========================================================
MEMÓRIA PERSISTENTE DO AGENTE (FATOS JÁ VALIDADOS)
=========================================================
{body}
=========================================================
"""

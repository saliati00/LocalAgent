import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.paths import MEMORY_DIR

DEFAULT_MEMORY_DIR = MEMORY_DIR
DEFAULT_MEMORY_FILE = DEFAULT_MEMORY_DIR / "store.json"

# Limites da memória persistente: ela entra no prompt de uma janela pequena, então precisa ser enxuta.
MAX_KEY_CHARS = 60
MAX_VALUE_CHARS = 400
MAX_DESCRIPTION_CHARS = 160
MAX_ENTRIES_PER_CATEGORY = 40


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
        clean_key = key.strip()
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        refusal = None

        if not clean_key:
            refusal = "A chave da memória não pode ser vazia."
        elif len(clean_key) > MAX_KEY_CHARS:
            refusal = f"A chave tem {len(clean_key)} caracteres; o limite é {MAX_KEY_CHARS}. Use um nome curto."
        elif len(text) > MAX_VALUE_CHARS:
            refusal = (
                f"O valor tem {len(text)} caracteres; o limite é {MAX_VALUE_CHARS}. A memória entra no prompt de uma janela pequena: "
                "guarde só o fato essencial (o resto vai em arquivo)."
            )
        elif len(description.strip()) > MAX_DESCRIPTION_CHARS:
            refusal = f"A descrição tem {len(description.strip())} caracteres; o limite é {MAX_DESCRIPTION_CHARS}."
        elif clean_key not in self._data.get(cat_key, {}) and len(self._data.get(cat_key, {})) >= MAX_ENTRIES_PER_CATEGORY:
            refusal = (
                f"A categoria '{cat_key}' já tem {MAX_ENTRIES_PER_CATEGORY} entradas (o máximo). "
                "Apague entradas antigas antes de guardar novas."
            )

        if refusal:
            return {"success": False, "error": refusal, "tool_error": True}

        if cat_key not in self._data:
            self._data[cat_key] = {}

        now = datetime.now().isoformat()
        entry = {
            "key": clean_key,
            "value": value,
            "description": description.strip(),
            "updated_at": now,
        }

        # Decisões moldam o comportamento futuro: só entram no contexto depois que o USUÁRIO as revisa.
        if cat_key == "decisions":
            entry["reviewed"] = False

        self._data[cat_key][clean_key] = entry
        self.save()
        result = {
            "success": True,
            "category": cat_key,
            "key": clean_key,
            "entry": entry,
        }

        if cat_key == "decisions":
            result["notice"] = (
                "Decisão registrada, mas AGUARDA REVISÃO do usuário: só entra no contexto depois de aprovada "
                "(python scripts\\revisar_memoria.py)."
            )

        return result

    def pending_review(self) -> list[dict]:
        """Decisões ainda não revisadas pelo usuário (entradas antigas, sem o campo, contam como revisadas)."""

        return [item for item in self._data.get("decisions", {}).values() if not item.get("reviewed", True)]

    def review(self, key: str, approve: bool) -> bool:
        """Aprova (passa a valer no contexto) ou rejeita (apaga) uma decisão pendente."""

        entry = self._data.get("decisions", {}).get(key.strip())

        if entry is None:
            return False

        if approve:
            entry["reviewed"] = True
            self.save()
            return True

        return self.delete("decisions", key)

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

    @staticmethod
    def _format_entry(key: str, item: dict) -> str:
        value = item.get("value")
        desc = item.get("description")

        if desc:
            return f"- {key}: {value} ({desc})"

        return f"- {key}: {value}"

    def format_context(
        self,
        categories: list[str] | None = None,
        max_chars: int | None = None,
    ) -> str:
        """
        Formata memórias persistentes em um resumo conciso para injeção no prompt do sistema.
        """
        cats_to_include = categories or ["environment", "decisions", "progress"]

        # Com teto, entram primeiro as entradas mais recentes; as antigas (que podem
        # estar defasadas) são descartadas até caber.
        allowed = None

        if max_chars is not None:
            candidates = []

            for cat in cats_to_include:
                for k, item in self._data.get(cat, {}).items():
                    if not item.get("reviewed", True):
                        continue

                    candidates.append((item.get("updated_at") or "", cat, k, self._format_entry(k, item)))

            candidates.sort(key=lambda row: row[0], reverse=True)

            allowed = set()
            used = 0

            for _, cat, k, line in candidates:
                if used + len(line) + 1 > max_chars:
                    continue

                allowed.add((cat, k))
                used += len(line) + 1

        sections = []

        for cat in cats_to_include:
            entries = self._data.get(cat, {})
            if not entries:
                continue

            lines = [f"[{cat.upper()}]:"]
            for k, item in entries.items():
                if not item.get("reviewed", True):
                    continue  # decisão pendente de revisão não vai para o prompt

                if allowed is not None and (cat, k) not in allowed:
                    continue

                lines.append(self._format_entry(k, item))

            if len(lines) > 1:
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

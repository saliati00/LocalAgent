"""Memoização de ferramentas de leitura dentro de uma tarefa."""

import json

READ_ONLY_TOOLS = {
    "get_model_registry",
    "get_project_status",
    "get_memory",
    "list_directory",
    "read_file",
    "check_tools",
}

CACHE_NOTICE = (
    "Resultado idêntico ao da consulta anterior: nada mudou desde então. "
    "Não repita esta consulta; use a informação já obtida ou execute a próxima ação."
)


class ToolMemo:
    """
    Guarda resultados de ferramentas somente-leitura.

    Qualquer chamada a uma ferramenta que possa alterar estado (escrita, comando,
    memória, checklist, registry) invalida todo o cache.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self.hits = 0

    @staticmethod
    def _key(name: str, arguments: dict) -> str:
        return name + "|" + json.dumps(arguments or {}, sort_keys=True, default=str)

    def lookup(self, name: str, arguments: dict) -> dict | None:
        if name not in READ_ONLY_TOOLS:
            return None

        cached = self._cache.get(self._key(name, arguments))

        if cached is None:
            return None

        self.hits += 1

        return {**cached, "cached": True, "notice": CACHE_NOTICE}

    def record(self, name: str, arguments: dict, result: dict) -> None:
        if name not in READ_ONLY_TOOLS:
            self._cache.clear()
            return

        if isinstance(result, dict) and result.get("success"):
            self._cache[self._key(name, arguments)] = dict(result)

    def clear(self) -> None:
        self._cache.clear()

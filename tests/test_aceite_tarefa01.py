"""Aceite da tarefa 01. Rodar: pytest -m aceite tests/test_aceite_tarefa01.py -q"""

import re

import pytest

from core.paths import WORKSPACE_DIR

pytestmark = pytest.mark.aceite

ARQUIVO = WORKSPACE_DIR / "tarefa-01" / "ambiente.md"
FERRAMENTAS = ["python", "git", "ollama", "nvidia-smi", "cmake"]


def test_arquivo_existe():
    assert ARQUIVO.exists(), "Crie workspace/tarefa-01/ambiente.md"


def test_titulo_e_uma_linha_por_ferramenta():
    texto = ARQUIVO.read_text(encoding="utf-8")

    assert texto.lstrip().startswith("# Ambiente")

    for nome in FERRAMENTAS:
        linha = re.search(rf"^- {re.escape(nome)}: (.+)$", texto, re.MULTILINE)

        assert linha, f"Falta a linha '- {nome}: <valor>'"
        assert linha.group(1).strip() not in {"", "<versão>", "<versão ou não encontrado>"}, (
            f"A linha de {nome} ainda está com o texto de exemplo"
        )


def test_versoes_com_numero_quando_encontradas():
    texto = ARQUIVO.read_text(encoding="utf-8")

    for nome in ("python", "git"):
        valor = re.search(rf"^- {nome}: (.+)$", texto, re.MULTILINE).group(1)

        assert "não encontrado" in valor.lower() or re.search(r"\d+\.\d+", valor), (
            f"A versão de {nome} deveria conter números (ex.: 3.12.4)"
        )

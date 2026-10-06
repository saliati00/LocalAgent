"""Aceite da tarefa 02. Rodar: pytest -m aceite tests/test_aceite_tarefa02.py -q"""

import json

import pytest

from core.paths import PROJECT_ROOT

pytestmark = pytest.mark.aceite

PASTA = PROJECT_ROOT / "scripts" / "eval" / "tarefas"
FORMATO = PROJECT_ROOT / "scripts" / "eval" / "FORMATO.md"
TIPOS = {
    "file_exists": {"path"},
    "file_contains": {"path", "text"},
    "command_exit_zero": {"command"},
}


def carregar():
    arquivos = sorted(PASTA.glob("*.json"))
    assert arquivos, "Crie arquivos .json em scripts/eval/tarefas/"
    return [(arquivo, json.loads(arquivo.read_text(encoding="utf-8"))) for arquivo in arquivos]


def caminho_seguro(caminho: str) -> bool:
    return bool(caminho) and not caminho.startswith(("/", "\\")) and ":" not in caminho and ".." not in caminho.split("/")


def test_formato_documentado():
    assert FORMATO.exists() and len(FORMATO.read_text(encoding="utf-8").strip()) > 200, (
        "Crie scripts/eval/FORMATO.md explicando o formato"
    )


def test_pelo_menos_cinco_tarefas_com_ids_unicos():
    tarefas = carregar()

    assert len(tarefas) >= 5
    ids = [dados.get("id") for _, dados in tarefas]
    assert all(isinstance(i, str) and i for i in ids)
    assert len(set(ids)) == len(ids), "Há ids repetidos"


def test_campos_obrigatorios():
    for arquivo, dados in carregar():
        for campo in ("id", "titulo", "prompt", "aceite"):
            assert campo in dados, f"{arquivo.name}: falta o campo '{campo}'"

        assert isinstance(dados["prompt"], str) and dados["prompt"].strip(), f"{arquivo.name}: prompt vazio"
        assert isinstance(dados["aceite"], list) and dados["aceite"], f"{arquivo.name}: aceite vazio"

        if "max_iteracoes" in dados:
            assert isinstance(dados["max_iteracoes"], int) and dados["max_iteracoes"] > 0


def test_criterios_de_aceite_validos():
    for arquivo, dados in carregar():
        for criterio in dados["aceite"]:
            tipo = criterio.get("type")

            assert tipo in TIPOS, f"{arquivo.name}: tipo inválido '{tipo}'"

            faltando = TIPOS[tipo] - set(criterio)
            assert not faltando, f"{arquivo.name}: critério {tipo} sem {faltando}"

            if "path" in criterio:
                assert caminho_seguro(criterio["path"]), f"{arquivo.name}: caminho inseguro {criterio['path']}"


def test_setup_usa_caminhos_seguros():
    for arquivo, dados in carregar():
        for caminho in dados.get("setup", {}):
            assert caminho_seguro(caminho), f"{arquivo.name}: caminho inseguro no setup: {caminho}"

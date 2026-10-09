"""
Tarefas REALISTAS de desenvolvimento para a bateria (não são testes sintéticos de ferramenta).

Cada tarefa é um mini-projeto Python com um pedido escrito como um usuário escreveria. O veredito vem
de código: um teste oculto (escrito só depois que o agente termina), a execução do programa ou um teste
de mutação. Nada é julgado por um modelo.

Cada tarefa tem:
  id, prompt, files (arquivos iniciais, relativos à pasta da tarefa), check(folder) -> (bool, detalhe)
  e solution (arquivos de uma solução correta; usada só nos testes do próprio verificador).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REAL_DIR = "workspace/bateria/real"
RUN_TIMEOUT = 90
EMPTY_PYTEST_INI = "[pytest]\n"


def run_python(folder: Path, *args: str, timeout: int = RUN_TIMEOUT) -> tuple[int, str]:
    try:
        done = subprocess.run([sys.executable, *args], cwd=str(folder), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              env={**os.environ, "PYTHONUTF8": "1"})
        return done.returncode, (done.stdout + done.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "tempo limite excedido ao executar"
    except OSError as exc:
        return 1, str(exc)


def run_pytest(folder: Path, target: str) -> tuple[bool, str]:
    """pytest isolado da configuração do projeto (pytest.ini vazio na pasta da tarefa)."""

    ini = folder / "pytest.ini"

    if not ini.exists():
        ini.write_text(EMPTY_PYTEST_INI, encoding="utf-8")

    code, output = run_python(folder, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", str(ini), "--rootdir", str(folder), target)
    last = output.splitlines()[-1] if output else ""

    return code == 0, last


def read(folder: Path, name: str) -> str | None:
    try:
        return (folder / name).read_text(encoding="utf-8")
    except OSError:
        return None


def hidden_tests(folder: Path, code: str, protect: dict[str, str] | None = None) -> tuple[bool, str]:
    """Roda um teste oculto contra o código do agente e confere que os arquivos protegidos não mudaram."""

    for name, original in (protect or {}).items():
        if read(folder, name) != original:
            return False, f"{name} foi alterado ou apagado (o pedido era não mexer nele)"

    (folder / "aceite_oculto.py").write_text(code, encoding="utf-8")
    passed, last = run_pytest(folder, "aceite_oculto.py")

    return passed, "testes ocultos passaram" if passed else f"testes ocultos falharam: {last}"


# ---------------------------------------------------------------- 1. corrigir-soma
CALC = '''def soma_ate(n):
    """Soma de 1 até n, inclusive."""
    return sum(range(1, n))


def media(valores):
    """Média aritmética de uma lista não vazia."""
    return sum(valores) / (len(valores) + 1)
'''
TEST_CALC = '''from calc import media, soma_ate


def test_soma_ate():
    assert soma_ate(4) == 10


def test_media():
    assert media([2, 4, 6]) == 4
'''


def check_corrigir_soma(folder):
    return hidden_tests(folder, '''from calc import media, soma_ate


def test_extra():
    assert soma_ate(1) == 1
    assert soma_ate(10) == 55
    assert soma_ate(0) == 0
    assert media([10]) == 10
    assert media([1, 2]) == 1.5


def test_visivel():
    assert soma_ate(4) == 10
    assert media([2, 4, 6]) == 4
''', protect={"test_calc.py": TEST_CALC})


# ---------------------------------------------------------------- 2. implementar-slugify
TEXTO = '''def slugify(texto):
    """Transforma um texto em slug: minúsculas, sem acentos, palavras separadas por '-'.

    slugify("Olá Mundo!") -> "ola-mundo"
    slugify("  Várias   palavras aqui ") -> "varias-palavras-aqui"
    """
    raise NotImplementedError
'''
TEXTO_SOLUCAO = '''import re
import unicodedata


def slugify(texto):
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    palavras = re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split()
    return "-".join(palavras)
'''


def check_slugify(folder):
    return hidden_tests(folder, '''from texto import slugify


def test_exemplos():
    assert slugify("Olá Mundo!") == "ola-mundo"
    assert slugify("  Várias   palavras aqui ") == "varias-palavras-aqui"
    assert slugify("Ação & Reação") == "acao-reacao"
    assert slugify("já-feito") == "ja-feito"
    assert slugify("") == ""
    assert slugify("123 abc") == "123-abc"
''')


# ---------------------------------------------------------------- 3. renomear-funcao
PEDIDO = '''def calcular_total(itens):
    return sum(preco * quantidade for preco, quantidade in itens)
'''
RELATORIO = '''from pedido import calcular_total


def resumo(itens):
    return f"Total: {calcular_total(itens)}"
'''
MAIN_PEDIDO = '''from relatorio import resumo

print(resumo([(10, 2), (5, 3)]))
'''


def check_renomear(folder):
    for name in ("pedido.py", "relatorio.py", "main.py"):
        content = read(folder, name)

        if content is None:
            return False, f"{name} sumiu"

        if "calcular_total" in content:
            return False, f"{name} ainda usa calcular_total"

    if "total_do_pedido" not in (read(folder, "pedido.py") or "") or "total_do_pedido" not in (read(folder, "relatorio.py") or ""):
        return False, "o novo nome não aparece em pedido.py e relatorio.py"

    code, output = run_python(folder, "main.py")

    return (code == 0 and output == "Total: 35"), f"main.py imprimiu {output[:80]!r}"


# ---------------------------------------------------------------- 4. adicionar-flag
SAUDAR = '''import argparse

parser = argparse.ArgumentParser()
parser.add_argument("nome")
args = parser.parse_args()

print(f"Olá, {args.nome}!")
'''
SAUDAR_SOLUCAO = '''import argparse

parser = argparse.ArgumentParser()
parser.add_argument("nome")
parser.add_argument("--maiusculas", action="store_true")
args = parser.parse_args()

mensagem = f"Olá, {args.nome}!"
print(mensagem.upper() if args.maiusculas else mensagem)
'''


def check_flag(folder):
    code, plain = run_python(folder, "saudar.py", "Ana")

    if code != 0 or plain != "Olá, Ana!":
        return False, f"sem a opção deveria imprimir 'Olá, Ana!' e imprimiu {plain[:60]!r}"

    code, loud = run_python(folder, "saudar.py", "Ana", "--maiusculas")

    return (code == 0 and loud == "OLÁ, ANA!"), f"com --maiusculas imprimiu {loud[:60]!r}"


# ---------------------------------------------------------------- 5. resumo-csv
VENDAS = "categoria,valor\nlivros,30\njogos,50\nlivros,20\njogos,10\nfilmes,15\n"
RESUMO_SOLUCAO = '''import csv
from collections import defaultdict

totais = defaultdict(int)

with open("vendas.csv", newline="", encoding="utf-8") as arquivo:
    for linha in csv.DictReader(arquivo):
        totais[linha["categoria"]] += int(linha["valor"])

for categoria in sorted(totais):
    print(f"{categoria}: {totais[categoria]}")
'''


def check_csv(folder):
    if read(folder, "resumo.py") is None:
        return False, "resumo.py não foi criado"

    code, output = run_python(folder, "resumo.py")

    if code != 0:
        return False, f"resumo.py deu erro: {output[-80:]}"

    parsed = []

    for line in output.splitlines():
        match = re.fullmatch(r"\s*(\w+)\s*:\s*(-?\d+(?:\.\d+)?)\s*", line)

        if not match:
            return False, f"linha fora do formato 'categoria: total': {line[:60]!r}"

        parsed.append((match.group(1), float(match.group(2))))

    expected = [("filmes", 15.0), ("jogos", 60.0), ("livros", 50.0)]

    return parsed == expected, f"resultado {parsed}" if parsed != expected else "totais corretos e em ordem"


# ---------------------------------------------------------------- 6. criar-testes (mutação)
VALIDADOR = '''def eh_palindromo(texto):
    """True se o texto é igual lido de trás para frente, ignorando maiúsculas e espaços."""
    limpo = texto.replace(" ", "").lower()
    return limpo == limpo[::-1]
'''
TESTES_SOLUCAO = '''from validador import eh_palindromo


def test_simples():
    assert eh_palindromo("arara")


def test_maiusculas():
    assert eh_palindromo("Ana")


def test_espacos():
    assert eh_palindromo("ola mundo") is False
    assert eh_palindromo("socorram me subi no onibus em marrocos")


def test_falso():
    assert not eh_palindromo("python")
'''
MUTANTS = {
    "ignora maiúsculas": VALIDADOR.replace(".lower()", ""),
    "sempre verdadeiro": VALIDADOR.replace("limpo == limpo[::-1]", "True"),
    "não ignora espaços": VALIDADOR.replace('texto.replace(" ", "").lower()', "texto.lower()"),
}


def check_testes(folder):
    content = read(folder, "test_validador.py")

    if content is None:
        return False, "test_validador.py não foi criado"

    if read(folder, "validador.py") != VALIDADOR:
        return False, "validador.py foi alterado (o pedido era só escrever testes)"

    if len(re.findall(r"^\s*assert\b", content, re.MULTILINE)) < 4:
        return False, "menos de 4 verificações (assert)"

    passed, last = run_pytest(folder, "test_validador.py")

    if not passed:
        return False, f"os testes não passam no código correto: {last}"

    survivors = []

    for name, mutant in MUTANTS.items():
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "mutante"
            shutil.copytree(folder, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            (copy / "validador.py").write_text(mutant, encoding="utf-8")
            still_passes, _ = run_pytest(copy, "test_validador.py")

            if still_passes:
                survivors.append(name)

    if survivors:
        return False, "os testes não detectam defeitos: " + ", ".join(survivors)

    return True, "testes passam no código certo e detectam os 3 defeitos plantados"


# ---------------------------------------------------------------- 7. corrigir-estado
CARRINHO = '''class Carrinho:
    def __init__(self, itens=[]):
        self.itens = itens

    def adicionar(self, item):
        self.itens.append(item)

    def total_itens(self):
        return len(self.itens)
'''
TEST_CARRINHO = '''from carrinho import Carrinho


def test_carrinho_novo_comeca_vazio():
    primeiro = Carrinho()
    primeiro.adicionar("a")
    segundo = Carrinho()
    assert segundo.total_itens() == 0
'''


def check_estado(folder):
    return hidden_tests(folder, '''from carrinho import Carrinho


def test_independentes():
    a, b, c = Carrinho(), Carrinho(), Carrinho()
    a.adicionar("x")
    a.adicionar("y")
    b.adicionar("z")
    assert (a.total_itens(), b.total_itens(), c.total_itens()) == (2, 1, 0)


def test_com_itens_iniciais():
    assert Carrinho(["x"]).total_itens() == 1
''', protect={"test_carrinho.py": TEST_CARRINHO})


# ---------------------------------------------------------------- 8. json-transformar
PESSOAS = json.dumps([
    {"nome": "Carla", "idade": 17}, {"nome": "Bruno", "idade": 18}, {"nome": "Ana", "idade": 30},
    {"nome": "Davi", "idade": 12}, {"nome": "Eva", "idade": 45},
], ensure_ascii=False, indent=2)
ADULTOS = [{"nome": "Ana", "idade": 30}, {"nome": "Bruno", "idade": 18}, {"nome": "Eva", "idade": 45}]


def check_json(folder):
    content = read(folder, "adultos.json")

    if content is None:
        return False, "adultos.json não foi criado"

    try:
        data = json.loads(content)
    except ValueError:
        return False, "adultos.json não é JSON válido"

    return data == ADULTOS, "lista correta e ordenada" if data == ADULTOS else f"conteúdo inesperado: {str(data)[:90]}"


# ---------------------------------------------------------------- 9. corrigir-importacao
MAIN_IMPORT = '''from utils.helpers import dobrar

print(dobrar(21))
'''
HELPERS = '''def dobrar(valor):
    return valor * 2
'''


def check_importacao(folder):
    if "def dobrar" not in (read(folder, "util/helpers.py") or ""):
        return False, "util/helpers.py perdeu a função dobrar"

    code, output = run_python(folder, "main.py")

    return (code == 0 and output == "42"), f"main.py imprimiu {output[-80:]!r}"


# ---------------------------------------------------------------- 10. refatorar-duplicacao
PRECOS = '''def preco_com_imposto_a(valor):
    return round(valor * 1.10, 2)


def preco_com_imposto_b(valor):
    return round(valor * 1.20, 2)


def preco_com_imposto_c(valor):
    return round(valor * 1.05, 2)
'''
PRECOS_SOLUCAO = '''def com_taxa(valor, taxa):
    return round(valor * (1 + taxa), 2)


def preco_com_imposto_a(valor):
    return com_taxa(valor, 0.10)


def preco_com_imposto_b(valor):
    return com_taxa(valor, 0.20)


def preco_com_imposto_c(valor):
    return com_taxa(valor, 0.05)
'''


def check_refatorar(folder):
    content = read(folder, "precos.py") or ""

    if "def com_taxa" not in content:
        return False, "a função auxiliar com_taxa não existe"

    if len(re.findall(r"com_taxa\(", content)) < 4:
        return False, "as três funções não usam com_taxa"

    return hidden_tests(folder, '''from precos import preco_com_imposto_a, preco_com_imposto_b, preco_com_imposto_c


def test_resultados_iguais():
    assert preco_com_imposto_a(100) == 110.0
    assert preco_com_imposto_b(100) == 120.0
    assert preco_com_imposto_c(100) == 105.0
    assert preco_com_imposto_a(19.99) == 21.99
    assert preco_com_imposto_c(0) == 0.0
''')


# ---------------------------------------------------------------- lista
TASKS = [
    {"id": "corrigir-soma",
     "prompt": "Na pasta {dir} o teste test_calc.py está falhando. Rode os testes, descubra o erro e corrija o código em calc.py. Não altere o teste.",
     "files": {"calc.py": CALC, "test_calc.py": TEST_CALC}, "check": check_corrigir_soma,
     "solution": {"calc.py": CALC.replace("range(1, n)", "range(1, n + 1)").replace("(len(valores) + 1)", "len(valores)")}},
    {"id": "implementar-slugify",
     "prompt": "Implemente a função slugify em {dir}/texto.py, seguindo a descrição e os exemplos da docstring. Teste com alguns exemplos antes de terminar.",
     "files": {"texto.py": TEXTO}, "check": check_slugify, "solution": {"texto.py": TEXTO_SOLUCAO}},
    {"id": "renomear-funcao",
     "prompt": "Renomeie a função calcular_total para total_do_pedido em todos os arquivos da pasta {dir}, sem mudar o comportamento. O main.py deve continuar funcionando.",
     "files": {"pedido.py": PEDIDO, "relatorio.py": RELATORIO, "main.py": MAIN_PEDIDO}, "check": check_renomear,
     "solution": {"pedido.py": PEDIDO.replace("calcular_total", "total_do_pedido"),
                  "relatorio.py": RELATORIO.replace("calcular_total", "total_do_pedido")}},
    {"id": "adicionar-opcao-cli",
     "prompt": "Em {dir}/saudar.py adicione a opção --maiusculas, que imprime a saudação inteira em letras maiúsculas. Sem a opção, o programa continua igual.",
     "files": {"saudar.py": SAUDAR}, "check": check_flag, "solution": {"saudar.py": SAUDAR_SOLUCAO}},
    {"id": "resumo-de-csv",
     "prompt": "Crie {dir}/resumo.py que lê o vendas.csv da mesma pasta e imprime o total por categoria, uma por linha no formato 'categoria: total', em ordem alfabética.",
     "files": {"vendas.csv": VENDAS}, "check": check_csv, "solution": {"resumo.py": RESUMO_SOLUCAO}},
    {"id": "escrever-testes",
     "prompt": "Escreva em {dir}/test_validador.py testes com pytest para a função eh_palindromo de validador.py, cobrindo pelo menos 4 casos diferentes (verdadeiros e falsos, com maiúsculas e com espaços). Rode e garanta que passam. Não altere o validador.py.",
     "files": {"validador.py": VALIDADOR}, "check": check_testes, "solution": {"test_validador.py": TESTES_SOLUCAO}},
    {"id": "corrigir-estado-compartilhado",
     "prompt": "O teste test_carrinho.py em {dir} falha de um jeito estranho: um carrinho novo já nasce com itens de outro carrinho. Descubra a causa e corrija carrinho.py sem mexer no teste.",
     "files": {"carrinho.py": CARRINHO, "test_carrinho.py": TEST_CARRINHO}, "check": check_estado,
     "solution": {"carrinho.py": CARRINHO.replace("itens=[]", "itens=None").replace("self.itens = itens", "self.itens = list(itens) if itens else []")}},
    {"id": "filtrar-json",
     "prompt": "Leia {dir}/pessoas.json e grave {dir}/adultos.json só com as pessoas de 18 anos ou mais, ordenadas por nome.",
     "files": {"pessoas.json": PESSOAS}, "check": check_json, "solution": {"adultos.json": json.dumps(ADULTOS, ensure_ascii=False)}},
    {"id": "corrigir-importacao",
     "prompt": "Rodar {dir}/main.py dá erro de importação. Descubra o motivo e corrija para que o programa imprima 42.",
     "files": {"main.py": MAIN_IMPORT, "util/__init__.py": "", "util/helpers.py": HELPERS}, "check": check_importacao,
     "solution": {"main.py": MAIN_IMPORT.replace("utils.helpers", "util.helpers")}},
    {"id": "refatorar-duplicacao",
     "prompt": "As três funções de {dir}/precos.py repetem o mesmo cálculo com taxas diferentes. Crie uma função auxiliar com_taxa(valor, taxa) e faça as três usarem ela, mantendo os nomes e os resultados.",
     "files": {"precos.py": PRECOS}, "check": check_refatorar, "solution": {"precos.py": PRECOS_SOLUCAO}},
]


def folder_of(task_id: str) -> str:
    return f"{REAL_DIR}/{task_id}"

import os
import shlex
from pathlib import Path

from core.paths import PROJECT_ROOT


SAFE_COMMANDS = {
    "pwd",
    "ls",
    "whoami",
    "uname",
    "cat",
    "which",
    "command",
    "type",
    "id",
    "df",
    "free",
    "lscpu",
    "lsblk",
    "find",
    "pytest",
    "nvidia-smi",
    # Windows
    "where",
    "hostname",
    "systeminfo",
    "tasklist",
    "ver",
}

# find só é seguro sem ações que executam/alteram/gravam.
UNSAFE_FIND_ARGS = {
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-fls",
}

# pytest executa código; só é seguro para testes versionados em tests/
# e sem flags que carregam plugins/configuração de fora.
UNSAFE_PYTEST_FLAGS = (
    "-p",
    "-c",
    "--rootdir",
    "--confcutdir",
    "--pyargs",
    "-o",
    "--override-ini",
    "--import-mode",
)

# Flags inofensivas cujo próximo argumento é um valor (não um caminho).
PYTEST_FLAGS_WITH_VALUE = {"-k", "-m", "-W", "--tb", "--maxfail"}

POWERSHELL_EXECUTABLES = {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}

# Cmdlets somente-leitura aceitos sem confirmação.
SAFE_POWERSHELL_CMDLETS = {
    "get-childitem",
    "get-content",
    "get-command",
    "get-location",
    "get-process",
    "get-computerinfo",
    "get-ciminstance",
    "get-item",
    "get-itemproperty",
    "get-date",
    "get-host",
    "test-path",
    "resolve-path",
}

SAFE_GIT_SUBCOMMANDS = {
    "status",
    "log",
    "branch",
    "remote",
    "show",
    "diff",
    "--version",
    "-v",
}

SAFE_CMAKE_SUBCOMMANDS = {
    "--version",
    "-version",
    "-v",
}

SAFE_GCC_SUBCOMMANDS = {
    "--version",
    "-v",
    "-dumpversion",
}

SAFE_MAKE_SUBCOMMANDS = {
    "--version",
    "-v",
}

SAFE_CURL_SUBCOMMANDS = {
    "--version",
    "-V",
}

SAFE_DNF_SUBCOMMANDS = {
    "list",
    "info",
    "search",
    "repoquery",
}

SAFE_RPM_SUBCOMMANDS = {
    "-q",
    "-qa",
    "-qi",
    "-ql",
    "-qf",
}

SAFE_PIP_SUBCOMMANDS = {
    "list",
    "show",
    "--version",
    "-V",
}

SAFE_OLLAMA_SUBCOMMANDS = {
    "list",
    "ps",
    "show",
    "--version",
    "-v",
}

SAFE_PYTHON_SUBCOMMANDS = {
    "--version",
    "-V",
}

SENSITIVE_COMMANDS = {
    "sudo",
    "dnf",
    "rpm",
    "apt",
    "apt-get",
    "winget",
    "choco",
    "scoop",
    "cmd",
    "powershell",
    "pwsh",
    "systemctl",
    "service",
    "mount",
    "umount",
    "chmod",
    "chown",
    "rm",
    "mv",
    "cp",
    "python",
    "python3",
    "pip",
    "pip3",
    "curl",
    "wget",
}


# Operadores/metacaracteres de shell que esta ferramenta
# deliberadamente NÃO suporta.
SHELL_OPERATORS = (
    "||",
    "&&",
    "|",
    ";",
    ">",
    ">>",
    "<",
    "<<",
    "$(",
    "`",
    "&",
)


def contains_shell_operator(command: str) -> str | None:
    """
    Retorna o operador encontrado ou None.

    A ferramenta run_command usa subprocess com shell=False.
    Portanto, não devemos aceitar sintaxe que sugira execução
    através de shell.
    """

    for operator in SHELL_OPERATORS:
        if operator in command:
            return operator

    return None


def split_command(command: str) -> list[str]:
    """
    Separa o comando em argumentos.

    No Windows, shlex em modo POSIX consome as barras invertidas de caminhos
    com unidade (C:, D:); por isso usa posix=False e remove as aspas externas.
    """

    if os.name != "nt":
        return shlex.split(command)

    parts = shlex.split(command, posix=False)

    return [
        part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part
        for part in parts
    ]


def parse_command(command: str) -> tuple[list[str] | None, str | None]:
    """
    Valida e separa o comando.

    Retorna:
        (parts, None) em caso de sucesso
        (None, erro) em caso de falha
    """

    if not command or not command.strip():
        return None, "Comando vazio."

    operator = contains_shell_operator(command)

    if operator is not None:
        return (
            None,
            (
                f"Comando composto não suportado: operador "
                f"'{operator}'. Use ferramentas/comandos separados."
            ),
        )

    try:
        parts = split_command(command)
    except ValueError as e:
        return None, f"Comando inválido: {e}"

    if not parts:
        return None, "Comando vazio."

    return parts, None


def _is_safe_find(parts: list[str]) -> bool:
    return not any(arg in UNSAFE_FIND_ARGS for arg in parts[1:])


def _is_safe_pytest(parts: list[str]) -> bool:
    tests_dir = (PROJECT_ROOT / "tests").resolve()
    skip_next = False

    for arg in parts[1:]:
        if skip_next:
            skip_next = False
            continue

        if arg in PYTEST_FLAGS_WITH_VALUE:
            skip_next = True
            continue

        if arg.startswith("-"):
            flag = arg.split("=", 1)[0]
            if flag in UNSAFE_PYTEST_FLAGS or any(
                arg.startswith(f) and f in {"-p", "-c", "-o"} and len(arg) > len(f)
                for f in UNSAFE_PYTEST_FLAGS
            ):
                return False
            continue

        candidate = Path(arg.split("::", 1)[0]).expanduser()

        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate

        # Valores de flags (ex.: -k expressao) não são caminhos existentes.
        if not candidate.exists():
            continue

        try:
            candidate.resolve().relative_to(tests_dir)
        except ValueError:
            return False

    return True


def _is_safe_powershell(parts: list[str]) -> bool:
    """Somente `-Command "<cmdlet de leitura> [args]"` (sem -File/-EncodedCommand)."""

    args = parts[1:]
    command_text = None
    index = 0

    while index < len(args):
        flag = args[index].lower()

        if flag in {"-noprofile", "-nologo", "-noninteractive"}:
            index += 1
            continue

        if flag in {"-command", "-c"} and index + 1 < len(args):
            command_text = " ".join(args[index + 1:])
            break

        return False

    if not command_text or not command_text.strip():
        return False

    first_token = command_text.strip().split()[0].lower()

    return first_token in SAFE_POWERSHELL_CMDLETS


def requires_confirmation(command: str) -> bool:
    parts, error = parse_command(command)

    if error:
        return True

    executable = parts[0]

    if executable.lower().endswith(".exe"):
        executable = executable[:-4]

    if executable == "find":
        return not _is_safe_find(parts)

    if executable == "pytest":
        return not _is_safe_pytest(parts)

    if executable.lower() in POWERSHELL_EXECUTABLES | {"powershell", "pwsh"}:
        return not _is_safe_powershell(parts)

    if executable in SAFE_COMMANDS:
        return False

    if executable == "git":
        if len(parts) < 2:
            return True

        subcommand = parts[1]

        return subcommand not in SAFE_GIT_SUBCOMMANDS

    if executable == "dnf":
        if len(parts) < 2:
            return True

        subcommand = parts[1]

        return subcommand not in SAFE_DNF_SUBCOMMANDS

    if executable == "rpm":
        if len(parts) < 2:
            return True

        subcommand = parts[1]

        return subcommand not in SAFE_RPM_SUBCOMMANDS

    if executable in {"pip", "pip3"}:
        if len(parts) >= 2 and parts[1] in SAFE_PIP_SUBCOMMANDS:
            return False
        return True

    if executable == "ollama":
        if len(parts) >= 2 and parts[1] in SAFE_OLLAMA_SUBCOMMANDS:
            return False
        return True

    if executable in {"python", "python3"}:
        if len(parts) >= 2 and parts[1] in SAFE_PYTHON_SUBCOMMANDS:
            return False
        return True

    if executable == "cmake":
        if len(parts) >= 2 and parts[1] in SAFE_CMAKE_SUBCOMMANDS:
            return False
        return True

    if executable in {"gcc", "g++"}:
        if len(parts) >= 2 and parts[1] in SAFE_GCC_SUBCOMMANDS:
            return False
        return True

    if executable == "make":
        if len(parts) >= 2 and parts[1] in SAFE_MAKE_SUBCOMMANDS:
            return False
        return True

    if executable == "curl":
        if len(parts) >= 2 and parts[1] in SAFE_CURL_SUBCOMMANDS:
            return False
        return True

    if executable in SENSITIVE_COMMANDS:
        return True

    return True


def request_confirmation(command: str, reason: str) -> bool:
    print()
    print("=" * 60)
    print("⚠️  AÇÃO REQUER CONFIRMAÇÃO")
    print("=" * 60)
    print()

    print("O que será feito:")
    print(reason)

    print()
    print("Comando exato:")
    print(f"  {command}")

    print()
    print("Pressione ENTER para executar.")
    print("Digite C e pressione ENTER para cancelar.")
    print()

    try:
        answer = input("> ").strip().lower()
        return answer == ""
    except (EOFError, OSError):
        print("❌ Entrada não interativa ou fechada. Operação cancelada.")
        return False


def authorize(command: str, reason: str) -> bool:
    parts, error = parse_command(command)

    if error:
        print()
        print("❌ Comando recusado pelo Permission Manager.")
        print(error)
        print()

        return False

    if requires_confirmation(command):
        return request_confirmation(command, reason)

    return True

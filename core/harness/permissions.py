import shlex


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
        parts = shlex.split(command)
    except ValueError as e:
        return None, f"Comando inválido: {e}"

    if not parts:
        return None, "Comando vazio."

    return parts, None


def requires_confirmation(command: str) -> bool:
    parts, error = parse_command(command)

    if error:
        return True

    executable = parts[0]

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

import os
import shutil
import subprocess

from core.harness.permissions import (
    authorize,
    parse_command,
)
from core.paths import PROJECT_ROOT, VENV_BIN_DIR, WORKSPACE_DIR


INSTALLATION_COMMANDS = {
    "dnf",
    "apt",
    "apt-get",
    "pacman",
    "zypper",
    "pip",
    "pip3",
    "npm",
    "yarn",
    "cargo",
    "winget",
    "choco",
    "scoop",
}


SYSTEM_CHANGE_COMMANDS = {
    "dnf",
    "apt",
    "apt-get",
    "pacman",
    "zypper",
    "rpm",
    "sudo",
    "systemctl",
    "service",
    "mount",
    "umount",
    "chmod",
    "chown",
    # Windows
    "winget",
    "choco",
    "sc",
    "reg",
    "regedit",
    "icacls",
    "takeown",
    "netsh",
    "schtasks",
    "setx",
    "bcdedit",
}


# Comandos de Linux que não existem no Windows (o modelo costuma tentá-los).
UNIX_ONLY_COMMANDS = {"cat", "ls", "grep", "head", "tail", "touch", "mkdir", "cp", "mv", "rm", "which", "chmod"}


DESTRUCTIVE_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
    "shred",
    "mkfs",
    "fdisk",
    "wipefs",
    # Windows
    "del",
    "erase",
    "rd",
    "move",
    "format",
    "diskpart",
    "remove-item",
    "move-item",
}


def get_command_executables(parts: list[str]) -> list[str]:
    """
    Retorna os executáveis relevantes do comando.

    Isso permite detectar casos como:

        sudo dnf install git

    mesmo que o primeiro executável seja 'sudo'.
    """

    if not parts:
        return []

    executables = []

    for part in parts:
        if part in {
            "sudo",
            "env",
            "command",
        }:
            executables.append(part)
            continue

        # O primeiro argumento que não seja um wrapper
        # é considerado o comando real.
        if not executables or executables[-1] in {
            "sudo",
            "env",
            "command",
        }:
            executables.append(part)

            if part not in {
                "sudo",
                "env",
                "command",
            }:
                break

    return [_normalize_executable(executable) for executable in executables]


def _normalize_executable(executable: str) -> str:
    """Reduz o caminho/nome do executável a 'pip' (sem pasta, .exe e maiúsculas)."""

    name = os.path.basename(executable.replace("\\", "/")).lower()

    if name.endswith(".exe"):
        name = name[:-4]

    return name


def check_constraints(
    parts: list[str],
    constraints=None,
) -> dict | None:
    """
    Verifica se o comando é permitido pelas restrições
    específicas da tarefa.

    Retorna None quando permitido.
    Retorna um dict de erro quando bloqueado.
    """

    if constraints is None:
        return None

    executables = get_command_executables(parts)

    if not executables:
        return None

    # ---------------------------------------------------------
    # Instalação
    # ---------------------------------------------------------

    if not getattr(constraints, "allow_install", True):

        for executable in executables:
            if executable in INSTALLATION_COMMANDS:

                # Só considera instalação quando o comando
                # realmente possui uma operação de instalação.
                installation_operations = {
                    "install",
                    "add",
                    "update",
                    "upgrade",
                }

                has_install_operation = any(
                    argument in installation_operations
                    for argument in parts[1:]
                )

                if has_install_operation:
                    return {
                        "success": False,
                        "error": (
                            "Operação bloqueada pelas restrições "
                            "da tarefa: instalações não são permitidas."
                        ),
                        "constraint_blocked": True,
                        "tool_error": True,
                    }

    # ---------------------------------------------------------
    # Alterações no sistema
    # ---------------------------------------------------------

    if not getattr(constraints, "allow_system_changes", True):

        for executable in executables:
            if executable in SYSTEM_CHANGE_COMMANDS:
                return {
                    "success": False,
                    "error": (
                        "Operação bloqueada pelas restrições "
                        "da tarefa: alterações no sistema não são permitidas."
                    ),
                    "constraint_blocked": True,
                    "tool_error": True,
                }

    # ---------------------------------------------------------
    # Operações destrutivas
    # ---------------------------------------------------------

    if not getattr(constraints, "allow_destructive", True):

        for executable in executables:
            if executable in DESTRUCTIVE_COMMANDS:
                return {
                    "success": False,
                    "error": (
                        "Operação bloqueada pelas restrições "
                        "da tarefa: operações destrutivas não são permitidas."
                    ),
                    "constraint_blocked": True,
                    "tool_error": True,
                }

    return None


MKDIR_COMMANDS = {"mkdir", "md"}
MKDIR_IGNORED_FLAGS = {"-p", "/p", "-parents", "--parents"}


def _make_workspace_dirs(parts: list[str]) -> dict | None:
    """
    mkdir/md só dentro de workspace/ e scripts/eval/ é feito em Python e não pede confirmação. No Windows o
    mkdir é um comando interno do cmd e não roda com shell=False, e criar pasta ali é inofensivo.
    Qualquer outro caso devolve None e segue o fluxo normal (com confirmação).
    """

    if _normalize_executable(parts[0]) not in MKDIR_COMMANDS:
        return None

    targets = [arg.strip('"') for arg in parts[1:] if arg.lower() not in MKDIR_IGNORED_FLAGS]

    if not targets or any(arg.startswith("-") for arg in targets):
        return None

    roots = [WORKSPACE_DIR.resolve(), (PROJECT_ROOT / "scripts" / "eval").resolve()]
    folders = []

    for arg in targets:
        folder = (PROJECT_ROOT / arg).resolve()

        if not any(folder == root or root in folder.parents for root in roots):
            return None

        folders.append(folder)

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    names = ", ".join(str(folder.relative_to(PROJECT_ROOT)) for folder in folders)

    return {"success": True, "returncode": 0, "stdout": f"Pasta(s) pronta(s): {names}", "stderr": "", "error": None}


def run_command(
    command: str,
    reason: str,
    constraints=None,
) -> dict:

    if not command or not command.strip():
        return {
            "success": False,
            "error": "Comando vazio.",
            "tool_error": True,
        }

    if not reason or not reason.strip():
        return {
            "success": False,
            "error": "É obrigatório informar a justificativa da execução.",
            "tool_error": True,
        }

    parts, parse_error = parse_command(command)

    if parse_error:
        return {
            "success": False,
            "error": parse_error,
            "tool_error": True,
        }

    # Expande ~ somente nos argumentos.
    # Não altera o executável.
    parts[1:] = [
        os.path.expanduser(arg)
        for arg in parts[1:]
    ]

    # ---------------------------------------------------------
    # Restrições específicas da tarefa
    # ---------------------------------------------------------

    constraint_error = check_constraints(
        parts,
        constraints,
    )

    if constraint_error is not None:
        return constraint_error

    made = _make_workspace_dirs(parts)

    if made is not None:
        return made

    # ---------------------------------------------------------
    # Permission Manager
    # ---------------------------------------------------------

    if not authorize(command, reason):
        return {
            "success": False,
            "cancelled": True,
            "error": "Execução recusada ou cancelada pelo usuário.",
            "tool_error": True,
        }

    # ---------------------------------------------------------
    # Execução
    # ---------------------------------------------------------

    try:
        env = os.environ.copy()
        venv_bin = str(VENV_BIN_DIR)
        if VENV_BIN_DIR.exists() and venv_bin not in env.get("PATH", ""):
            env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        # No Windows o CreateProcess procura o executável no PATH do processo
        # atual, não no do env passado; resolve explicitamente (inclui PATHEXT).
        resolved = shutil.which(parts[0], path=env.get("PATH"))
        if resolved:
            parts[0] = resolved

        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
            cwd=str(PROJECT_ROOT),
            env=env,
        )

        success = result.returncode == 0

        return {
            "success": success,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": (
                None
                if success
                else (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"Comando terminou com código {result.returncode}"
                )
            ),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Comando excedeu o limite de 300 segundos.",
            "tool_error": True,
        }

    except FileNotFoundError as e:
        message = str(e)

        if os.name == "nt" and _normalize_executable(parts[0]) in UNIX_ONLY_COMMANDS:
            message = (
                f"'{parts[0]}' não existe no Windows. Use read_file (no lugar de cat/head/tail), "
                "list_directory (no lugar de ls) e search_files (no lugar de grep/find)."
            )

        return {
            "success": False,
            "error": message,
            "tool_error": True,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "tool_error": True,
        }

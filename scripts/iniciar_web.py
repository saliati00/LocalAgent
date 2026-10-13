"""
Sobe a interface web do LocalAgent, tudo dentro da pasta do projeto:

    1. a ponte (scripts/ponte_web.py) com o agente no modo só FAST, nesta mesma janela;
    2. o Open WebUI (instalado em .venv-webui) apontando para a ponte, com os dados em data-webui/;
    3. o navegador em http://127.0.0.1:8080.

Ctrl+C (ou fechar a janela) encerra os dois. Use iniciar-web.bat.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

BRIDGE_PORT = 8765
WEBUI_PORT = 8080
WEBUI_DIR = ROOT / ".venv-webui"
DATA_DIR = ROOT / "data-webui"
WAIT_SECONDS = 300  # a primeira subida do Open WebUI baixa arquivos e demora


def webui_executable() -> Path:
    return WEBUI_DIR / "Scripts" / "open-webui.exe"


def webui_environment(bridge_port: int = BRIDGE_PORT) -> dict:
    """Configuração do Open WebUI: só a ponte como fonte de modelos, sem login e sem chamadas automáticas ao agente."""

    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(DATA_DIR),
        "WEBUI_AUTH": "False",
        "ENABLE_SIGNUP": "False",
        "ENABLE_OLLAMA_API": "False",
        "OPENAI_API_BASE_URL": f"http://127.0.0.1:{bridge_port}/v1",
        "OPENAI_API_KEY": "local",
        # Título, tags, sugestões e autocompletar são pedidos automáticos ao modelo: aqui cada pedido seria uma tarefa do agente.
        "ENABLE_TITLE_GENERATION": "False",
        "ENABLE_TAGS_GENERATION": "False",
        "ENABLE_FOLLOW_UP_GENERATION": "False",
        "ENABLE_AUTOCOMPLETE_GENERATION": "False",
        "ENABLE_SEARCH_QUERY_GENERATION": "False",
        "ENABLE_RETRIEVAL_QUERY_GENERATION": "False",
        "ENABLE_EVALUATION_ARENA_MODELS": "False",
        "ANONYMIZED_TELEMETRY": "False",
        "DO_NOT_TRACK": "True",
        "SCARF_NO_ANALYTICS": "True",
        "PYTHONUTF8": "1",
    })

    return env


def wait_for(url: str, seconds: int) -> bool:
    deadline = time.time() + seconds

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return True
        except OSError:
            time.sleep(3)

    return False


def stop_tree(process: subprocess.Popen) -> None:
    """Encerra o Open WebUI e tudo o que ele abriu."""

    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()


def main() -> int:
    from core.console import ensure_utf8_console

    ensure_utf8_console()
    os.environ["LOCALAGENT_SO_FAST"] = "1"

    if not webui_executable().exists():
        print("O Open WebUI não está instalado (pasta .venv-webui). Rode instalar.bat e tente de novo.")
        return 1

    import ponte_web

    try:
        server, _ = ponte_web.build_server(BRIDGE_PORT)
    except OSError as exc:
        print(f"Não consegui abrir a ponte na porta {BRIDGE_PORT} (já há outra janela do LocalAgent aberta?): {exc}")
        return 1

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Ponte do LocalAgent (só FAST) em http://127.0.0.1:{BRIDGE_PORT}/v1")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Iniciando o Open WebUI. Na primeira vez pode levar alguns minutos...")
    webui = subprocess.Popen(
        [str(webui_executable()), "serve", "--host", "127.0.0.1", "--port", str(WEBUI_PORT)],
        env=webui_environment(), cwd=str(ROOT),
    )

    try:
        if wait_for(f"http://127.0.0.1:{WEBUI_PORT}/health", WAIT_SECONDS):
            print(f"\nPronto. Abrindo http://127.0.0.1:{WEBUI_PORT}  (Ctrl+C aqui encerra tudo)")
            webbrowser.open(f"http://127.0.0.1:{WEBUI_PORT}")
        else:
            print("O Open WebUI não respondeu a tempo. Veja as mensagens acima; tente de novo ou envie a pasta logs.")

        webui.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        stop_tree(webui)
        server.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())

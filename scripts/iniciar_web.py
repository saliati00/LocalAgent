"""
Abre o chat do LocalAgent no navegador (só FAST). Sobe a ponte (scripts/ponte_web.py) nesta janela e abre
http://agent.localhost:8765 (o mesmo que http://127.0.0.1:8765). Ctrl+C encerra. Use iniciar-web.bat.
"""

import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PORT = 8765


def main() -> int:
    from core.console import ensure_utf8_console

    ensure_utf8_console()
    os.environ["LOCALAGENT_SO_FAST"] = "1"

    import ponte_web

    try:
        server, _ = ponte_web.build_server(PORT)
    except OSError as exc:
        print(f"Não consegui abrir a porta {PORT} (já há outra janela do LocalAgent aberta?): {exc}")
        return 1

    url = f"http://{ponte_web.SITE_NAME}:{PORT}"
    print(f"LocalAgent (só FAST) em {url}  (também em http://127.0.0.1:{PORT}; Ctrl+C aqui encerra)")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

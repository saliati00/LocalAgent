"""
Ponte entre a página de chat (web/index.html) e o Harness: uma API no formato OpenAI que roda o agente.

    GET  /                       a página de chat
    GET  /v1/models              um único "modelo": o LocalAgent
    POST /v1/chat/completions    a última mensagem do usuário vira a tarefa do agente

- Um resumo das últimas trocas vai junto como contexto (o agente não guarda a conversa).
- O progresso (ferramentas usadas e se deram certo) aparece no chat como citação; depois vem a resposta final.
- Confirmações (rodar comando, instalar...) viram uma pergunta no chat: responda SIM ou NÃO na mensagem seguinte.
- Uma tarefa por vez. Só escuta em 127.0.0.1.
- Roda no modo só FAST (LOCALAGENT_SO_FAST), definido por quem inicia (scripts/iniciar_web.py).
- Qualquer outro cliente que fale o formato OpenAI também funciona.
"""

import argparse
import contextlib
import json
import queue
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL_ID = "localagent"
DEFAULT_PORT = 8765
CONFIRM_TIMEOUT_SECONDS = 600
KEEP_ALIVE_SECONDS = 15
YES = ("sim", "s", "ok", "yes", "y", "pode", "confirmo", "executar")

LOG_LINE = re.compile(r"^\[\d{4}-\d\d-\d\d [\d:]+\] \[[0-9a-f]+\] (\w+)(?: \| (.*))?$")

PAGE = ROOT / "web" / "index.html"
SITE_NAME = "agent.localhost"  # os navegadores resolvem *.localhost para o próprio PC, sem mexer no arquivo hosts
ALLOWED_HOSTS = ("127.0.0.1", "localhost", SITE_NAME)
HISTORY_PAIRS = 3
HISTORY_CHARS = 300


def progress_line(event: str, details: str) -> str | None:
    """Uma linha do log do Harness vira uma linha curta de progresso (ou nada)."""

    parts = [p.strip() for p in (details or "").split(" | ")]

    if event == "TOOL" and parts and parts[0]:
        shown = " | ".join(parts[1:])[:90]
        return f"🔧 `{parts[0]}` {shown}".rstrip()

    if event == "RESULT" and len(parts) >= 2:
        if parts[1] == "OK":
            return "   ✓ ok"

        return "   ✗ " + " | ".join(parts[2:])[:120]

    if event in ("ESCALATION_SKIPPED", "FAST_RETRY", "MALFORMED_TOOL_CALL", "NEEDS_HUMAN", "STOP"):
        return f"⚠️ {event.replace('_', ' ').lower()}: {(details or '')[:160]}"

    return None


class LineWriter:
    """Substitui o stdout durante a tarefa: guarda só as linhas de progresso."""

    def __init__(self, emit):
        self.emit = emit
        self.buffer = ""

    def write(self, text: str) -> int:
        self.buffer += text

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            match = LOG_LINE.match(line.strip())

            if match:
                shown = progress_line(match.group(1), match.group(2) or "")

                if shown:
                    self.emit(shown)

        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class Session:
    """A tarefa em andamento (só existe uma). O agente roda numa thread e fala com a requisição por filas."""

    def __init__(self, run_agent):
        self.run_agent = run_agent
        self.events: queue.Queue = queue.Queue()
        self.answers: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.waiting = False
        self.lock = threading.Lock()

    @property
    def busy(self) -> bool:
        if self.thread is None:
            return False

        self.thread.join(timeout=0.5)  # a thread acabou de enviar "done" e está saindo
        return self.thread.is_alive()

    def start(self, prompt: str, context: str = "") -> None:
        self.events = queue.Queue()
        self.answers = queue.Queue()
        self.waiting = False
        self.thread = threading.Thread(target=self._work, args=(prompt, context), daemon=True)
        self.thread.start()

    def answer(self, text: str) -> None:
        self.waiting = False
        self.answers.put(text)

    def _ask(self, command: str, reason: str) -> bool:
        self.waiting = True
        self.events.put(("ask", f"**Preciso da sua confirmação.**\n\n{reason}\n\n`{command}`\n\nResponda **SIM** para executar ou **NÃO** para cancelar."))

        try:
            reply = self.answers.get(timeout=CONFIRM_TIMEOUT_SECONDS)
        except queue.Empty:
            self.waiting = False
            return False

        return reply.strip().lower().strip(".!") in YES

    def _work(self, prompt: str, context: str = "") -> None:
        import agent
        from core.harness import permissions

        permissions.CONFIRMATION_HANDLER = self._ask
        result = {"status": "failed", "response": ""}

        try:
            with contextlib.redirect_stdout(LineWriter(lambda line: self.events.put(("text", line)))):
                result = (self.run_agent(prompt, context=context) if context else self.run_agent(prompt)) or result
        except Exception as exc:  # noqa: BLE001 - qualquer erro vira mensagem no chat
            result = {"status": "failed", "response": f"Erro no agente: {exc}"}
        finally:
            permissions.CONFIRMATION_HANDLER = None
            self.events.put(("done", result))


def final_text(result: dict) -> str:
    response = (result.get("response") or "").strip()
    status = result.get("status") or ""

    if status in ("completed", "complete") and response:
        return response

    note = {"needs_human": "Preciso de você para continuar.", "cancelled": "Tarefa cancelada.", "failed": "A tarefa não terminou."}.get(status, f"Tarefa encerrada ({status}).")

    return f"{response}\n\n_{note}_" if response else f"_{note}_"


def make_chunk(content: str | None, finish: str | None = None, role: bool = False, stream_id: str = "") -> dict:
    delta: dict = {}

    if role:
        delta["role"] = "assistant"

    if content is not None:
        delta["content"] = content

    return {
        "id": stream_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def collect_reply(session: Session):
    """Gera pedaços de texto até a tarefa terminar ou pedir uma confirmação. Termina com ('end', None)."""

    while True:
        try:
            kind, value = session.events.get(timeout=KEEP_ALIVE_SECONDS)
        except queue.Empty:
            yield ("ping", "")
            continue

        if kind == "text":
            yield ("text", "> " + value + "\n>\n")
        elif kind == "ask":
            yield ("text", "\n" + value + "\n")
            yield ("end", None)
            return
        elif kind == "done":
            yield ("text", "\n" + final_text(value) + "\n")
            yield ("end", None)
            return


def last_user_text(messages: list) -> str:
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue

        content = message.get("content")

        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))

        return (content or "").strip()

    return ""


def host_of(value: str) -> str:
    """'agent.localhost:8765' ou 'http://agent.localhost:8765' -> 'agent.localhost'."""

    value = (value or "").strip().lower()

    if "://" in value:
        value = value.split("://", 1)[1]

    value = value.split("/", 1)[0]

    return value.rsplit(":", 1)[0] if ":" in value else value


def request_allowed(host_header: str, origin_header: str) -> bool:
    """
    Só aceita pedidos feitos pelos nomes do próprio PC. Barra páginas de outros sites que tentem falar com o agente
    pelo seu navegador (pelo nome do site, no cabeçalho Host, ou pela origem, no cabeçalho Origin).
    """

    if host_of(host_header) not in ALLOWED_HOSTS:
        return False

    return not origin_header or host_of(origin_header) in ALLOWED_HOSTS


def history_context(messages: list) -> str:
    """Resumo curto das últimas trocas (pedido e resposta final), sem o progresso das ferramentas e sem as confirmações."""

    pairs = []
    pending_user = None
    last_request = None

    for message in (messages or [])[:-1]:  # a última é o pedido de agora
        content = message.get("content")

        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))

        content = (content or "").strip()

        if message.get("role") == "user":
            if last_request and content.lower().strip(".!") in YES + ("não", "nao", "n"):
                pending_user = last_request  # a resposta a uma confirmação continua o pedido original
            else:
                pending_user = last_request = content
        elif message.get("role") == "assistant" and pending_user is not None:
            if "Responda **SIM**" not in content:
                answer = " ".join(line for line in content.splitlines() if line.strip() and not line.lstrip().startswith(">"))
                pairs.append((pending_user, answer))

            pending_user = None

    lines = []

    for user, answer in pairs[-HISTORY_PAIRS:]:
        lines.append(f"- Usuário: {user[:HISTORY_CHARS]}\n  Agente: {answer[:HISTORY_CHARS]}")

    return "\n".join(lines)


def make_handler(session: Session, resolve_prompt):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalAgentBridge/1.0"

        def log_message(self, fmt, *args):  # sem ruído no terminal
            pass

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _forbidden(self) -> bool:
            if request_allowed(self.headers.get("Host", ""), self.headers.get("Origin", "")):
                return False

            self._json({"error": {"message": f"acesso permitido só por {SITE_NAME}, localhost ou 127.0.0.1"}}, 403)
            return True

        def do_GET(self):
            if self._forbidden():
                return

            if self.path in ("/", "/index.html"):
                try:
                    body = PAGE.read_bytes()
                except OSError:
                    self._json({"error": {"message": "web/index.html não encontrado"}}, 404)
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.rstrip("/") in ("/v1/models", "/models"):
                self._json({"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "localagent"}]})
            elif self.path.rstrip("/") in ("/health", "/v1"):
                self._json({"status": "ok", "busy": session.busy})
            else:
                self._json({"error": {"message": "não encontrado"}}, 404)

        def do_POST(self):
            if self._forbidden():
                return

            if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
                self._json({"error": {"message": "não encontrado"}}, 404)
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, OSError):
                self._json({"error": {"message": "pedido inválido"}}, 400)
                return

            messages = request.get("messages")
            text = last_user_text(messages)
            stream = bool(request.get("stream"))
            stream_id = "chatcmpl-" + uuid.uuid4().hex[:12]

            if not text:
                self._reply(["Escreva a tarefa que o agente deve fazer."], stream, stream_id)
            else:
                with session.lock:
                    if session.waiting:
                        session.answer(text)
                        source = collect_reply(session)
                    elif session.busy:
                        source = None
                    else:
                        prompt = resolve_prompt(text)

                        if prompt is None:
                            self._reply(["Não encontrei esse prompt salvo."], stream, stream_id)
                            return

                        # Pedidos comuns levam o resumo da conversa; tarefas numeradas e prompts salvos já são completos.
                        session.start(prompt, history_context(messages) if prompt == text else "")
                        source = collect_reply(session)

                if source is None:
                    self._reply(["Já existe uma tarefa em andamento. Espere terminar para pedir outra."], stream, stream_id)
                else:
                    self._relay(source, stream, stream_id)

        def _reply(self, pieces: list, stream: bool, stream_id: str) -> None:
            self._relay(iter([("text", p) for p in pieces] + [("end", None)]), stream, stream_id)

        def _relay(self, source, stream: bool, stream_id: str) -> None:
            if not stream:
                text = "".join(value for kind, value in source if kind == "text")
                self._json({
                    "id": stream_id, "object": "chat.completion", "created": int(time.time()), "model": MODEL_ID,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                })
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def send(payload: str) -> None:
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()

            try:
                send("data: " + json.dumps(make_chunk("", role=True, stream_id=stream_id)) + "\n\n")

                for kind, value in source:
                    if kind == "text":
                        send("data: " + json.dumps(make_chunk(value, stream_id=stream_id), ensure_ascii=False) + "\n\n")
                    elif kind == "ping":
                        send(": ainda trabalhando\n\n")
                    elif kind == "end":
                        break

                send("data: " + json.dumps(make_chunk(None, finish="stop", stream_id=stream_id)) + "\n\n")
                send("data: [DONE]\n\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # o navegador fechou; a tarefa continua e a próxima requisição retoma

    return Handler


def build_server(port: int = DEFAULT_PORT, run_agent=None, resolve_prompt=None, host: str = "127.0.0.1"):
    if run_agent is None or resolve_prompt is None:
        import agent

        run_agent = run_agent or agent.agent
        resolve_prompt = resolve_prompt or agent.resolve_prompt

    session = Session(run_agent)

    return ThreadingHTTPServer((host, port), make_handler(session, resolve_prompt)), session


def main(argv=None) -> int:
    from core.console import ensure_utf8_console

    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="Ponte OpenAI-compatível para o Open WebUI")
    parser.add_argument("--porta", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    server, _ = build_server(args.porta)
    print(f"Ponte do LocalAgent em http://127.0.0.1:{args.porta}/v1  (Ctrl+C para encerrar)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())

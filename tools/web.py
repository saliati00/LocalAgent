import html
import os
import re
from pathlib import Path
import httpx

from tools.filesystem import is_path_writable, PROJECT_ROOT


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

# Limite de segurança por download (evita encher o disco por engano).
MAX_DOWNLOAD_BYTES = 2 * 1024 ** 3


def clean_html(raw_html: str) -> str:
    """
    Remove tags de script, estilo e HTML bruto, retornando texto legível.
    """
    # Remove scripts e estilos
    text = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags HTML
    text = re.sub(r"<[^>]+>", " ", text)
    # Decodifica entidades HTML (&amp;, &lt;, etc.)
    text = html.unescape(text)
    # Colapsa espaços em branco repetidos
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def web_search(query: str, max_results: int = 5) -> dict:
    """
    Pesquisa na internet via DuckDuckGo HTML.
    Retorna títulos, links e snippets dos primeiros resultados.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "error": "Consulta de pesquisa vazia.",
            "results": [],
        }

    try:
        response = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query.strip()},
            headers={"User-Agent": USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )

        if response.status_code != 200 and response.status_code != 202:
            return {
                "success": False,
                "error": f"Serviço de pesquisa retornou status {response.status_code}",
                "results": [],
            }

        html_text = response.text

        # Extrai links e títulos
        url_matches = re.findall(r'<a class="result__url" href="([^"]+)"', html_text)
        title_matches = re.findall(
            r'<a[^>]*class="result__snippet[^>]*>(.*?)</a>', html_text, re.DOTALL
        )

        results = []
        for i, url in enumerate(url_matches[:max_results]):
            url = url.strip()
            if url.startswith("//"):
                url = "https:" + url
            elif not url.startswith("http"):
                url = "https://" + url

            snippet = ""
            if i < len(title_matches):
                snippet = clean_html(title_matches[i])

            results.append({
                "url": url,
                "snippet": snippet,
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Falha na pesquisa web: {e}",
            "results": [],
        }


def fetch_url(url: str, max_length: int = 6000) -> dict:
    """
    Acessa uma página web ou endpoint de documentação/API e retorna seu conteúdo textual.
    """
    if not url or not url.strip():
        return {
            "success": False,
            "error": "URL não fornecida.",
        }

    target_url = url.strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    try:
        response = httpx.get(
            target_url,
            headers={"User-Agent": USER_AGENT},
            timeout=20.0,
            follow_redirects=True,
        )

        content_type = response.headers.get("content-type", "")

        if "html" in content_type:
            text = clean_html(response.text)
        else:
            text = response.text

        truncated = len(text) > max_length
        if truncated:
            text = text[:max_length] + f"\n\n[... truncado em {max_length} caracteres de {len(response.text)} totais ...]"

        return {
            "success": True,
            "url": target_url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content": text,
            "truncated": truncated,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao acessar {target_url}: {e}",
        }


def download_file(url: str, destination: str) -> dict:
    """
    Baixa um arquivo da internet e salva no destino especificado dentro do projeto.
    """
    if not url or not url.strip():
        return {
            "success": False,
            "error": "URL não fornecida.",
        }

    dest_path = Path(destination).expanduser().resolve()
    writable, error_msg = is_path_writable(dest_path)
    if not writable:
        return {
            "success": False,
            "error": error_msg,
        }

    part_path = dest_path.with_name(dest_path.name + ".part")

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        bytes_written = 0

        with httpx.stream(
            "GET",
            url.strip(),
            headers={"User-Agent": USER_AGENT},
            timeout=60.0,
            follow_redirects=True,
        ) as response:
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Servidor retornou status {response.status_code}",
                }

            with open(part_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=16384):
                    bytes_written += len(chunk)

                    if bytes_written > MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Download excedeu o limite de {MAX_DOWNLOAD_BYTES} bytes."
                        )

                    f.write(chunk)

        # Só aparece no destino final quando o download terminou inteiro.
        os.replace(part_path, dest_path)

        return {
            "success": True,
            "url": url,
            "destination": str(dest_path),
            "bytes_downloaded": bytes_written,
        }

    except Exception as e:
        part_path.unlink(missing_ok=True)

        return {
            "success": False,
            "error": f"Erro ao baixar arquivo: {e}",
        }

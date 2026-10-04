# Skill: Consulta e Pesquisa no GitHub e Internet

## Objetivo

Instruir o agente sobre como pesquisar repositórios, releases, documentação, READMEs e arquivos de código no GitHub e na internet sem depender de tokens autenticados ou ferramentas pesadas.

---

## Métodos de Consulta

### 1. Pesquisa Web via Ferramenta
Use a ferramenta `web_search`:
```json
{
  "query": "llama.cpp releases github"
}
```
Isso retorna links e descrições dos principais resultados.

### 2. Consulta à API Pública do GitHub
A API do GitHub pode ser acessada via `fetch_url`:
- Para obter a última release de um projeto:
  `https://api.github.com/repos/<owner>/<repo>/releases/latest`
- Para obter tags:
  `https://api.github.com/repos/<owner>/<repo>/tags`
- Para obter conteúdo bruto de um arquivo (ex.: README):
  `https://raw.githubusercontent.com/<owner>/<repo>/main/README.md`

Exemplo:
`fetch_url(url="https://api.github.com/repos/ollama/ollama/releases/latest")`

### 3. Leitura de Documentação Web
Use `fetch_url`:
```json
{
  "url": "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/README.md"
}
```
A ferramenta limpa HTML quando aplicável e retorna o texto diretamente no contexto.

### 4. Operações com Git Local
Para repositórios clonados localmente:
- Verificar estado: `run_command(command="git status", reason="Verificar estado do repositorio")`
- Ver histórico: `run_command(command="git log -n 5 --oneline", reason="Verificar ultimos commits")`
- Ver alterações: `run_command(command="git diff", reason="Inspecionar diferencas de codigo")`

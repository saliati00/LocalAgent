# LocalAgent no Windows — manual simples

Este manual é para quem **nunca instalou nada disso**. Você só precisa de internet e de uns 30 minutos (a maior parte é esperar o download).

## O que você vai ter no final

Um assistente que roda **no seu próprio computador**, sem pagar nada, e que consegue ler arquivos, rodar comandos e pesquisar na internet quando você pede. Antes de qualquer ação mais séria, ele **pergunta a você**.

## O que o seu computador precisa ter

- Windows 10 ou 11 (versão atualizada).
- Placa de vídeo **NVIDIA** com driver instalado (a sua RTX 3070 serve). Se os jogos funcionam, o driver provavelmente está certo. Sem placa NVIDIA, funciona, mas fica muito lento.
- Uns **15 GB livres** no disco.
- Internet.

---

## Passo a passo

### Passo 1 — Colocar a pasta no computador
Copie a pasta **LocalAgent** inteira para algum lugar fácil, por exemplo `C:\LocalAgent` ou dentro de **Documentos**.
(Pode vir de pendrive, nuvem ou do GitHub: no GitHub, botão verde **Code** → **Download ZIP**, e depois clique com o botão direito no ZIP → **Extrair tudo**.)

> Evite pastas dentro do OneDrive ou com nomes muito longos.
> Se a pasta tiver uma subpasta chamada **.venv** vinda de outro computador, pode apagar: o instalador cria de novo (e recria sozinho se ela estiver quebrada).

### Passo 2 — Instalar tudo
1. Abra a pasta LocalAgent.
2. Dê **duplo clique** em **`instalar.bat`**.
3. Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.
4. Vai abrir uma janela preta com texto. **Não feche.** Ela faz sozinha:
   - confere/instala o Python, o Git e o Ollama (o programa que roda a IA);
   - cria o ambiente do projeto e instala as bibliotecas;
   - roda os testes do projeto;
   - pergunta se pode baixar o modelo de IA (cerca de **5 GB**). Digite **S** e aperte **ENTER**.
5. Pode aparecer uma janelinha do Windows pedindo permissão para instalar programas. Clique em **Sim**.
6. No final aparece **"PRONTO! Instalação concluída"**. Aperte qualquer tecla.

> Se o instalador pedir para **fechar a janela e rodar de novo**, é normal: acontece depois de instalar o Python ou o Ollama. Basta dar duplo clique em `instalar.bat` outra vez; ele continua de onde parou.

### Passo 3 — Conferir (opcional, mas recomendado)
Duplo clique em **`verificar.bat`**. Ele roda os testes e testa a conversa com a IA.
Se aparecer algo como *"Modelo qwen3:8b respondeu: conexão local funcionando"*, está tudo certo.

### Passo 4 — Usar
1. Duplo clique em **`iniciar.bat`**.
2. Quando aparecer **`Tarefa (ENTER vazio para sair):`**, escreva o que quer em português e aperte ENTER. Exemplos:
   - `Liste os arquivos da pasta workspace e me diga o que são.`
   - `Verifique se o git e o python estão instalados.`
   - `Crie um arquivo workspace/ola.txt com o texto "oi".`
3. **Tarefas numeradas (o jeito mais simples de dar continuidade):** digite `dê continuidade à tarefa 1` (ou `@tarefa1`, `@tarefa2`...). O agente carrega o roteiro da tarefa e **retoma de onde parou**. Comece pela tarefa 1. A lista e como saber se cada uma terminou estão em `tarefas\LEIA-ME.md`.
4. Para o desenvolvimento geral do projeto, digite **`@iniciar-desenvolvimento`**. Isso carrega o prompt salvo na pasta `prompts` (você pode abrir o arquivo e ajustar o texto).
5. Para sair, aperte ENTER sem escrever nada.

### Depois de usar: resumo dos números
Dê duplo clique em `verificar.bat` ou rode `.venv\Scripts\python scripts\summarize_logs.py`. Ele mostra o tamanho do prompt, tokens, avisos de contexto cheio e quantas vezes o agente pediu ajuda. Guarde essa saída para me mostrar.

---

## As perguntas que o agente faz

Quando ele quiser fazer algo mais sensível (instalar programa, apagar, rodar um script), aparece uma caixa assim:

```
AÇÃO REQUER CONFIRMAÇÃO
O que será feito: ...
Comando exato: ...
Pressione ENTER para executar.
Digite C e pressione ENTER para cancelar.
```

- **ENTER** = pode fazer.
- **C** + ENTER = cancela.
- Leia o "Comando exato". Na dúvida, **cancele**.

O agente **nunca** consegue alterar os arquivos que mandam nas regras dele (pasta `core`, `tests`, `agent.py`, etc.). Isso é de propósito.

## Quando o agente diz "preciso de você"
Se aparecer **`[NEEDS_HUMAN]`**, significa que a tarefa depende de algo que só você pode fazer (uma senha, uma decisão). Leia a mensagem, faça a parte que cabe a você e peça de novo.

---

## Se der problema

| O que aconteceu | O que fazer |
|---|---|
| "O winget não foi encontrado" | Abra a **Microsoft Store**, procure **Instalador de Aplicativo**, clique em **Atualizar**, e rode `instalar.bat` de novo. |
| "Python foi instalado, mas esta janela não o enxerga" | Feche a janela e dê duplo clique em `instalar.bat` outra vez. |
| Aviso: "Driver da NVIDIA não encontrado" | Instale o driver em nvidia.com/drivers e rode `instalar.bat` de novo. |
| "Não foi possível falar com o Ollama" | Abra o programa **Ollama** pelo menu Iniciar, ou dê duplo clique em `iniciar.bat` (ele abre sozinho). |
| "O modelo ... não foi baixado" | Abra o **Prompt de Comando** e rode `ollama pull qwen3:8b`. |
| O agente está muito lento | Feche jogos e navegadores pesados. Confira no `verificar.bat` se a placa NVIDIA foi detectada. |
| Algum teste falhou na instalação | Guarde o arquivo **`instalacao.log`** (fica na pasta) e mostre para quem te ajuda. |

Todos os passos da instalação ficam registrados em **`instalacao.log`**. O que o agente fez fica em **`logs\agent.log`**.

---

## Coisas úteis para saber

- **Desfazer uma mudança do agente:** antes de sobrescrever qualquer arquivo, o programa guarda a versão anterior na pasta `backups`. Para ver e restaurar: `.venv\Scripts\python scripts\restaurar.py list` e depois `.venv\Scripts\python scripts\restaurar.py restore "ID"` (copie o ID da lista). Restaurar também guarda a versão atual, então dá para voltar atrás.
- **O agente tem busca no projeto:** ele consegue procurar um texto nos arquivos sem ler tudo (ferramenta `search_files`), o que economiza memória do modelo.

- **Onde o agente trabalha:** ele só escreve dentro da pasta do projeto (e na pasta temporária do Windows). A pasta `workspace` é o lugar seguro para testar.
- **Skills novas:** o agente (o modelo mais forte, quando você tiver um) pode **propor** receitas novas, mas elas só passam a valer depois que **você** aprovar:
  - ver rascunhos: `.venv\Scripts\python scripts\promote_skill.py list`
  - ler um: `.venv\Scripts\python scripts\promote_skill.py show NOME`
  - aprovar: `.venv\Scripts\python scripts\promote_skill.py promote NOME` (digite o nome para confirmar)
  - recusar: `.venv\Scripts\python scripts\promote_skill.py reject NOME`
- **Modelo mais forte (14B):** o projeto prevê um segundo modelo maior para tarefas difíceis, mas ele **não é baixado pelo instalador**. Vem depois, com sua decisão (veja `specs/projeto.md`).
- **Atualizar o projeto:** se receber uma versão nova da pasta, substitua os arquivos e rode `instalar.bat` de novo (ele reaproveita o que já está instalado).
- **Desinstalar:** apague a pasta LocalAgent. O Ollama e o modelo ficam no Windows; para remover, use *Configurações → Aplicativos* (Ollama) e a pasta `C:\Users\SEU_USUARIO\.ollama`.

## Primeira rodada de testes
Depois de instalar, dê duplo clique em **`bateria.bat`**: ela roda sozinha dezenas de testes (1 a 1,5 hora, sem digitar nada) e grava um relatório em `logsbateria`. O **`ROTEIRO-DE-TESTES.md`** explica o que ela faz e os poucos testes manuais que restam.

## Resumo de 10 segundos

1. Copie a pasta → 2. `instalar.bat` → 3. `verificar.bat` → 4. `iniciar.bat` e escreva o que quer.

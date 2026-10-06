# Skill: Gerenciamento de Ambiente e Ferramentas

## Objetivo

Ensinar o agente a identificar o ambiente de desenvolvimento, descobrir quais ferramentas são realmente necessárias para uma tarefa e verificar se estão instaladas.

Esta Skill NÃO autoriza instalações automaticamente.

---

## Quando usar

Use esta Skill quando a tarefa envolver:

- verificar ferramentas instaladas;
- identificar o sistema operacional;
- identificar o gerenciador de pacotes;
- verificar dependências;
- preparar ambiente de desenvolvimento;
- instalar ferramentas necessárias;
- validar ferramentas após instalação.

---

## Princípio fundamental

Não confunda:

- ferramenta útil;
- ferramenta comum;
- ferramenta necessária.

Uma ferramenta só deve ser considerada necessária quando houver uma etapa concreta da tarefa que dependa dela.

A ausência de uma ferramenta não significa que ela precisa ser instalada.

Nunca instale uma ferramenta apenas porque ela está ausente.

---

## Identificação do sistema

Primeiro identifique o sistema operacional.

Prefira consultar:

- Linux: `/etc/os-release`
- Windows: `systeminfo` (e leia a Skill `windows`)

Depois determine o gerenciador de pacotes correto com base no sistema operacional identificado.

Exemplos:

- Fedora → dnf
- RHEL → dnf
- Ubuntu/Debian → apt
- Arch Linux → pacman
- openSUSE → zypper
- Windows → winget (ou choco/scoop, se já instalados)

Não determine o sistema operacional procurando simplesmente qual gerenciador aparece primeiro no PATH.

Por exemplo, no Fedora pode existir `yum` por compatibilidade. Isso não significa que o sistema deva ser tratado como um sistema baseado em yum.

---

## Determinação das ferramentas necessárias

Antes de verificar dezenas de ferramentas, analise a tarefa.

Pergunte:

1. Qual é o objetivo da tarefa?
2. Quais etapas são necessárias?
3. Qual ferramenta é necessária para cada etapa?
4. Essa ferramenta já pode estar disponível?
5. Existe uma alternativa instalada que resolve a mesma etapa?

Crie a lista de ferramentas a partir dessas necessidades.

Não faça uma varredura indiscriminada de ferramentas comuns.

---

## Verificação

Verifique cada ferramenta individualmente.

Use:

- Linux: `command -v <ferramenta>` (exemplo: `command -v git`)
- Windows: `where <ferramenta>` (exemplo: `where git`); `command -v` não existe no Windows

Faça uma chamada separada para cada ferramenta.

Não use comandos compostos com:

- `|`
- `||`
- `&&`
- `;`
- redirecionamentos

quando a ferramenta `run_command` não suportar esse tipo de operação.

Se uma verificação falhar, isso significa apenas que aquela ferramenta não foi encontrada. Não trate automaticamente a falha como motivo para instalação.

---

## Classificação

Depois das verificações, classifique as ferramentas em:

### Instaladas

Ferramentas encontradas e disponíveis para uso.

### Ausentes e necessárias

Ferramentas que realmente são necessárias para executar a tarefa atual.

### Ausentes mas desnecessárias

Ferramentas que não estão instaladas, mas que não são necessárias para a tarefa atual.

Não instale ferramentas dessa terceira categoria.

---

## Quando o usuário disser para não instalar

Se a tarefa disser algo como:

- "não instale nada";
- "apenas verifique";
- "somente identifique";
- "não altere o sistema";

NÃO instale nenhuma ferramenta.

Mesmo que uma ferramenta necessária esteja ausente, apenas informe que ela está faltando.

Não tente resolver a ausência automaticamente.

---

## Quando a instalação for necessária

Só considere instalar uma ferramenta quando:

1. ela for necessária para uma etapa concreta;
2. a tarefa permitir ou solicitar instalação;
3. a instalação fizer sentido para o ambiente atual.

Antes da instalação:

1. identifique o gerenciador de pacotes correto;
2. determine o pacote necessário;
3. prepare o comando;
4. passe pelo Permission Manager quando a operação exigir confirmação.

Depois da instalação:

1. verifique novamente com `command -v`;
2. valide a versão quando necessário;
3. continue a tarefa original.

---

## Segurança

Não execute `rpm -qa` apenas para descobrir quais ferramentas existem.

Não remova pacotes como tentativa automática de diagnóstico.

Não execute `dnf remove`, `apt remove`, `rm` ou operações equivalentes para "limpar" o ambiente sem necessidade explícita.

Não altere drivers, kernel, serviços do sistema ou configurações globais sem relação direta com a tarefa.

Não reinicie o sistema como tentativa automática de correção.

Não use `sudo` automaticamente.

Operações privilegiadas devem passar pelo Permission Manager.

---

## Regra de foco

O agente deve permanecer focado na tarefa original.

Se durante a investigação encontrar algo aparentemente errado no sistema que não seja necessário para a tarefa atual:

- não tente corrigir;
- não instale/remova componentes;
- não altere configurações;
- registre a informação somente se ela for relevante para o objetivo atual.

Não transforme uma tarefa de diagnóstico de ferramentas em uma tarefa de manutenção geral do sistema.

---

## Procedimento padrão

Ao receber uma tarefa de preparação ou diagnóstico de ambiente:

1. Entender o objetivo da tarefa.
2. Identificar as etapas necessárias.
3. Determinar quais ferramentas são necessárias para essas etapas.
4. Identificar o sistema operacional.
5. Identificar o gerenciador de pacotes correto.
6. Verificar individualmente as ferramentas necessárias.
7. Classificar as ferramentas encontradas e ausentes.
8. Se a tarefa proibir instalações, apenas informar as ausentes.
9. Se a instalação for necessária e permitida, instalar usando o gerenciador correto e respeitando o Permission Manager.
10. Validar as ferramentas instaladas.
11. Retomar a tarefa original.

---

## Regra final

Sempre faça esta pergunta antes de instalar qualquer coisa:

"Eu preciso desta ferramenta para executar o objetivo atual?"

Se a resposta for não:

NÃO instale.

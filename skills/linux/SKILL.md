# Skill: Operações e Diagnóstico Linux (Fedora KDE)

## Objetivo

Fornecer instruções e melhores práticas para diagnóstico do sistema operacional, verificação de hardware, inspeção de processos, gerenciamento de serviços e instalação de pacotes no ambiente Fedora 44 KDE.

---

## Identificação do Sistema e Recursos

### Sistema Operacional e Versão
```bash
cat /etc/os-release
uname -a
```

### CPU e Memória
```bash
lscpu
free -h
```

### Disco e Armazenamento
```bash
df -h
```

### GPU NVIDIA e VRAM
```bash
nvidia-smi
```
- Observe `Memory-Usage` (ex.: `6339MiB / 8192MiB`).
- Identifique processos ocupando VRAM (ex.: Ollama `llama-server`).

---

## Gerenciamento de Pacotes (DNF / RPM)

O sistema utiliza **Fedora** com **DNF**.

### Verificar se um executável existe no PATH
Prefira SEMPRE:
```bash
command -v <comando>
```
Exemplo: `command -v git` ou `command -v cmake`.

### Consultar informações de um pacote SEM instalar
```bash
dnf info <pacote>
```
ou para pacotes já instalados:
```bash
rpm -q <pacote>
```

### Regras de Segurança para Instalações
1. Não execute `rpm -qa` indiscriminadamente.
2. Nunca execute desinstalações (`dnf remove`, `rm`) para diagnosticar.
3. Se a tarefa permitir instalação e o pacote for estritamente necessário:
   - Apresente justificativa clara no `run_command`.
   - Lembre-se que operações com `sudo` ou `dnf install` passam pelo Permission Manager.
4. Após qualquer instalação, confirme a disponibilidade com `command -v <comando>`.

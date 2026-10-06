# Skill: Operações e Diagnóstico Windows

## Objetivo

Instruções para diagnosticar o sistema, verificar hardware e ferramentas e instalar software em um PC com **Windows 10/11**, usando `run_command` (que executa com `shell=False`).

---

## Regras da ferramenta `run_command` no Windows

- Não existe shell: `dir`, `type`, `echo`, `cd`, `copy`, `del` são comandos internos do `cmd` e **não** são executáveis. Para listar e ler arquivos use as ferramentas `list_directory` e `read_file`.
- Operadores `|`, `||`, `&&`, `;`, `&`, `>`, `<` são rejeitados. Faça uma chamada por comando.
- Caminhos usam `\` e podem ter unidade: `C:\Users\nome\arquivo.txt`. Use aspas se houver espaços: `"C:\Program Files\App\app.exe"`.
- O Python do projeto é o do `.venv\Scripts`; use `python` e `pytest` normalmente.

---

## Identificação do sistema e recursos

### Sistema operacional e hardware
```text
systeminfo
```

### GPU NVIDIA e VRAM
```text
nvidia-smi
```
- Observe `Memory-Usage` (ex.: `6339MiB / 8192MiB`).

### Consultas somente-leitura via PowerShell (não pedem confirmação)
```text
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController"
powershell -NoProfile -Command "Get-CimInstance Win32_Processor"
powershell -NoProfile -Command "Get-ComputerInfo"
powershell -NoProfile -Command "Get-Command git"
```
Somente estes cmdlets de leitura passam sem confirmação: `Get-ChildItem`, `Get-Content`, `Get-Command`, `Get-Location`, `Get-Process`, `Get-ComputerInfo`, `Get-CimInstance`, `Get-Item`, `Get-ItemProperty`, `Get-Date`, `Get-Host`, `Test-Path`, `Resolve-Path`. Qualquer outro comando PowerShell exige confirmação do usuário.

---

## Verificar se um executável existe no PATH

Use SEMPRE `where` (não existe `command -v` no Windows):
```text
where git
where cmake
where python
```
Se `where` não encontrar, a ferramenta não está no PATH; isso não significa que não esteja instalada.

---

## Gerenciamento de pacotes

Gerenciadores comuns: **winget** (nativo), **choco** e **scoop**.

### Consultar sem instalar
```text
winget search <pacote>
winget show <pacote>
```
(`winget` sempre passa pelo Permission Manager e pede confirmação.)

### Regras de segurança para instalações
1. Só instale se a tarefa permitir e a ferramenta for estritamente necessária.
2. Justifique no `reason` do `run_command`.
3. `winget`/`choco`/`scoop` com `install`, `update` ou `upgrade` são instalações: respeitam a restrição `allow_install` da tarefa.
4. Alterações de sistema (`reg`, `sc`, `icacls`, `takeown`, `netsh`, `schtasks`, `setx`) respeitam `allow_system_changes`.
5. Remoções (`del`, `rd`, `Remove-Item`) respeitam `allow_destructive`. Nunca remova nada só para diagnosticar.
6. Após instalar, confirme com `where <comando>`.

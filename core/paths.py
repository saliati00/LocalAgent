"""Caminhos centrais do projeto, independentes de SO e de onde o repositório foi clonado."""

import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SKILLS_DIR = PROJECT_ROOT / "skills"
SPECS_DIR = PROJECT_ROOT / "specs"
TASKS_DIR = PROJECT_ROOT / "tasks"
MODELS_DIR = PROJECT_ROOT / "models"
MEMORY_DIR = PROJECT_ROOT / "memory"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"

PROJECT_SPEC_PATH = SPECS_DIR / "projeto.md"
REGISTRY_PATH = MODELS_DIR / "registry.json"
MEMORY_STORE_PATH = MEMORY_DIR / "store.json"

TMP_ROOT = Path(tempfile.gettempdir()).resolve()

VENV_DIR = PROJECT_ROOT / ".venv"
VENV_BIN_DIR = VENV_DIR / ("Scripts" if os.name == "nt" else "bin")

LOGS_DIR = PROJECT_ROOT / "logs"
SKILLS_PENDING_DIR = PROJECT_ROOT / "skills_pending"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
TAREFAS_DIR = PROJECT_ROOT / "tarefas"

"""Configuration centralisée, lue depuis l'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "data" / "demo_odoo.sqlite"
DEFAULT_KB = PROJECT_ROOT / "data" / "kb"


def load_dotenv(path: Path | None = None) -> None:
    """Charge un fichier .env sans dépendance externe.

    Les variables déjà présentes dans l'environnement ont la priorité : un
    export explicite doit toujours l'emporter sur le fichier.
    """
    env_file = path or PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


# Doit s'exécuter avant l'évaluation des valeurs par défaut de Settings.
load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Paramètres d'exécution.

    `max_rows` et `query_timeout_s` sont des garde-fous : même si le modèle
    génère une requête coûteuse, elle est bornée en volume et en durée.
    """

    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}")
    kb_path: Path = Path(os.getenv("KB_PATH", str(DEFAULT_KB)))
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5")
    max_rows: int = _int_env("MAX_ROWS", 200)
    query_timeout_s: int = _int_env("QUERY_TIMEOUT_S", 10)
    max_agent_steps: int = _int_env("MAX_AGENT_STEPS", 8)
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls()

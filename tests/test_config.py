from __future__ import annotations

import os
from pathlib import Path

from odoo_ai_agent.config import Settings, load_dotenv


def test_dotenv_charge_les_valeurs(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# commentaire\nMA_CLE_TEST=valeur123\nAUTRE='avec quotes'\n\n", encoding="utf-8"
    )
    monkeypatch.delenv("MA_CLE_TEST", raising=False)
    monkeypatch.delenv("AUTRE", raising=False)
    load_dotenv(env_file)
    assert os.environ["MA_CLE_TEST"] == "valeur123"
    assert os.environ["AUTRE"] == "avec quotes"


def test_environnement_prioritaire_sur_dotenv(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    env_file = tmp_path / ".env"
    env_file.write_text("PRIORITE_TEST=depuis_le_fichier\n", encoding="utf-8")
    monkeypatch.setenv("PRIORITE_TEST", "depuis_l_environnement")
    load_dotenv(env_file)
    assert os.environ["PRIORITE_TEST"] == "depuis_l_environnement"


def test_fichier_absent_ne_leve_pas() -> None:
    load_dotenv(Path("/chemin/qui/n/existe/pas/.env"))


def test_valeurs_par_defaut() -> None:
    settings = Settings()
    assert settings.max_rows > 0
    assert settings.max_agent_steps > 0
    assert settings.database_url.startswith(("sqlite", "postgres"))

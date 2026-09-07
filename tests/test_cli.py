"""Test de fumée de l'interface en ligne de commande.

Ce test existe parce que le README documentait `python -m odoo_ai_agent`
alors que le paquet n'avait pas de `__main__.py`. Soixante et un tests
étaient verts, et la commande annoncée ne fonctionnait pas : ils couvraient
la logique interne, jamais l'interface publique.
"""

from __future__ import annotations

import subprocess
import sys


def test_le_module_est_executable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "odoo_ai_agent", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "ask" in result.stdout
    assert "shell" in result.stdout
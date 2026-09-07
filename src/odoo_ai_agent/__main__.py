"""Point d'entrée du paquet : permet `python -m odoo_ai_agent`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
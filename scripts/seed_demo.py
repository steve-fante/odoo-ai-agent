"""Génère une base SQLite qui imite un schéma Odoo réduit.

Objectif : permettre à n'importe qui de cloner le dépôt et de lancer l'agent en
une commande, sans installer Odoo ni PostgreSQL. Les noms de tables et de
colonnes reprennent ceux d'Odoo (res_partner, sale_order, account_move…), si
bien que les requêtes écrites ici restent valables sur une vraie base.

La graine aléatoire est fixe : les chiffres sont donc reproductibles, ce qui
permet aux évaluations de comparer la réponse de l'agent à une vérité terrain.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42

SCHEMA = """
CREATE TABLE res_country (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL
);

CREATE TABLE res_partner (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    is_company INTEGER NOT NULL,
    country_id INTEGER REFERENCES res_country(id),
    customer_rank INTEGER NOT NULL,
    supplier_rank INTEGER NOT NULL,
    create_date TEXT NOT NULL
);

CREATE TABLE product_category (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE product_template (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    categ_id INTEGER REFERENCES product_category(id),
    list_price REAL NOT NULL,
    standard_price REAL NOT NULL,
    type TEXT NOT NULL
);

CREATE TABLE sale_order (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    partner_id INTEGER REFERENCES res_partner(id),
    date_order TEXT NOT NULL,
    state TEXT NOT NULL,
    amount_untaxed REAL NOT NULL,
    amount_total REAL NOT NULL
);

CREATE TABLE sale_order_line (
    id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES sale_order(id),
    product_id INTEGER REFERENCES product_template(id),
    product_uom_qty REAL NOT NULL,
    price_unit REAL NOT NULL,
    price_subtotal REAL NOT NULL
);

CREATE TABLE account_move (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    partner_id INTEGER REFERENCES res_partner(id),
    invoice_date TEXT NOT NULL,
    move_type TEXT NOT NULL,
    state TEXT NOT NULL,
    payment_state TEXT NOT NULL,
    amount_total REAL NOT NULL
);

CREATE TABLE stock_location (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    usage TEXT NOT NULL
);

CREATE TABLE stock_quant (
    id INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES product_template(id),
    location_id INTEGER REFERENCES stock_location(id),
    quantity REAL NOT NULL
);
"""

COUNTRIES = [
    (1, "France", "FR"),
    (2, "Belgique", "BE"),
    (3, "Suisse", "CH"),
    (4, "Espagne", "ES"),
    (5, "Allemagne", "DE"),
    (6, "Cameroun", "CM"),
]

CATEGORIES = [
    (1, "Matières premières"),
    (2, "Produits finis"),
    (3, "Emballages"),
    (4, "Prestations de services"),
    (5, "Maintenance"),
]

COMPANY_WORDS_A = [
    "Atlantique", "Bocage", "Cristal", "Delta", "Estuaire", "Forézienne", "Garance",
    "Hermine", "Iroise", "Jade", "Korrigan", "Lisière", "Mistral", "Novéa", "Ombelle",
    "Pastel", "Quartz", "Rivage", "Sillon", "Tramontane",
]
COMPANY_WORDS_B = [
    "Industries", "Distribution", "Services", "Agro", "Logistique", "Conseil",
    "Technologies", "Négoce",
]
FIRST_NAMES = ["Claire", "Julien", "Awa", "Marc", "Léa", "Samir", "Nina", "Thomas"]
LAST_NAMES = ["Bertin", "Moreau", "Ngassa", "Lefèvre", "Ollivier", "Roux", "Vasseur"]

PRODUCT_NAMES = [
    "Pomme de terre calibre 40/60", "Pomme de terre calibre 60/80", "Frite fraîche 9 mm",
    "Purée déshydratée 5 kg", "Flocon de pomme de terre", "Amidon alimentaire",
    "Carton 10 kg imprimé", "Film plastique alimentaire", "Palette bois EUR",
    "Étiquette adhésive rouleau", "Sac kraft 25 kg", "Bac plastique 600x400",
    "Prestation d'installation", "Formation utilisateurs (jour)", "Maintenance annuelle",
    "Audit de process", "Transport frigorifique", "Nettoyage industriel",
    "Contrôle qualité laboratoire", "Location matériel (semaine)",
]

LOCATIONS = [
    (1, "Stock/Entrepôt principal", "internal"),
    (2, "Stock/Chambre froide", "internal"),
    (3, "Partenaires/Clients", "customer"),
    (4, "Partenaires/Fournisseurs", "supplier"),
]

SALE_STATES = ["draft", "sent", "sale", "done", "cancel"]
SALE_STATE_WEIGHTS = [12, 8, 40, 32, 8]


def _partners(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    start = date(2022, 1, 1)
    for i in range(1, 41):
        is_company = 1 if i <= 30 else 0
        if is_company:
            name = f"{rng.choice(COMPANY_WORDS_A)} {rng.choice(COMPANY_WORDS_B)}"
        else:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        country = rng.choices([1, 2, 3, 4, 5, 6], weights=[60, 10, 8, 8, 8, 6])[0]
        supplier = 1 if i % 5 == 0 else 0
        customer = 0 if supplier else 1
        created = start + timedelta(days=rng.randint(0, 900))
        rows.append((i, name, is_company, country, customer, supplier, created.isoformat()))
    return rows


def _products(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    for i, name in enumerate(PRODUCT_NAMES, start=1):
        categ = 4 if i >= 13 else (3 if i >= 7 else rng.choice([1, 2]))
        kind = "service" if categ in (4, 5) else "product"
        cost = round(rng.uniform(2, 240), 2)
        price = round(cost * rng.uniform(1.25, 2.1), 2)
        rows.append((i, name, categ, price, cost, kind))
    return rows


def seed(output: Path | str = "data/demo_odoo.sqlite") -> Path:
    rng = random.Random(SEED)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)

    conn.executemany("INSERT INTO res_country VALUES (?,?,?)", COUNTRIES)
    conn.executemany("INSERT INTO product_category VALUES (?,?)", CATEGORIES)
    conn.executemany("INSERT INTO stock_location VALUES (?,?,?)", LOCATIONS)

    partners = _partners(rng)
    conn.executemany("INSERT INTO res_partner VALUES (?,?,?,?,?,?,?)", partners)

    products = _products(rng)
    conn.executemany("INSERT INTO product_template VALUES (?,?,?,?,?,?)", products)

    customers = [p[0] for p in partners if p[4] == 1]
    orders: list[tuple] = []
    lines: list[tuple] = []
    line_id = 1
    base_day = date(2024, 1, 8)

    for order_id in range(1, 161):
        partner = rng.choice(customers)
        order_date = base_day + timedelta(days=rng.randint(0, 640))
        state = rng.choices(SALE_STATES, weights=SALE_STATE_WEIGHTS)[0]
        untaxed = 0.0
        for _ in range(rng.randint(1, 4)):
            product = rng.choice(products)
            qty = float(rng.randint(1, 40))
            unit = round(product[3] * rng.uniform(0.9, 1.05), 2)
            subtotal = round(qty * unit, 2)
            untaxed += subtotal
            lines.append((line_id, order_id, product[0], qty, unit, subtotal))
            line_id += 1
        untaxed = round(untaxed, 2)
        orders.append(
            (
                order_id,
                f"SO{order_id:05d}",
                partner,
                order_date.isoformat(),
                state,
                untaxed,
                round(untaxed * 1.20, 2),
            )
        )

    conn.executemany("INSERT INTO sale_order VALUES (?,?,?,?,?,?,?)", orders)
    conn.executemany("INSERT INTO sale_order_line VALUES (?,?,?,?,?,?)", lines)

    moves: list[tuple] = []
    move_id = 1
    for order in orders:
        if order[4] not in ("sale", "done"):
            continue
        invoice_date = date.fromisoformat(order[3]) + timedelta(days=rng.randint(1, 25))
        payment = rng.choices(["paid", "not_paid", "partial"], weights=[68, 22, 10])[0]
        moves.append(
            (
                move_id,
                f"INV/{invoice_date.year}/{move_id:05d}",
                order[2],
                invoice_date.isoformat(),
                "out_invoice",
                "posted",
                payment,
                order[6],
            )
        )
        move_id += 1

    conn.executemany("INSERT INTO account_move VALUES (?,?,?,?,?,?,?,?)", moves)

    quants: list[tuple] = []
    quant_id = 1
    for product in products:
        if product[5] != "product":
            continue
        for location in (1, 2):
            quants.append((quant_id, product[0], location, float(rng.randint(0, 900))))
            quant_id += 1
    conn.executemany("INSERT INTO stock_quant VALUES (?,?,?,?)", quants)

    conn.commit()
    conn.close()
    return path


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "data/demo_odoo.sqlite"
    created = seed(target)
    print(f"Base de démonstration créée : {created}")

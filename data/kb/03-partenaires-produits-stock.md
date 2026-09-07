# Partenaires, produits et stock

## `res_partner` — clients, fournisseurs et contacts

Odoo ne sépare pas les clients des fournisseurs : tout est un partenaire. La
distinction se fait par deux compteurs.

- `customer_rank > 0` : le partenaire est un client.
- `supplier_rank > 0` : le partenaire est un fournisseur.
- `is_company = 1` : société ; `is_company = 0` : personne physique.
- `country_id` pointe vers `res_country`.

Un même partenaire peut être à la fois client et fournisseur : les deux compteurs
sont alors positifs. Ne jamais supposer l'exclusivité.

## `product_template` — catalogue

- `list_price` : prix de vente public.
- `standard_price` : coût de revient. La marge unitaire théorique vaut
  `list_price - standard_price`.
- `type` : `product` pour un article stockable, `service` pour une prestation.
  Les services n'apparaissent jamais dans `stock_quant`.
- `categ_id` pointe vers `product_category`.

## `stock_quant` et `stock_location` — stock disponible

`stock_quant` donne la quantité d'un produit à un emplacement donné.

`stock_location.usage` précise la nature de l'emplacement :

| Valeur     | Signification                                            |
|------------|----------------------------------------------------------|
| `internal` | Emplacement physique de l'entreprise. Compte dans le stock. |
| `customer` | Emplacement virtuel client (marchandise livrée).          |
| `supplier` | Emplacement virtuel fournisseur (marchandise attendue).   |
| `inventory`| Écart d'inventaire.                                       |

**Règle de gestion.** Le stock réel disponible se calcule uniquement sur les
emplacements dont `usage = 'internal'`. Additionner tous les emplacements donne
un résultat systématiquement faux.

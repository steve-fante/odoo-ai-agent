# Cycle de vente Odoo — table `sale_order`

Un bon de commande client est stocké dans `sale_order`. Les lignes détaillées se
trouvent dans `sale_order_line`, reliées par `sale_order_line.order_id`.

## Champ `state` : les statuts possibles

| Valeur   | Signification métier                                                        |
|----------|------------------------------------------------------------------------------|
| `draft`  | Devis en cours de rédaction, non envoyé au client. Aucun engagement.         |
| `sent`   | Devis envoyé au client, en attente de réponse.                              |
| `sale`   | Bon de commande confirmé. C'est le passage à l'engagement commercial ferme.  |
| `done`   | Commande verrouillée, livrée et clôturée.                                    |
| `cancel` | Commande annulée. À exclure de tout calcul de chiffre d'affaires.            |

**Règle de gestion importante.** Le chiffre d'affaires commandé se calcule sur les
états `sale` et `done` uniquement. Inclure `draft` ou `sent` reviendrait à compter
des devis qui ne se transformeront pas tous. Inclure `cancel` est toujours une erreur.

## Montants

- `amount_untaxed` : total hors taxes de la commande.
- `amount_total` : total toutes taxes comprises.
- Dans cette base de démonstration, le taux appliqué est de 20 % : on a donc
  `amount_total = amount_untaxed * 1.20`.

Pour une analyse de performance commerciale, on privilégie `amount_untaxed`,
qui neutralise l'effet des taux de TVA différents selon les pays.

## Dates

`date_order` porte la date de commande, au format `AAAA-MM-JJ`. Pour agréger par
mois en SQLite, utiliser `substr(date_order, 1, 7)`. Sur PostgreSQL, préférer
`date_trunc('month', date_order)`.

## Lignes de commande

`sale_order_line` contient :

- `product_uom_qty` : quantité commandée ;
- `price_unit` : prix unitaire négocié, qui peut différer du `list_price` du produit ;
- `price_subtotal` : montant hors taxes de la ligne, soit `product_uom_qty * price_unit`.

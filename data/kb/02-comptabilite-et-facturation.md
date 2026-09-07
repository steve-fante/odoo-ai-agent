# Comptabilité et facturation — table `account_move`

`account_move` regroupe toutes les pièces comptables : factures clients, factures
fournisseurs, avoirs et écritures diverses. Le champ discriminant est `move_type`.

## Champ `move_type`

| Valeur        | Signification                        |
|---------------|--------------------------------------|
| `out_invoice` | Facture client (vente)               |
| `out_refund`  | Avoir client                         |
| `in_invoice`  | Facture fournisseur (achat)          |
| `in_refund`   | Avoir fournisseur                    |
| `entry`       | Écriture comptable diverse           |

**Piège classique.** Une requête sur le chiffre d'affaires facturé doit filtrer
`move_type = 'out_invoice'`. Sans ce filtre, on additionne les achats et les ventes.

## Champ `state`

| Valeur   | Signification                                              |
|----------|------------------------------------------------------------|
| `draft`  | Facture brouillon, non comptabilisée. À exclure des totaux. |
| `posted` | Facture comptabilisée, juridiquement émise.                |
| `cancel` | Facture annulée.                                            |

## Champ `payment_state`

| Valeur      | Signification                                        |
|-------------|------------------------------------------------------|
| `not_paid`  | Aucun règlement reçu.                                |
| `partial`   | Règlement partiel.                                   |
| `paid`      | Facture entièrement réglée.                          |
| `in_payment`| Paiement enregistré mais non encore rapproché.       |
| `reversed`  | Facture extournée par un avoir.                      |

**Encours client** = somme des `amount_total` des factures `out_invoice`,
`state = 'posted'`, dont `payment_state` vaut `not_paid` ou `partial`.

## Montant

`amount_total` est le montant TTC de la pièce. Il n'existe pas de champ
`amount_untaxed` dans cette base de démonstration pour `account_move`.

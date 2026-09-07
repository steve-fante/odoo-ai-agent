# Conventions Odoo et pièges fréquents

## Nommage

- Les tables reprennent le nom du modèle Odoo, les points remplacés par des
  tirets bas : le modèle `sale.order` devient la table `sale_order`.
- Toute table possède une clé primaire `id` de type entier.
- Une relation Many2one se matérialise par une colonne suffixée `_id`
  (`partner_id`, `product_id`, `categ_id`).
- Les champs monétaires sont des réels. Arrondir à deux décimales à l'affichage.

## Pièges les plus fréquents

1. **Oublier de filtrer les états.** Compter les commandes `cancel` ou les
   factures `draft` fausse tous les indicateurs commerciaux.
2. **Confondre `sale_order.amount_total` et la somme des lignes.** La somme des
   `price_subtotal` correspond à `amount_untaxed`, pas au TTC.
3. **Joindre `sale_order` et `account_move` par le partenaire.** Ce lien n'est pas
   fiable : un client peut avoir plusieurs commandes et plusieurs factures. Les
   deux tables s'analysent séparément.
4. **Ignorer `usage` dans `stock_location`.** Voir la fiche stock.
5. **Compter les partenaires sans filtrer `customer_rank`.** La table contient
   aussi les fournisseurs et les contacts.

## Agrégations temporelles

En SQLite, il n'existe pas de `date_trunc`. Utiliser :

- année : `substr(date_order, 1, 4)`
- mois : `substr(date_order, 1, 7)`

Sur PostgreSQL, `date_trunc('month', date_order)` reste préférable.

## Volumétrie de la base de démonstration

Ordres de grandeur, utiles pour vérifier qu'une requête n'a pas dérapé :

- environ 40 partenaires, dont une trentaine de sociétés ;
- 20 produits répartis en 5 catégories ;
- 160 bons de commande couvrant 2024 et 2025 ;
- une facture client par commande confirmée ou clôturée.

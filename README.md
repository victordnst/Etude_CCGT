# Modélisation Économique & Dispatching d'une Centrale CCGT

Ce projet personnel explore la rentabilité opérationnelle d'une centrale à cycle combiné gaz (CCGT) type de 400 MW sur le marché français de l'électricité en 2025. 

L'objectif est de relier concrètement le fonctionnement physique d'un actif thermique aux signaux de prix de marché en utilisant Python.

---

## 1. Données utilisées

Le script traite et croise des données réelles de marché :
- **Électricité (Spot France 2025) :** Prix Day-Ahead (EPEX Spot / ENTSO-E) et consommation nationale d'électricité (load).
- **Gaz naturel :** Cours quotidiens des contrats à terme TTF (Title Transfer Facility).
- **Quotas d'émission de CO2 :** Prix des quotas européens (EU ETS).

Le pipeline synchronise les pas de temps (rééchantillonnage de la fréquence quart-horaire au pas journalier) et propage les cours financiers du vendredi sur le week-end pour assurer l'alignement des séries temporelles.

---

## 2. Logique de calcul

Pour déterminer si l'actif doit tourner ou non, le script calcule la marge nette journalière :

1. **Spark Spread (€/MWh) :** Marge brute entre la vente d'électricité et le coût du combustible.  
   $$\text{Spark Spread} = \text{Prix Électricité} - \frac{\text{Prix Gaz}}{\text{Rendement}}$$
   *(Rendement thermique de base fixé à 50 %)*

2. **Clean Spark Spread (€/MWh) :** Marge nette après intégration du coût du carbone.  
   $$\text{Clean Spark Spread} = \text{Spark Spread} - (\text{Facteur d'émission} \times \text{Prix Carbone})$$
   *(Facteur d'émission standard retenu : 0,411 tCO2/MWh)*

3. **Décision de dispatching :** L'unité produit uniquement lorsque le Clean Spark Spread est positif. Si la marge est négative, l'actif s'arrête afin d'éviter les pertes opérationnelles (`CSS_Realise = max(CSS, 0)`).

---

## 3. Résultats & Enseignements

- **Activation selon la tension réseau :** En visualisant la relation entre consommation nationale et marge opérationnelle, on observe empiriquement l'ordre de mérite (*merit order*) : la centrale démarre principalement lors des pointes de demande hivernales, lorsque le prix de l'électricité compense le coût cumulé du combustible et du carbone.
- **Sensibilité au rendement :** Une variation du rendement de l'installation (testée de 45 % à 60 %) modifie sensiblement le nombre de jours rentables et le cash-flow capté.
- **Couverture des coûts fixes :** L'analyse montre que le cash-flow généré sur le seul marché Spot ne suffit pas toujours à couvrir l'ensemble des coûts fixes annuels d'exploitation (FOM estimés à 30 000 €/MW/an). Cela illustre concrètement l'intérêt des mécanismes de capacité pour assurer la viabilité économique de moyens de pointe indispensables à la sécurité d'approvisionnement.

---

## 4. Structure du projet

```text
├── DATA/                  # Données brutes (Spot, Conso, Gaz TTF, Carbone)
├── figures/               # Graphiques générés (CSS temporel, Merit order, Sensibilité)
├── ccgt_analysis.py       # Script Python de calcul et visualisation
├── requirements.txt       # pandas, matplotlib
└── README.md
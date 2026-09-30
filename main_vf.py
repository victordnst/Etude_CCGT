import matplotlib.pyplot as plt
import pandas as pd


#____________ Paramètres ____________ 

RENDEMENT_REF = 0.50          # Rendement thermique de base (50%)
FACTEUR_EMISSION = 0.411      # Facteur d'émission standard CCGT (tCO2/MWh)
PUISSANCE_CENTRALE_MW = 400    # Puissance installée (MW)
COUTS_FIXES_FOM = 30000        # Coûts fixes annuels en €/MW/an


#______________________________ Préparation des données ______________________________

# Marché Spot Électricité Français 2025
df_prix_elec = pd.read_csv('DATA/ENERGY_PRICES_2025.csv')
df_prix_elec['Date'] = pd.to_datetime(
    df_prix_elec['MTU (UTC)'].str.split(' - ').str[0], 
    format='%d/%m/%Y %H:%M:%S'
)
df_prix_elec = df_prix_elec.set_index('Date')[['Day-ahead Price (EUR/MWh)']]

# Consommation Française 2025
df_conso = pd.read_csv('DATA/DAYAHEAD_2025.csv')
df_conso['Date'] = pd.to_datetime(
    df_conso['MTU (UTC)'].str.split(' - ').str[0], 
    format='%d/%m/%Y %H:%M'
)
df_conso = df_conso.set_index('Date')[['Actual Total Load (MW)']]

# Fusion et modification fréquence (15min -> Day)
df_quarthoraire = pd.concat([df_prix_elec, df_conso], axis=1, join='inner').dropna()
df_quotidien_physique = df_quarthoraire.resample('D').mean()

# Gaz TTF et Quotas CO2
df_gaz = pd.read_csv(
    'DATA/ICE Dutch TTF Natural Gas Futures Historical Data.csv',
    index_col='Date', parse_dates=True, thousands=','
)[['Price']].rename(columns={'Price': 'Gas Price EUR'}).sort_index()

df_carbone = pd.read_csv(
    'DATA/Carbon Emissions Futures Historical Data.csv',
    index_col='Date', parse_dates=True, thousands=','
)[['Price']].rename(columns={'Price': 'Carbon Price EUR'}).sort_index()

df_quotidien_financier = pd.concat([df_gaz, df_carbone], axis=1, join='inner').dropna()

# Propagation des cours du vendredi sur le week-end
df_marche = df_quotidien_physique.join(df_quotidien_financier, how='left')
df_marche = df_marche.ffill().bfill()


#____________ Modélisation de la rentabilité (spark spread et clean spark spread) ____________ 

# Marge brute (Spark Spread)
df_marche['Spark_Spread'] = (
    df_marche['Day-ahead Price (EUR/MWh)'] - (df_marche['Gas Price EUR'] / RENDEMENT_REF)
)

# Marge nette décarbonée (Clean Spark Spread)
df_marche['Clean_Spark_Spread'] = (
    df_marche['Spark_Spread'] - (FACTEUR_EMISSION * df_marche['Carbon Price EUR'])
)

# Non démarrage de l'usine si la marge est négative
df_marche['CSS_Realise'] = df_marche['Clean_Spark_Spread'].clip(lower=0)

# Euros par jour pour 1 MW disponible (24h de fonctionnement)
df_marche['Gain_Journalier_EUR_par_MW'] = df_marche['CSS_Realise'] * 24

#Matrice de corrélation pour analyser les facteurs explicatifs
print("\n __________ Corrélations avec le Clean Spark Spread ____________\n")
correlation_matrice = df_marche.corr().round(3)
print(correlation_matrice['Clean_Spark_Spread'])

# Diagnostics
taux_activation = (df_marche['Clean_Spark_Spread'] > 0).mean() * 100
css_moyen_brut = df_marche['Clean_Spark_Spread'].mean()
jours_rentables = df_marche[df_marche['Clean_Spark_Spread'] > 0]

print("_" * 65)
print("                INDICATEURS DE RENTABILITÉ OPÉRATIONNELLE\n")

print(f"CSS > 0 : {taux_activation:.1f} % de l'année ({len(jours_rentables)} jours)")
print(f"Clean Spark Spread Moyen Annuel      : {css_moyen_brut:.2f} €/MWh")
print(f"Marge Réalisée Moyenne en Activité   : {jours_rentables['CSS_Realise'].mean():.2f} €/MWh")

# Analyse du seuil de tension réseau
charge_moyenne_annuelle = (df_marche['Actual Total Load (MW)'] / 1000).mean()
charge_moyenne_active = (jours_rentables['Actual Total Load (MW)'] / 1000).mean()

print(f"Consommation moyenne annuelle           : {charge_moyenne_annuelle:.2f} GW")
print(f"Consommation requise pour activer le CCGT: {charge_moyenne_active:.2f} GW")
print(f"Prime de tension réseau requise          : {charge_moyenne_active - charge_moyenne_annuelle:.2f} GW")
print("_" * 65)


#____________ Analyse de sensibilité au rendement de l'usine ____________ 

rendements_testes = [0.45, 0.50, 0.55, 0.60]
resultats_sensibilite = []

for r in rendements_testes:
    css_sim = (
        df_marche['Day-ahead Price (EUR/MWh)'] - (df_marche['Gas Price EUR'] / r)
        - (FACTEUR_EMISSION * df_marche['Carbon Price EUR'])
    )
    jours_itm = (css_sim > 0).mean() * 100
    css_actif = css_sim[css_sim > 0]
    cash_flow_annuel = css_sim.clip(lower=0).sum() * 24
    
    resultats_sensibilite.append({
        'Rendement (%)': int(r * 100),
        'Jours Rentables (%)': round(jours_itm, 1),
        'CSS Réalisé Moyen (€/MWh)': round(css_actif.mean(), 2) if (css_sim > 0).any() else 0.0,
        'Cash-Flow (€/MW/an)': round(cash_flow_annuel, 1)
    })

df_sensibilite = pd.DataFrame(resultats_sensibilite)

print("\n" + "_" * 65)
print("             RÉSULTATS DE L'ANALYSE DE SENSIBILITÉ\n")

print(df_sensibilite.to_string(index=False))
print("_" * 65)


#____________ Diagnostic économique ____________ 

cash_flow_spot_mw_an = df_marche['Gain_Journalier_EUR_par_MW'].sum()
deficit_par_mw = cash_flow_spot_mw_an - COUTS_FIXES_FOM
perte_totale_annuelle = deficit_par_mw * PUISSANCE_CENTRALE_MW

print("\n" + "_" * 65)
print(f"       BILAN ÉCONOMIQUE SPOT (CENTRALE TYPE DE {PUISSANCE_CENTRALE_MW} MW)\n")

print(f"Cash-flow capté sur le marché Spot : {cash_flow_spot_mw_an:,.1f} €/MW/an")
print(f"Coûts fixes annuels d'exploitation : {COUTS_FIXES_FOM:,.1f} €/MW/an")
print(f"Solde net unitaire avant capacité  : {deficit_par_mw:,.1f} €/MW/an")
print(f"Déficit net total pour {PUISSANCE_CENTRALE_MW} MW       : {perte_totale_annuelle:,.1f} €\n")

print("CONCLUSION :")
print("Le marché Spot seul ne permet pas l'équilibre financier de l'actif.")
print(f"Une rémunération de capacité d'au moins {abs(deficit_par_mw):,.0f} €/MW/an")
print("est indispensable pour maintenir cette unité disponible pour le système.")



#____________ Visualisation graphique ____________ 

# Chronologie du Clean Spark Spread
plt.figure(figsize=(10, 4))
plt.plot(df_marche.index, df_marche['Clean_Spark_Spread'], label='Clean Spark Spread (€/MWh)', color='#1f77b4', lw=1)
plt.axhline(0, color='crimson', linestyle='--', alpha=0.8, label='Seuil de rentabilité')
plt.title("Clean Spark Spread CCGT 2025", fontsize=11, fontweight='bold')
plt.ylabel("€/MWh")
plt.grid(alpha=0.3)
plt.legend(loc='lower left')
plt.tight_layout()
plt.show()

# Validation empirique de l'ordre de mérite
plt.figure(figsize=(8, 4.5))
plt.scatter(df_marche['Actual Total Load (MW)'] / 1000, df_marche['Clean_Spark_Spread'], alpha=0.7, edgecolors='none', color='#2ca02c')
plt.axhline(0, color='crimson', linestyle='--', alpha=0.8)
plt.xlabel("Consommation Nationale (GW)")
plt.ylabel("Clean Spark Spread (€/MWh)")
plt.title("Courbe de merit order: CSS(Charge)", fontsize=11, fontweight='bold')
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()

# Sensibilité du Cash-flow au rendement
plt.figure(figsize=(7, 4))
plt.bar(df_sensibilite['Rendement (%)'].astype(str) + '%', df_sensibilite['Cash-Flow (€/MW/an)'], color='#3182bd', width=0.5)
plt.axhline(COUTS_FIXES_FOM, color='crimson', linestyle='--', label=f'Coûts Fixes ({COUTS_FIXES_FOM:,} €/MW/an)')
plt.title("Cash-Flow Annuel Spot selon le Rendement Thermique", fontsize=11, fontweight='bold')
plt.xlabel("Rendement Thermique")
plt.ylabel("€ / MW / an")
plt.grid(axis='y', alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()












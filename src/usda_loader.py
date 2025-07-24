import pandas as pd

# --------------------
# usda_loader.py
# --------------------
# Purpose:
#   Calculate the Food Insecurity Score as well as the Food Resilience Score
#   Combine enriched socioeconomic data with USDA Food Access Research Atlas data
#   to compute a county-level Food Insecurity Score (FIS) and its resilience food metric
# Input:
#   - data/socioeconomic_full.csv --> counties with poverty, education, and housing metrics.
#   - data/2019 Food Access Research Atlas Data/Food Access Research Atlas.csv --> tract-level LILA flags and low-access percentages.
# Output:
#   data/food_access_score.csv

# load and pads the FIPS with zeros
census = pd.read_csv('data/socioeconomic_full.csv', dtype=str)
census['county'] = census['county'].str.zfill(3)

atlas = pd.read_csv('data/2019 Food Access Research Atlas Data/Food Access Research Atlasp.csv', dtype=str, low_memory=False)
# extract FIPS
atlas['State']  = atlas['CensusTract'].str[:2]
atlas['county'] = atlas['CensusTract'].str[2:5]
atlas = atlas[atlas['State']=='13']  # Georgia only
# casts LILA (Low Income, Low Access)
atlas['LILATracts_1And10'] = atlas['LILATracts_1And10'].astype(int)

# Calculates the fraction of LILA tracts that are flagged
county_flag = (
    atlas.groupby(['State','county'])
         .agg(frac_lila_tracts=('LILATracts_1And10','mean'))
         .reset_index()
)

# Merges with the socioeconomic_full.csv file we made earlier
merged = census.merge(county_flag, on=['State','county'], how='left')

# Renames columns
merged = merged.rename(columns={'frac_lila_tracts':'FIS'})
merged['Resilience_Food'] = 1 - merged['FIS']

merged.to_csv('data/food_access_score.csv', index=False)
print("✅ food_access_score.csv written")

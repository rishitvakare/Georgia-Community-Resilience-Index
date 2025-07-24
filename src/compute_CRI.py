import os
import pandas as pd
from pathlib import Path

# Will compute the final CRI score
# Will apply equal weights (1/3) to each of the three metrics:  
#   - Food Insecurity Score (FIS)
#   - Healthcare Uninsured Count
#   - Socioeconomic Vulnerability (SEV)

# For now, we are keeping the default weights = 1/3

# If case studies/research show one metric is more important, we can adjust the weights later

data_directory =  Path('data')
socioeconomic_sev = data_directory / 'socioeconomic_sev.csv'
healthcare_sev = data_directory / 'healthcare_resilience.csv'
food_access_score = data_directory / 'food_access_score.csv'
OUTPUT_CSV = data_directory / 'community_resilience_index.csv'

# Load & rename FIPS columns
socio_df = pd.read_csv(socioeconomic_sev, dtype=str)
# Rename uppercase 'State' → 'state'
socio_df = socio_df.rename(columns={'State': 'state'})
food_df  = pd.read_csv(food_access_score, dtype=str)
# Rename uppercase 'State' → 'state'
food_df  = food_df.rename(columns={'State': 'state'})
health_df= pd.read_csv(healthcare_sev, dtype=str)
# Rename StateFIPS/CountyFIPS → state/county
health_df = health_df.rename(columns={
    'StateFIPS': 'state',
    'CountyFIPS': 'county'
})

# Zero-pad FIPS strings
for dataframe in (socio_df, food_df, health_df):
    dataframe['state']  = dataframe['state'].str.zfill(2)
    dataframe['county'] = dataframe['county'].str.zfill(3)

# Merge three components on (state, county)
merged_file = (
    socio_df
    .merge(food_df[['state','county','Resilience_Food']], on=['state','county'], how='left')
    .merge(health_df[['state','county','Resilience_Health']], on=['state','county'], how='left')
)

# Convert all resilience columns to numeric
for col in ['Resilience_Socio','Resilience_Food','Resilience_Health']:
    merged_file[col] = pd.to_numeric(merged_file[col], errors='coerce')

# Computes the CRI with equal weights
w1 = w2 = w3 = 1/3
merged_file['CRI'] = (
    w1 * merged_file['Resilience_Socio'] +
    w2 * merged_file['Resilience_Food'] +
    w3 * merged_file['Resilience_Health']
)

merged_file['state_name']  = 'Georgia'

# Only keeps the relevant variables for the CRI
output = merged_file[[
    'state',        
    'state_name',    
    'county',        
    'County Name',   
    'Resilience_Socio',
    'Resilience_Food',
    'Resilience_Health',
    'CRI'
]]

# Renames the columns to be more descriptive
output.columns = [
    'StateFIPS',
    'State Name',
    'CountyFIPS',
    'County Name',
    'Socioeconomic Resilience',
    'Food Resilience',
    'Healthcare Resilience',
    'Community Resilience Index (CRI)'
]

# 8) Save that
os.makedirs(data_directory, exist_ok=True)
output.to_csv(OUTPUT_CSV, index=False)
print(f"Saved final CRI to {OUTPUT_CSV}")

import os
import pandas as pd

# --------------------
# socioeconomic_score.py
# --------------------
# Purpose:
#   Calculate the Socioeconomic Vulnerability Score (SEV) and its resilience component
#   from an enriched Census dataset (socioeconomic_full.csv).
#   The script applies min-max normalization to three indicators:
#     - poverty_rate
#     - education_no_hs_rate
#     - housing_cost_burden
#   and then computes SEV and Resilience_Socio = 1 - SEV.
#
# Input:
#   data/socioeconomic_full.csv
# Output:
#   data/socioeconomic_sev.csv

# 1) Load enriched socioeconomic data
input_path = 'data/socioeconomic_full.csv'
if not os.path.exists(input_path):
    raise FileNotFoundError(f"Missing input file: {input_path}")

df = pd.read_csv(input_path)

# 2) Normalize indicators via min-max to [0,1]
metrics = ['Poverty Rate', 'No_HS_Education', 'Housing_Cost_Burden']
for metric in metrics:
    minimum = df[metric].min()
    maximum = df[metric].max()
    # Avoid division by zero if all values are equal
    if maximum > minimum:
        df[f'norm_{metric}'] = (df[metric] - minimum) / (maximum - minimum)
    else:
        df[f'norm_{metric}'] = 0.0

# 3) Compute Socioeconomic Vulnerability Score (SEV) as the average of normalized metrics
df['SEV'] = df[[f'norm_{metric}' for metric in metrics]].mean(axis=1)

# 4) 1 - SEV = Resiliency Score
df['Resilience_Socio'] = 1 - df['SEV']

# 5) Save the results
os.makedirs('data', exist_ok=True)
output_path = 'data/socioeconomic_sev.csv'
df.to_csv(output_path, index=False)
print(f"Saved socioeconomic SEV data to {output_path}")

import os
import pandas as pd

# --------------------
# healthcare_score.py
# --------------------
#Purpose:
#    - Load county-level uninsured counts under 65 (healthcare_uninsured_counts.csv)
#    - Compute the uninsured rate = Uninsured population / Total population under 65
#    - Normalize uninsured_rate into [0,1] via min-max method into NormInsured
#    - Derive Resilience_Health = 1 - Normalized_Uninsured
#    - Output augmented CSV with new columns: uninsured_rate, NormUninsured, Resilience_Health
#Inputs:
#    - data/healthcare_uninsured_counts.csv
#Outputs:
#    - data/healthcare_resilience.csv

# 1) Paths
INPUT_CSV  = 'data/healthcare_uninsured_counts.csv'
OUTPUT_CSV = 'data/healthcare_resilience.csv'

# 2) Load data
df = pd.read_csv(INPUT_CSV)

# 3) Compute uninsured rate
df['uninsured_rate'] = df['Uninsured Population Under 65'] / df['Total Population Under 65']

# 4) Normalize uninsured_rate via min-max
minimum_val = df['uninsured_rate'].min()
maximum_val = df['uninsured_rate'].max()
if maximum_val > minimum_val:
    df['Normalized_Uninsured'] = (df['uninsured_rate'] - minimum_val) / (maximum_val - minimum_val)
else:
    df['Normalized_Uninsured'] = df['uninsured_rate']

# 5) Derive resilience
df['Resilience_Health'] = 1 - df['Normalized_Uninsured']

# 6) Save results
os.makedirs('data', exist_ok=True)
df.to_csv(OUTPUT_CSV, index=False)
print(f"✅ Saved healthcare resilience data to {OUTPUT_CSV}")

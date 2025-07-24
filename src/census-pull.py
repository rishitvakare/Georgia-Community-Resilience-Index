import os
import requests
import pandas as pd

# --------------------
# census_pull.py (week 5-6 version)
# --------------------
# Fetches 2021 ACS 5-Year data for Georgia counties:
# --> poverty & population (B17001)
# --> education levels (B15003)
# --> housing cost burden (B25070)
# Computes the SEV by taking the mean of all three metrics
# Resiliency Score = 1 - SEV
# Writes all of the data to data/socioeconomic_full.csv


# 1) Load API key
API_KEY = os.getenv('CENSUS_API_KEY')
if not API_KEY:
    raise RuntimeError("Please enter your CENSUS_API_KEY environment variable")

# 2) Define endpoint & variables
BASE_URL = 'https://api.census.gov/data/2021/acs/acs5'
# Poverty: B17001_002E = poverty estimate, B17001_001E = total population
# Education: B15003_001E = total pop 25+, B15003_002E..B15003_015E = pop without HS diploma
# Housing cost burden: B25070_010E = households paying >30% income, B25070_001E = total units
edu_fields = [f'B15003_{i:03d}E' for i in range(2, 16)]  # 002E to 015E
VARS = [
    'NAME',
    'B17001_002E', 'B17001_001E',
    'B15003_001E', *edu_fields,
    'B25070_010E', 'B25070_001E'
]
params = {
    'get': ','.join(VARS),
    'for': 'county:*',
    'in': 'state:13',  # Georgia
    'key': API_KEY
}

# 3) Request data
response = requests.get(BASE_URL, params=params)
response.raise_for_status()
records = response.json()

# 4) Build DataFrame
columns = records[0]
rows = records[1:]
data_frame = pd.DataFrame(rows, columns=columns)

# 5) Convert relevant columns to numeric
num_cols = ['B17001_002E','B17001_001E','B15003_001E','B25070_010E','B25070_001E'] + edu_fields
for col in num_cols:
    data_frame[col] = pd.to_numeric(data_frame[col], errors='coerce')

# 6) Compute derived metrics
data_frame['poverty_rate'] = data_frame['B17001_002E'] / data_frame['B17001_001E']
data_frame['education_no_hs_rate'] = data_frame[edu_fields].sum(axis=1) / data_frame['B15003_001E']
data_frame['housing_cost_burden'] = data_frame['B25070_010E'] / data_frame['B25070_001E']

# 7) Select & rename columns
output = data_frame[['NAME','state','county','poverty_rate','education_no_hs_rate','housing_cost_burden']].copy()
output = output.rename(columns={
    'NAME': 'County Name',
    'state': 'State',
    'poverty_rate': 'Poverty Rate',
    'education_no_hs_rate': 'No_HS_Education', 
    'housing_cost_burden': "Housing_Cost_Burden"

})

# 8) Save to CSV
os.makedirs('data', exist_ok=True)
out_path = 'data/socioeconomic_full.csv'
output.to_csv(out_path, index=False)
print(f"Saved enriched socioeconomic data to {out_path}")


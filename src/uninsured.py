# healthcare_access_raw_loader.py

import os
import requests
import pandas as pd

# --------------------
# Purpose:
#   Query the Census ACS API to fetch the **raw uninsured count**
#   among residents under 65 for every county in Georgia.
#   Doing the population under 65 because after 65, Medicare is available
#

# 1) Load your Census API key from the environment
API_KEY = os.getenv('CENSUS_API_KEY')
if not API_KEY:
    raise RuntimeError("Please set the CENSUS_API_KEY environment variable.")

# 2) Define the ACS endpoint and variables
BASE_URL = 'https://api.census.gov/data/2021/acs/acs5'
VARS = {
    'total_under65': 'B27010_001E',
    'uninsured_under65': 'B27010_017E'
}
params = {
    'get': f"{VARS['total_under65']},{VARS['uninsured_under65']},NAME",
    'for': 'county:*',
    'in': 'state:13',   # 13 = Georgia
    'key': API_KEY
}

# 3) Send request
resp = requests.get(BASE_URL, params=params)
resp.raise_for_status()
data = resp.json()

# 4) Parse into DataFrame
columns = data[0]
rows = data[1:]
df = pd.DataFrame(rows, columns=columns)

# 5) Convert to numeric
df['total_under65'] = df[VARS['total_under65']].astype(int)
df['uninsured_count'] = df[VARS['uninsured_under65']].astype(int)
df['county_name'] = df['NAME']
df['state'] = df['state']
df['county'] = df['county']

# 6) Select & reorder columns
out = df[['state', 'county', 'county_name', 'uninsured_count', 'total_under65']]

# 7) Save to CSV
os.makedirs('data', exist_ok=True)
output_path = 'data/healthcare_uninsured_counts.csv'

out = out.rename(columns={
    'state': 'StateFIPS',
    'county': 'CountyFIPS',
    'county_name': 'County Name',
    'uninsured_count': 'Uninsured Population Under 65',
    'total_under65': 'Total Population Under 65'
})


out.to_csv(output_path, index=False)
print(f"Saved to {output_path}")

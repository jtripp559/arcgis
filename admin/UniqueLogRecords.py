import pandas as pd
import os
import glob
# from pprint import pprint
# Define the directory path containing the CSV files
directory_path = r'C:\MS\OneDrive - Example Organization, Inc\SharePoint - ORG - GIS and IT\Programming\Monitoring\ORG ArcGIS Server Logs'
# Find all CSV files in the directory
csv_files = glob.glob(os.path.join(directory_path, '*.csv'))
# Initialize an empty DataFrame to hold all data
all_data = pd.DataFrame()
# Read each CSV file and concatenate into a single DataFrame
for file in csv_files:
    df = pd.read_csv(file)
    all_data = pd.concat([all_data, df], ignore_index=True)
# Extract unique combinations of message and code
unique_combinations = all_data[['message', 'code']].drop_duplicates()
# Count occurrences of each unique combination
combination_counts = all_data.groupby(['message', 'code']).size().reset_index(name='count')
# sort the combinations by count descending
combination_counts = combination_counts.sort_values(by='count', ascending=False)
# exclude the combinations with count less than 2
combination_counts = combination_counts[combination_counts['count'] > 1]
# Display the unique combinations and their counts
# pprint(combination_counts)
for index, row in combination_counts.iterrows():
    print(row['count'], row['code'], row['message'])
    print('-----------------------------------')
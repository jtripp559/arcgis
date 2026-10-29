import os
import xmltodict
import json
from datetime import datetime
from tqdm import tqdm
import pandas as pd
from pprint import pprint

# Directory to search for manifest.xml files
# base_dir = r"C:\MS\OneDrive - RRG Nature Based Solutions, Inc\SharePoint - NBS - GIS and IT\GIS\GIS Projects\Migrate ArcGIS\data\arcgisinput"
base_dir = r"\\192.168.4.243\c$\arcgisserver\directories\arcgissystem\arcgisinput"
if not os.path.exists(base_dir):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, 'Input')
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

# output_filename_base = 'ArcGIS_Manifest_Test'
output_filename_base = 'ArcGIS_Manifest_RRG'


timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
current_dir = os.getcwd()
output_dir = current_dir
output_dir = os.path.join(current_dir, 'Output')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

svc_manifest_keys = ['ID', 'Name', 'OnPremisePath', 'ByReference']
SVCResource_keys = ['ID', 'Name', 'OnPremisePath', 'ServerPath']
SVCDataset_keys = ['ID', 'Name', 'OnPremisePath', 'OnServerName', 'DatasetType']

def list_all_directories(root_dir):
    directories = []
    for dirpath, dirnames, _ in os.walk(root_dir):
        for dirname in dirnames:
            directories.append(os.path.join(dirpath, dirname))
    return directories

# Function to process a single manifest.xml file
def process_manifest(manifest_path):
    # To store the results
    flat_results = []
    results = {
        'svc_manifest': {},
        'resources': []
    }
    
    try:
        with open(manifest_path, 'r') as xml_file:
            xml_content = xmltodict.parse(xml_file.read())
        
        svc_manifest = xml_content.get('SVCManifest')

        # If SVCManifest exists, process it
        if svc_manifest:
            # print("Found SVCManifest")
            # Extract the attributes directly under "SVCManifest"
            results['svc_manifest'] = {key: svc_manifest.get(key) for key in svc_manifest_keys}
            svc_manifest_flat = {f'svc_manifest.{key}': results['svc_manifest'].get(key) for key in svc_manifest_keys}
        
        # add the manifest path to the flat results
        manifest_filename = os.path.basename(manifest_path)
        manifest_dir = os.path.dirname(manifest_path)
        manifest_dir_parts = manifest_dir.split(os.sep)
        svc_manifest_flat['manifest_path'] = manifest_path
        svc_manifest_flat['manifest_filename'] = manifest_filename
        svc_manifest_flat['manifest_dir'] = manifest_dir
        
        record_dir = False
        dir_cnt = 0
        for i, dir_part in enumerate(manifest_dir_parts):
            if record_dir:
                if dir_part == 'extracted':
                    record_dir = False
                    break
                # add the directory parts to the flat results as separate columns
                dir_cnt += 1
                svc_manifest_flat[f'manifest_dir_part_{dir_cnt}'] = dir_part
            else:
                if dir_part == 'arcgisinput':
                    record_dir = True

        # Process Resources
        resources = svc_manifest.get('Resources', {}).get('SVCResource', [])
        if isinstance(resources, dict):  # If there's only one resource, make it a list
            resources = [resources]

        for svc_resource in resources:
            resource_data = {key: svc_resource.get(key) for key in SVCResource_keys}
            resource_data['Datasets'] = []
            resource_data_flat = {f'resource.{key}': resource_data.get(key) for key in SVCResource_keys}

            # Process DatasetIDs
            dataset_ids = svc_resource.get('DatasetIDs', {}).get('String', [])
            if isinstance(dataset_ids, str):  # If there's only one dataset ID, make it a list
                dataset_ids = [dataset_ids]

            # Process Databases -> SVCDataset
            databases = svc_manifest.get('Databases', {}).get('SVCDatabase', [])
            if isinstance(databases, dict):  # If there's only one database, make it a list
                databases = [databases]

            for database in databases:
                datasets = database.get('Datasets', {}).get('SVCDataset', [])
                if isinstance(datasets, dict):  # If there's only one dataset, make it a list
                    datasets = [datasets]

                for dataset in datasets:
                    dataset_data = {key: dataset.get(key) for key in SVCDataset_keys}
                    dataset_data_flat = {f'dataset.{key}': dataset.get(key) for key in SVCDataset_keys}
                                        
                    resource_data['Datasets'].append(dataset_data)
                    
                    combined_data_flat = {**svc_manifest_flat, **resource_data_flat, **dataset_data_flat}
                    flat_results.append(combined_data_flat)
                
                if (not datasets) or (len(datasets) == 0):
                    combined_data_flat = {**svc_manifest_flat, **resource_data_flat}
                    flat_results.append(combined_data_flat)
            
            if (not databases) or (len(databases) == 0):
                combined_data_flat = {**svc_manifest_flat, **resource_data_flat}
                flat_results.append(combined_data_flat)

            results['resources'].append(resource_data)

    except Exception as e:
        print(f"Error processing manifest {manifest_path}: {e}")
    return (results, flat_results)

# Function to traverse directories and find manifest.xml files
def find_manifests_and_extract(base_dir):
    manifest_data = []
    manifest_data_flat = []
    
    # Get list of all files
    print("Finding all manifest.xml files...")
    all_files = [os.path.join(root, file) for root, _, files in os.walk(base_dir) for file in files if file == 'manifest.xml']
    
    print(f"Processing {len(all_files)} manifest files")
    for manifest_path in tqdm(all_files, desc="Processing manifests"):
        (data, data_flat) = process_manifest(manifest_path)
        if data:
            manifest_dir = os.path.dirname(manifest_path)
            manifest_data.append({
                'manifest_path': manifest_path,
                'manifest_filename': os.path.basename(manifest_path),
                'manifest_dir': manifest_dir,
                'manifest_dir_parts': manifest_dir.split(os.sep),
                'svc_manifest': data['svc_manifest'],
                'resources': data['resources']
            })
        if data_flat:
            manifest_data_flat.extend(data_flat)
    
    return (manifest_data, manifest_data_flat)

def write_results_to_file(results, results_flat):
    print("Writing results to file...")
    # pprint(results_flat)
    output_file_name = f"{output_filename_base}_{timestamp}"
    output_file_path = os.path.join(output_dir, output_file_name)
    if isinstance(results, list) or isinstance(results, dict):
        with open(f"{output_file_path}.json", 'w') as f:
            json.dump(results, f, indent=4)
        ''' 
        # Flattening the dictionary
        results_df = pd.json_normalize(results, sep='.')
        # Writing the dataframe to a CSV file
        results_df.to_csv(f"{output_file_path}.csv", index=False)
        '''
    else:
        if not isinstance(results, str):
            results = str(results)
        with open(f"{output_file_path}.txt", 'w') as f:
            f.write(results)
    
    # Write the flat results to a CSV file
    if results_flat != []:
        results_df = pd.DataFrame(results_flat)
        results_df.to_csv(f"{output_file_path}.csv", index=False)
        
    print(f"Results written to: {output_file_path}")

# Run the search and extraction process
if __name__ == "__main__":
    print("Starting...")
    
    (results, results_flat) = find_manifests_and_extract(base_dir)
    
    write_results_to_file(results, results_flat)
    
    print("Completed!")

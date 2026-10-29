"""
Script to combine Portal and AGOL JSON files based on sourceUrl/url relationships
and generate a flattened CSV output.

Author: AI Assistant
Date: September 8, 2025
"""

import json
import pandas as pd
import os
from datetime import datetime

def convert_timestamp(timestamp_ms, field_name, item_id):
    """
    Convert timestamp from milliseconds to human-readable format
    Similar to the timestamp conversion in GetAllArcGISServiceMetadata.py
    """
    try:
        if timestamp_ms is not None and isinstance(timestamp_ms, (int, float)):
            if timestamp_ms < 0:
                return None
            # Validate timestamp is within reasonable range
            timestamp_seconds = timestamp_ms / 1000
            if 0 <= timestamp_seconds <= 32503680000:  # Unix timestamp for year 3000
                return datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
            else:
                return None
        else:
            return None
    except Exception as e:
        print(f"Failed to convert {field_name} timestamp of {timestamp_ms} for {item_id}: {e}")
        return None

def load_json_file(filepath):
    """Load JSON file and return the data"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} items from {os.path.basename(filepath)}")
        return data
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []

def create_url_index(portal_data):
    """Create an index of Portal items by their URL for fast lookup"""
    url_index = {}
    for item in portal_data:
        url = item.get('url')
        if url:
            url_index[url] = item
    print(f"Created URL index with {len(url_index)} entries")
    return url_index

def flatten_dict(d, parent_key='', sep='_'):
    """
    Flatten a nested dictionary, converting lists to comma-separated strings
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert list to comma-separated string
            if v:  # Only if list is not empty
                # Handle nested objects in lists
                if isinstance(v[0], dict):
                    # For list of dicts, convert each dict to string representation
                    list_str = '; '.join([str(item) for item in v])
                else:
                    # For simple lists, join with commas
                    list_str = ', '.join([str(item) for item in v])
                items.append((new_key, list_str))
            else:
                items.append((new_key, ''))
        else:
            items.append((new_key, v))
    return dict(items)

def process_timestamps_in_item(item, item_source):
    """
    Process timestamp fields in an item, converting them to human-readable format
    """
    if not item:
        return item
    
    # Create a copy to avoid modifying original data
    processed_item = item.copy()
    item_id = item.get('id', 'unknown')
    
    # Common timestamp fields to convert
    timestamp_fields = ['created', 'modified', 'lastViewed', 'lastmodified']
    
    for field in timestamp_fields:
        if field in processed_item:
            original_timestamp = processed_item[field]
            if original_timestamp:
                converted_timestamp = convert_timestamp(original_timestamp, field, f"{item_source}_{item_id}")
                processed_item[f'{field}_readable'] = converted_timestamp
    
    return processed_item

def combine_data(portal_data, agol_data):
    """
    Combine Portal and AGOL data based on sourceUrl/url relationships
    """
    # remove all records where owner begins with "esri_"
    portal_data = [item for item in portal_data if not item.get('owner', '').startswith('esri_')]
    agol_data = [item for item in agol_data if not item.get('owner', '').startswith('esri_')]
    
    excluded_types = ['Administrative Report', 'API Key', 'Application', 'Code Attachment', 'Data Store', 'Geometry Service',
                      'Mobile Application', 'OGCFeatureServer', 'Service Definition', 'Symbol Service', 'WMS']
    portal_data = [item for item in portal_data if item.get('type') not in excluded_types]
    agol_data = [item for item in agol_data if item.get('type') not in excluded_types]
    
    print("Creating URL index for Portal data...")
    portal_url_index = create_url_index(portal_data)
    
    combined_records = []
    matched_portal_ids = set()
    matched_urls = {}  # Dictionary: url -> agol_id
    
    print("Processing AGOL items and matching with Portal...")
    # Process AGOL items first
    for agol_item in agol_data:
        # Process timestamps in AGOL item
        processed_agol_item = process_timestamps_in_item(agol_item, 'AGOL')
        
        source_url = agol_item.get('sourceUrl')
        combined_record = {
            'ArcGIS_Location': 'AGOL_only',
            'related_agol_id': agol_item.get('id'),
            'agol_id': agol_item.get('id'),
            'portal_id': None,
            'source_url': source_url,
            'AGOL': processed_agol_item,
            'Portal': None
        }
        
        if source_url and source_url in portal_url_index:
            # Found a match
            portal_item = portal_url_index[source_url]
            # Process timestamps in Portal item
            processed_portal_item = process_timestamps_in_item(portal_item, 'Portal')
            
            combined_record['ArcGIS_Location'] = 'AGOL_and_Portal'
            combined_record['portal_id'] = portal_item.get('id')
            combined_record['Portal'] = processed_portal_item
            matched_portal_ids.add(portal_item.get('id'))
            matched_urls[source_url] = agol_item.get('id')
        
        combined_records.append(combined_record)
    
    print("Adding unmatched Portal items...")
    # Add unmatched Portal items
    for portal_item in portal_data:
        portal_id = portal_item.get('id')
        if portal_id not in matched_portal_ids:
            # Process timestamps in unmatched Portal item
            processed_portal_item = process_timestamps_in_item(portal_item, 'Portal')
            
            arc_location = 'Portal_Only'
            related_agol_id = None
            
            if portal_item.get('type') == 'Map Service':
                # replace '/MapServer' with '/FeatureServer' in the URL if applicable
                url = portal_item.get('url', '')
                if url.endswith('/MapServer'):
                    url = url.replace('/MapServer', '/FeatureServer')
                if url in matched_urls:
                    arc_location = 'AGOL_and_Portal_by_FeatureServer'
                    related_agol_id = matched_urls[url]

            combined_record = {
                'ArcGIS_Location': arc_location,
                'related_agol_id': related_agol_id,
                'agol_id': None,
                'portal_id': portal_id,
                'source_url': portal_item.get('url'),
                'AGOL': None,
                'Portal': processed_portal_item
            }
            combined_records.append(combined_record)
    
    # sort by related_agol_id, agol_id, portal_id
    combined_records.sort(key=lambda x: (x['related_agol_id'] or '', x['agol_id'] or '', x['portal_id'] or ''))
    
    print(f"Combined data created with {len(combined_records)} total records")
    return combined_records

def create_flattened_csv(combined_data, output_path):
    """
    Create a flattened CSV from the combined data
    """
    print("Flattening data for CSV export...")
    flattened_records = []
    
    for record in combined_data:
        flat_record = {
            'ArcGIS_Location': record['ArcGIS_Location'],
            'related_agol_id': record['related_agol_id'],
            'agol_id': record['agol_id'],
            'portal_id': record['portal_id'],
            'source_url': record['source_url']
        }
        
        # Flatten AGOL data
        if record['AGOL']:
            agol_flat = flatten_dict(record['AGOL'], parent_key='AGOL')
            flat_record.update(agol_flat)
        
        # Flatten Portal data
        if record['Portal']:
            portal_flat = flatten_dict(record['Portal'], parent_key='Portal')
            flat_record.update(portal_flat)
        
        flattened_records.append(flat_record)
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(flattened_records)
    
    # change order of columns to have ArcGIS_Location, related_agol_id, agol_id, portal_id, source_url first
    # followed by columns ending in the following ['title', 'type', 'owner', 'contentStatus', 'tags', 'categories', 'readable', 'protected', 'numViews']
    cols = df.columns.tolist()
    cols_of_interest = ['ArcGIS_Location', 'related_agol_id', 'agol_id', 'portal_id', 'source_url']
    cols_of_interest_endings = ['title', 'type', 'owner', 'contentStatus', 'tags', 'categories', 'readable', 'protected', 'numViews']
    # add to cols_of_interest any columns that end with the specified endings
    for ending in cols_of_interest_endings:
        cols_of_interest.extend([col for col in cols if col.endswith(ending) and col not in cols_of_interest])
    cols = cols_of_interest + [col for col in cols if col not in cols_of_interest]
    df = df[cols]

    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"Flattened CSV saved to: {output_path}")
    print(f"CSV contains {len(df)} rows and {len(df.columns)} columns")
    
    return df

def main():
    # File paths
    base_path = r"c:\Develop\GIS\gis_general\Scripts\ArcGIS Admin\Output"
    portal_file = os.path.join(base_path, "NBS", "ArcGIS_Items_NBS_20250905171728_gis_items.json")
    agol_file = os.path.join(base_path, "AGOL", "ArcGIS_Items_AGOL_20250908101638_gis_items.json")
    
    # Output paths
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    combined_json_path = os.path.join(base_path, f"Combined_ArcGIS_Items_{timestamp}.json")
    flattened_csv_path = os.path.join(base_path, f"Combined_ArcGIS_Items_{timestamp}.csv")
    
    print("=== ArcGIS JSON File Combiner ===")
    print(f"Portal file: {portal_file}")
    print(f"AGOL file: {agol_file}")
    print()
    
    # Load data
    print("Loading JSON files...")
    portal_data = load_json_file(portal_file)
    agol_data = load_json_file(agol_file)
    
    if not portal_data and not agol_data:
        print("Error: No data loaded from either file")
        return
    
    # Combine data
    print("\nCombining data...")
    combined_data = combine_data(portal_data, agol_data)
    
    # Save combined JSON
    print(f"\nSaving combined JSON to: {combined_json_path}")
    with open(combined_json_path, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)
    
    # Create flattened CSV
    print("\nCreating flattened CSV...")
    df = create_flattened_csv(combined_data, flattened_csv_path)
    
    # Print summary statistics
    print("\n=== Summary Statistics ===")
    match_counts = df['ArcGIS_Location'].value_counts()
    print("Match types:")
    for ArcGIS_Location, count in match_counts.items():
        print(f"  {ArcGIS_Location}: {count}")
    
    print(f"\nTotal records: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    
    # Show sample of columns
    print(f"\nSample columns (first 10):")
    for i, col in enumerate(df.columns[:10]):
        print(f"  {i+1}. {col}")
    if len(df.columns) > 10:
        print(f"  ... and {len(df.columns) - 10} more columns")
    
    print("\n=== Process Complete ===")
    print(f"Combined JSON: {combined_json_path}")
    print(f"Flattened CSV: {flattened_csv_path}")

if __name__ == "__main__":
    main()

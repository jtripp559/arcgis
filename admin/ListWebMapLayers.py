# ListWebMapLayers.py
#
# Developer: Julie Tripp
# Date: 09/12/2025
#
# Description: This script connects to ArcGIS Online/Enterprise and lists all layers
#              from a specified web map, including their properties and metadata.

import os
import json
import logging
from datetime import datetime
from arcgis.gis import GIS
from arcgis.mapping import WebMap
import pandas as pd

# Configuration
PORTAL_URL = 'https://gis.example.com/arcgisportal'  # Change to your portal URL
MAX_ITEMS = 10000  # Maximum number of web maps to process

# Global variables
gis = None
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
has_logging = False

def init_logging():
    """Initialize logging similar to workspace patterns"""
    global has_logging
    current_dir = os.getcwd()
    output_dir = os.path.join(current_dir, 'Output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    log_file = os.path.join(output_dir, f'WebMapLayers_{timestamp}.log')
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    has_logging = True
    return output_dir

def log_message(message, log_level='info'):
    """Log message similar to workspace pattern"""
    if log_level.lower() == 'error':
        logging.error(message)
        print(f"ERROR: {message}")
    elif log_level.lower() == 'warning':
        logging.warning(message)
        print(f"WARNING: {message}")
    else:
        logging.info(message)
        print(f"INFO: {message}")

def connect_to_arcgis():
    """Connect to ArcGIS using patterns from workspace"""
    global gis
    try:
        log_message("Connecting to ArcGIS using Windows credentials")
        # Using Windows authentication - similar to patterns in workspace
        gis = GIS(PORTAL_URL)
        
        user_info = gis.properties.user
        log_message(f"Successfully connected as: {user_info.username}")
        return True
        
    except Exception as e:
        log_message(f"Failed to connect to ArcGIS: {e}", 'error')
        return False

def find_all_web_maps():
    """Find all web maps in the portal"""
    try:
        log_message("Searching for all web maps in the portal...")
        search_results = gis.content.search(query="", item_type="Web Map", max_items=MAX_ITEMS)
        
        if not search_results:
            log_message("No web maps found in the portal", 'warning')
            return []
        
        log_message(f"Found {len(search_results)} web maps")
        return search_results
        
    except Exception as e:
        log_message(f"Failed to find web maps: {e}", 'error')
        return []

def extract_layer_info(layer_data, layer_type="operational"):
    """Extract layer information from layer data"""
    layer_info = {
        'layer_type': layer_type,
        'id': layer_data.get('id', ''),
        'title': layer_data.get('title', ''),
        'url': layer_data.get('url', ''),
        'layer_type_detail': layer_data.get('layerType', ''),
        'visibility': layer_data.get('visibility', True),
        'opacity': layer_data.get('opacity', 1.0),
        'item_id': '',
        'service_type': '',
        'layer_definition': '',
        'popup_info': '',
        'drawing_info': ''
    }
    
    # Extract item ID if available
    if 'itemId' in layer_data:
        layer_info['item_id'] = layer_data['itemId']
    
    # Determine service type from URL
    if layer_info['url']:
        if 'FeatureServer' in layer_info['url']:
            layer_info['service_type'] = 'Feature Service'
        elif 'MapServer' in layer_info['url']:
            layer_info['service_type'] = 'Map Service'
        elif 'ImageServer' in layer_info['url']:
            layer_info['service_type'] = 'Image Service'
        elif 'VectorTileServer' in layer_info['url']:
            layer_info['service_type'] = 'Vector Tile Service'
        else:
            layer_info['service_type'] = 'Other'
    
    # Extract layer definition info
    if 'layerDefinition' in layer_data:
        layer_def = layer_data['layerDefinition']
        layer_info['layer_definition'] = json.dumps(layer_def) if layer_def else ''
    
    # Extract popup info  
    if 'popupInfo' in layer_data:
        popup_info = layer_data['popupInfo']
        layer_info['popup_info'] = json.dumps(popup_info) if popup_info else ''
    
    # Extract drawing info
    if 'drawingInfo' in layer_data:
        drawing_info = layer_data['drawingInfo']
        layer_info['drawing_info'] = json.dumps(drawing_info) if drawing_info else ''
    
    return layer_info

def process_sublayers(layers_list, parent_info=""):
    """Recursively process sublayers"""
    all_layers = []
    
    for i, layer in enumerate(layers_list):
        layer_info = extract_layer_info(layer)
        layer_info['parent_layer'] = parent_info
        layer_info['layer_index'] = i
        
        all_layers.append(layer_info)
        
        # Check for sublayers
        if 'layers' in layer and layer['layers']:
            sublayer_parent = f"{parent_info}/{layer_info['title']}" if parent_info else layer_info['title']
            sublayers = process_sublayers(layer['layers'], sublayer_parent)
            all_layers.extend(sublayers)
    
    return all_layers

def process_single_web_map(web_map_item):
    """Process a single web map and extract all layer information"""
    try:
        log_message(f"Processing web map: {web_map_item.title} (ID: {web_map_item.id})")
        
        # Get web map data
        web_map = WebMap(web_map_item)
        web_map_data = web_map.definition
        
        all_layers = []
        
        # Process operational layers
        if 'operationalLayers' in web_map_data:
            operational_layers = process_sublayers(web_map_data['operationalLayers'])
            for layer in operational_layers:
                layer['layer_type'] = 'operational'
                layer['web_map_id'] = web_map_item.id
                layer['web_map_title'] = web_map_item.title
                layer['web_map_owner'] = web_map_item.owner
            all_layers.extend(operational_layers)
        
        # Process basemap layers
        if 'baseMap' in web_map_data and 'baseMapLayers' in web_map_data['baseMap']:
            basemap_layers = process_sublayers(web_map_data['baseMap']['baseMapLayers'])
            for layer in basemap_layers:
                layer['layer_type'] = 'basemap'
                layer['web_map_id'] = web_map_item.id
                layer['web_map_title'] = web_map_item.title
                layer['web_map_owner'] = web_map_item.owner
            all_layers.extend(basemap_layers)
        
        # Process reference layers (if any)
        if 'baseMap' in web_map_data and 'referenceLayers' in web_map_data['baseMap']:
            reference_layers = process_sublayers(web_map_data['baseMap']['referenceLayers'])
            for layer in reference_layers:
                layer['layer_type'] = 'reference'
                layer['web_map_id'] = web_map_item.id
                layer['web_map_title'] = web_map_item.title
                layer['web_map_owner'] = web_map_item.owner
            all_layers.extend(reference_layers)
        
        log_message(f"Found {len(all_layers)} layers in web map: {web_map_item.title}")
        return all_layers
        
    except Exception as e:
        log_message(f"Failed to process web map {web_map_item.title}: {e}", 'error')
        return []

def list_all_web_map_layers():
    """List all layers from all web maps in the portal"""
    try:
        # Find all web maps
        web_map_items = find_all_web_maps()
        if not web_map_items:
            return []
        
        all_layers_data = []
        processed_count = 0
        
        log_message(f"Processing {len(web_map_items)} web maps...")
        
        for web_map_item in web_map_items:
            try:
                layers = process_single_web_map(web_map_item)
                all_layers_data.extend(layers)
                processed_count += 1
                
                # Log progress every 10 web maps
                if processed_count % 10 == 0:
                    log_message(f"Processed {processed_count}/{len(web_map_items)} web maps")
                    
            except Exception as e:
                log_message(f"Failed to process web map {web_map_item.title}: {e}", 'error')
                continue
        
        log_message(f"Successfully processed {processed_count} web maps with {len(all_layers_data)} total layers")
        return all_layers_data
        
    except Exception as e:
        log_message(f"Failed to list all web map layers: {e}", 'error')
        return []

def export_layers_to_files(layers_data, output_dir):
    """Export layer data to JSON and CSV files"""
    try:
        # Export to JSON
        json_file = os.path.join(output_dir, f'AllWebMapLayers_{timestamp}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(layers_data, f, indent=2, ensure_ascii=False)
        log_message(f"Exported layer data to JSON: {json_file}")
        
        # Export to CSV
        csv_file = os.path.join(output_dir, f'AllWebMapLayers_{timestamp}.csv')
        df = pd.DataFrame(layers_data)
        df.to_csv(csv_file, index=False, encoding='utf-8')
        log_message(f"Exported layer data to CSV: {csv_file}")
        
        # Also create a web map summary
        web_map_summary = create_web_map_summary(layers_data)
        summary_file = os.path.join(output_dir, f'WebMapSummary_{timestamp}.csv')
        summary_df = pd.DataFrame(web_map_summary)
        summary_df.to_csv(summary_file, index=False, encoding='utf-8')
        log_message(f"Exported web map summary to CSV: {summary_file}")
        
        return json_file, csv_file, summary_file
        
    except Exception as e:
        log_message(f"Failed to export layer data: {e}", 'error')
        return None, None, None

def create_web_map_summary(layers_data):
    """Create a summary of web maps and their layer counts"""
    try:
        web_map_summary = {}
        
        for layer in layers_data:
            web_map_id = layer.get('web_map_id')
            web_map_title = layer.get('web_map_title')
            web_map_owner = layer.get('web_map_owner')
            layer_type = layer.get('layer_type')
            
            if web_map_id not in web_map_summary:
                web_map_summary[web_map_id] = {
                    'web_map_id': web_map_id,
                    'web_map_title': web_map_title,
                    'web_map_owner': web_map_owner,
                    'total_layers': 0,
                    'operational_layers': 0,
                    'basemap_layers': 0,
                    'reference_layers': 0
                }
            
            web_map_summary[web_map_id]['total_layers'] += 1
            if layer_type == 'operational':
                web_map_summary[web_map_id]['operational_layers'] += 1
            elif layer_type == 'basemap':
                web_map_summary[web_map_id]['basemap_layers'] += 1
            elif layer_type == 'reference':
                web_map_summary[web_map_id]['reference_layers'] += 1
        
        return list(web_map_summary.values())
        
    except Exception as e:
        log_message(f"Failed to create web map summary: {e}", 'error')
        return []

def print_layer_summary(layers_data):
    """Print a summary of the layers from all web maps"""
    if not layers_data:
        log_message("No layers found")
        return
    
    # Group by layer type and service type
    layer_types = {}
    service_types = {}
    web_map_counts = {}
    
    for layer in layers_data:
        layer_type = layer.get('layer_type', 'unknown')
        service_type = layer.get('service_type', 'unknown')
        web_map_id = layer.get('web_map_id', 'unknown')
        
        layer_types[layer_type] = layer_types.get(layer_type, 0) + 1
        service_types[service_type] = service_types.get(service_type, 0) + 1
        web_map_counts[web_map_id] = web_map_counts.get(web_map_id, 0) + 1
    
    log_message("\n=== Overall Layer Summary ===")
    log_message(f"Total layers across all web maps: {len(layers_data)}")
    log_message(f"Total web maps processed: {len(web_map_counts)}")
    
    log_message("\nBy layer type:")
    for layer_type, count in layer_types.items():
        log_message(f"  {layer_type}: {count}")
    
    log_message("\nBy service type:")
    for service_type, count in service_types.items():
        log_message(f"  {service_type}: {count}")
    
    log_message("\nTop 10 web maps by layer count:")
    sorted_web_maps = sorted(web_map_counts.items(), key=lambda x: x[1], reverse=True)
    for i, (web_map_id, count) in enumerate(sorted_web_maps[:10]):
        # Find the web map title for this ID
        web_map_title = "Unknown"
        for layer in layers_data:
            if layer.get('web_map_id') == web_map_id:
                web_map_title = layer.get('web_map_title', 'Unknown')
                break
        log_message(f"  {i+1}. {web_map_title[:50]}... ({count} layers)")

def main():
    """Main execution function"""
    try:
        # Initialize logging
        output_dir = init_logging()
        log_message("Starting All Web Map Layer Listing")
        
        # Connect to ArcGIS
        if not connect_to_arcgis():
            return False
        
        # List all web map layers
        layers_data = list_all_web_map_layers()
        if not layers_data:
            log_message("No layers found to process", 'warning')
            return False
        
        # Print summary
        print_layer_summary(layers_data)
        
        # Export to files
        json_file, csv_file, summary_file = export_layers_to_files(layers_data, output_dir)
        
        log_message("Successfully completed all web map layer listing")
        log_message(f"Files created:")
        log_message(f"  Layer details (JSON): {json_file}")
        log_message(f"  Layer details (CSV): {csv_file}")
        log_message(f"  Web map summary (CSV): {summary_file}")
        
        return True
        
    except Exception as e:
        log_message(f"Script failed with error: {e}", 'error')
        import traceback
        log_message(traceback.format_exc(), 'error')
        return False

if __name__ == '__main__':
    # No need for user input since we're processing all web maps
    print("This script will process ALL web maps in the portal.")
    confirm = input("Do you want to continue? (y/N): ").strip().lower()
    
    if confirm in ['y', 'yes']:
        success = main()
        if success:
            print("Script completed successfully")
        else:
            print("Script failed - check log file for details")
            exit(1)
    else:
        print("Script cancelled by user")
        exit(0)
# ListWebAppBuilderLayers.py
#
# Developer: Julie Tripp
def get_user_input(prompt, default_value='', value_to_check=''):
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    
    try:
        user_input = input(f"{input_prompt}: ")
        user_input = user_input.strip()
        if user_input == '' or user_input is None:
            user_input = default_value
    except EOFError:
        # Handle EOF error by using default value
        print(f"No input detected, using default value: {default_value}")
        user_input = default_value
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
        exit(0)
    
    print(f"{prompt}: {user_input}")
    return user_input025

#
# Description: This script connects to ArcGIS Online/Enterprise and lists all layers
#              from Web Mapping Applications (Web AppBuilder apps) in your organization.

import os
import json
import logging
import datetime
from arcgis.gis import GIS
from arcgis.mapping import WebMap
import pandas as pd
import requests
import getpass
import traceback

# Configuration
MAX_ITEMS = 10000  # Maximum number of web apps to process
FILENAME_BASE = 'ArcGIS_WebAppBuilderLayers'

# Global variables
PORTAL_URL = ''
base_url = ''
selected_portal = None
gis = None
arcgis_username = None
arcgis_password = None

timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

def init_logging():
    """Initialize logging similar to workspace patterns"""
    current_dir = os.getcwd()
    output_dir = os.path.join(current_dir, 'Output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    log_file = os.path.join(output_dir, f'{FILENAME_BASE}_{timestamp}.log')
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return output_dir

def log_message(message, log_level='info'):
    """Log message similar to workspace pattern"""
    if log_level.lower() == 'error':
        logging.error(message)
    elif log_level.lower() == 'warning':
        logging.warning(message)
    else:
        logging.info(message)
    print(f"{log_level.upper()}: {message}")

def get_user_input(prompt, default_value='', value_to_check=''):
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    
    try:
        user_input = input(f"{input_prompt}: ")
        user_input = user_input.strip()
        if user_input == '' or user_input is None:
            user_input = default_value
    except EOFError:
        # Handle EOF error by using default value
        print(f"No input detected, using default value: {default_value}")
        user_input = default_value
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
        exit(0)
    
    log_message(f"{prompt}: {user_input}")
    return user_input


def connect_to_arcgis():
    global PORTAL_URL, base_url, selected_portal, FILENAME_BASE, gis, arcgis_username, arcgis_password
    connected = False

    # ArcGIS Online
    portal_url_agol = 'https://rrg.maps.arcgis.com'
    base_url_agol = 'https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services'
    # Old ArcGIS Enterprise
    portal_url_rrg = 'https://gis.renewablegroup.com/portal'
    base_url_rrg = 'https://gis.renewablegroup.com/server/rest/services'
    # New ArcGIS Enterprise
    portal_url_nbs = 'https://maps.rrgnbs.com/arcgisportal'
    base_url_nbs = 'https://maps.rrgnbs.com/arcgisserver/rest/services/'
    
    which_portal = get_user_input("Which ArcGIS portal (AGOL, RRG, NBS)", default_value='AGOL')
    which_portal = which_portal.upper()
    if which_portal.startswith('A'):
        PORTAL_URL = portal_url_agol
        base_url = base_url_agol
        selected_portal = 'AGOL'
    elif which_portal.startswith('R'):
        PORTAL_URL = portal_url_rrg
        base_url = base_url_rrg
        selected_portal = 'RRG'
    else:
        PORTAL_URL = portal_url_nbs
        base_url = base_url_nbs
        selected_portal = 'NBS'
    FILENAME_BASE = f'{FILENAME_BASE}_{selected_portal}'
    
    # Get arcgis_username and password from the user
    arcgis_username = get_user_input("ArcGIS Username (not SSO)", default_value='rrgadmin')
    arcgis_password = getpass.getpass(f"**  ArcGIS Password for {arcgis_username}: ")
    if arcgis_username == "" or arcgis_password == "":
        log_message("Missing username or password.", level='error')
    else:
        '''
        try:
            arcpy.SignInToPortal(PORTAL_URL, arcgis_username, arcgis_password)
            connected = True
            log_message(f"Connected to {PORTAL_URL} as {arcgis_username}")
        except Exception as e:
            log_message(f"Failed to connect to {PORTAL_URL} using arcpy: {e}", level='error')
        '''
        try:
            gis = GIS(PORTAL_URL, arcgis_username, arcgis_password, verify_cert=False)
            connected = True
            log_message(f"Connected to {PORTAL_URL} using GIS")
        except Exception as e:
            log_message(f"Failed to connect to {PORTAL_URL} using GIS: {e}", level='error')
            log_message(traceback.format_exc())
    return connected

def find_all_web_apps():
    """Find all Web Mapping Applications in the organization"""
    try:
        log_message("Searching for Web Mapping Applications in the organization...")
        
        # Search for Web Mapping Applications, excluding Esri content
        query = "NOT owner:esri* AND NOT owner:esri_*"
        search_results = gis.content.search(
            query=query, 
            item_type="Web Mapping Application", 
            max_items=MAX_ITEMS,
            outside_org=False  # Only search within organization
        )
        
        if not search_results:
            log_message("No Web Mapping Applications found in the organization", 'warning')
            return []
        
        # Filter out apps that are not Web AppBuilder (check typeKeywords)
        web_app_builder_apps = []
        for app in search_results:
            type_keywords = app.get('typeKeywords', [])
            # Web AppBuilder apps typically have these keywords
            if any(keyword in ['Web AppBuilder', 'WAB', 'JavaScript'] for keyword in type_keywords):
                web_app_builder_apps.append(app)
            elif 'Web AppBuilder' in str(app.get('tags', [])):
                web_app_builder_apps.append(app)
            else:
                # Check if URL contains Web AppBuilder indicators
                app_url = app.get('url', '')
                if 'webappbuilder' in app_url.lower() or '/apps/webappbuilder/' in app_url.lower():
                    web_app_builder_apps.append(app)
        
        log_message(f"Found {len(search_results)} total Web Mapping Applications")
        log_message(f"Identified {len(web_app_builder_apps)} as Web AppBuilder applications")
        return web_app_builder_apps
        
    except Exception as e:
        log_message(f"Failed to find Web Mapping Applications: {e}", 'error')
        return []

def get_web_app_config(app_item):
    """Get the configuration of a Web AppBuilder application"""
    try:
        # Try to get app data which may contain web map reference
        app_data = app_item.get_data()
        
        if app_data:
            return app_data
        else:
            log_message(f"No configuration data found for app: {app_item.title}", 'warning')
            return None
            
    except Exception as e:
        log_message(f"Failed to get config for app {app_item.title}: {e}", 'error')
        return None

def extract_web_map_id_from_config(app_config, app_item):
    """Extract web map ID from Web AppBuilder configuration"""
    try:
        web_map_id = None
        
        if isinstance(app_config, dict):
            # Common locations for web map ID in Web AppBuilder config
            if 'map' in app_config:
                if isinstance(app_config['map'], dict):
                    web_map_id = app_config['map'].get('itemId')
                elif isinstance(app_config['map'], str):
                    web_map_id = app_config['map']
            
            # Alternative locations
            if not web_map_id:
                web_map_id = app_config.get('webmap') or app_config.get('itemId')
            
            # Look in nested structures
            if not web_map_id and 'values' in app_config:
                values = app_config['values']
                if isinstance(values, dict):
                    web_map_id = values.get('webmap') or values.get('itemId')
        
        return web_map_id
        
    except Exception as e:
        log_message(f"Failed to extract web map ID from config for {app_item.title}: {e}", 'error')
        return None

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

def process_single_web_app(app_item):
    """Process a single Web AppBuilder application and extract all layer information"""
    try:
        log_message(f"Processing Web App: {app_item.title} (ID: {app_item.id})")
        
        # Get app configuration
        app_config = get_web_app_config(app_item)
        if not app_config:
            log_message(f"Could not get configuration for app: {app_item.title}", 'warning')
            return []
        
        # Extract web map ID from configuration
        web_map_id = extract_web_map_id_from_config(app_config, app_item)
        if not web_map_id:
            log_message(f"Could not find web map ID in app config for: {app_item.title}", 'warning')
            return []
        
        log_message(f"Found web map ID {web_map_id} for app: {app_item.title}")
        
        # Get the web map
        try:
            web_map_item = gis.content.get(web_map_id)
            if not web_map_item:
                log_message(f"Could not access web map {web_map_id} for app: {app_item.title}", 'warning')
                return []
        except Exception as e:
            log_message(f"Error accessing web map {web_map_id} for app {app_item.title}: {e}", 'error')
            return []
        
        # Get web map data
        web_map = WebMap(web_map_item)
        web_map_data = web_map.definition
        
        all_layers = []
        
        # Process operational layers
        if 'operationalLayers' in web_map_data:
            operational_layers = process_sublayers(web_map_data['operationalLayers'])
            for layer in operational_layers:
                layer['layer_type'] = 'operational'
                layer['web_app_id'] = app_item.id
                layer['web_app_title'] = app_item.title
                layer['web_app_owner'] = app_item.owner
                layer['web_app_url'] = app_item.get('url', '')
                layer['web_map_id'] = web_map_id
                layer['web_map_title'] = web_map_item.title
            all_layers.extend(operational_layers)
        
        # Process basemap layers
        if 'baseMap' in web_map_data and 'baseMapLayers' in web_map_data['baseMap']:
            basemap_layers = process_sublayers(web_map_data['baseMap']['baseMapLayers'])
            for layer in basemap_layers:
                layer['layer_type'] = 'basemap'
                layer['web_app_id'] = app_item.id
                layer['web_app_title'] = app_item.title
                layer['web_app_owner'] = app_item.owner
                layer['web_app_url'] = app_item.get('url', '')
                layer['web_map_id'] = web_map_id
                layer['web_map_title'] = web_map_item.title
            all_layers.extend(basemap_layers)
        
        # Process reference layers (if any)
        if 'baseMap' in web_map_data and 'referenceLayers' in web_map_data['baseMap']:
            reference_layers = process_sublayers(web_map_data['baseMap']['referenceLayers'])
            for layer in reference_layers:
                layer['layer_type'] = 'reference'
                layer['web_app_id'] = app_item.id
                layer['web_app_title'] = app_item.title
                layer['web_app_owner'] = app_item.owner
                layer['web_app_url'] = app_item.get('url', '')
                layer['web_map_id'] = web_map_id
                layer['web_map_title'] = web_map_item.title
            all_layers.extend(reference_layers)
        
        log_message(f"Found {len(all_layers)} layers in Web App: {app_item.title}")
        return all_layers
        
    except Exception as e:
        log_message(f"Failed to process Web App {app_item.title}: {e}", 'error')
        return []

def list_all_web_app_layers():
    """List all layers from all Web AppBuilder applications in the organization"""
    try:
        # Find all Web AppBuilder applications
        web_app_items = find_all_web_apps()
        if not web_app_items:
            return []
        
        all_layers_data = []
        processed_count = 0
        
        log_message(f"Processing {len(web_app_items)} Web AppBuilder applications...")
        
        for app_item in web_app_items:
            try:
                layers = process_single_web_app(app_item)
                all_layers_data.extend(layers)
                processed_count += 1
                
                # Log progress every 5 web apps
                if processed_count % 5 == 0:
                    log_message(f"Processed {processed_count}/{len(web_app_items)} Web Apps")
                    
            except Exception as e:
                log_message(f"Failed to process Web App {app_item.title}: {e}", 'error')
                continue
        
        log_message(f"Successfully processed {processed_count} Web Apps with {len(all_layers_data)} total layers")
        return all_layers_data
        
    except Exception as e:
        log_message(f"Failed to list all Web App layers: {e}", 'error')
        return []

def export_layers_to_files(layers_data, output_dir):
    """Export layer data to JSON and CSV files"""
    try:
        # Export to JSON
        json_file = os.path.join(output_dir, f'{FILENAME_BASE}_{timestamp}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(layers_data, f, indent=2, ensure_ascii=False)
        log_message(f"Exported layer data to JSON: {json_file}")
        
        # Export to CSV
        csv_file = os.path.join(output_dir, f'{FILENAME_BASE}_{timestamp}.csv')
        df = pd.DataFrame(layers_data)
        df.to_csv(csv_file, index=False, encoding='utf-8')
        log_message(f"Exported layer data to CSV: {csv_file}")
        
        # Create Web App summary
        web_app_summary = create_web_app_summary(layers_data)
        summary_file = os.path.join(output_dir, f'WebAppBuilderSummary_{timestamp}.csv')
        summary_df = pd.DataFrame(web_app_summary)
        summary_df.to_csv(summary_file, index=False, encoding='utf-8')
        log_message(f"Exported Web App summary to CSV: {summary_file}")
        
        return json_file, csv_file, summary_file
        
    except Exception as e:
        log_message(f"Failed to export layer data: {e}", 'error')
        return None, None, None

def create_web_app_summary(layers_data):
    """Create a summary of Web AppBuilder applications and their layer counts"""
    try:
        web_app_summary = {}
        
        for layer in layers_data:
            web_app_id = layer.get('web_app_id')
            web_app_title = layer.get('web_app_title')
            web_app_owner = layer.get('web_app_owner')
            web_app_url = layer.get('web_app_url')
            web_map_id = layer.get('web_map_id')
            web_map_title = layer.get('web_map_title')
            layer_type = layer.get('layer_type')
            
            if web_app_id not in web_app_summary:
                web_app_summary[web_app_id] = {
                    'web_app_id': web_app_id,
                    'web_app_title': web_app_title,
                    'web_app_owner': web_app_owner,
                    'web_app_url': web_app_url,
                    'web_map_id': web_map_id,
                    'web_map_title': web_map_title,
                    'total_layers': 0,
                    'operational_layers': 0,
                    'basemap_layers': 0,
                    'reference_layers': 0
                }
            
            web_app_summary[web_app_id]['total_layers'] += 1
            if layer_type == 'operational':
                web_app_summary[web_app_id]['operational_layers'] += 1
            elif layer_type == 'basemap':
                web_app_summary[web_app_id]['basemap_layers'] += 1
            elif layer_type == 'reference':
                web_app_summary[web_app_id]['reference_layers'] += 1
        
        return list(web_app_summary.values())
        
    except Exception as e:
        log_message(f"Failed to create Web App summary: {e}", 'error')
        return []

def print_layer_summary(layers_data):
    """Print a summary of the layers from all Web AppBuilder applications"""
    if not layers_data:
        log_message("No layers found")
        return
    
    # Group by layer type, service type, and web app
    layer_types = {}
    service_types = {}
    web_app_counts = {}
    
    for layer in layers_data:
        layer_type = layer.get('layer_type', 'unknown')
        service_type = layer.get('service_type', 'unknown')
        web_app_id = layer.get('web_app_id', 'unknown')
        
        layer_types[layer_type] = layer_types.get(layer_type, 0) + 1
        service_types[service_type] = service_types.get(service_type, 0) + 1
        web_app_counts[web_app_id] = web_app_counts.get(web_app_id, 0) + 1
    
    log_message("\n=== Web AppBuilder Layer Summary ===")
    log_message(f"Total layers across all Web Apps: {len(layers_data)}")
    log_message(f"Total Web AppBuilder applications processed: {len(web_app_counts)}")
    
    log_message("\nBy layer type:")
    for layer_type, count in layer_types.items():
        log_message(f"  {layer_type}: {count}")
    
    log_message("\nBy service type:")
    for service_type, count in service_types.items():
        log_message(f"  {service_type}: {count}")
    
    log_message("\nTop 10 Web Apps by layer count:")
    sorted_web_apps = sorted(web_app_counts.items(), key=lambda x: x[1], reverse=True)
    for i, (web_app_id, count) in enumerate(sorted_web_apps[:10]):
        # Find the web app title for this ID
        web_app_title = "Unknown"
        for layer in layers_data:
            if layer.get('web_app_id') == web_app_id:
                web_app_title = layer.get('web_app_title', 'Unknown')
                break
        log_message(f"  {i+1}. {web_app_title[:50]}... ({count} layers)")

def main():
    """Main execution function"""
    try:
        # Initialize logging
        output_dir = init_logging()
        log_message("Starting Web AppBuilder Layer Listing")
        
        # Connect to ArcGIS
        if not connect_to_arcgis():
            return False
        
        # List all Web AppBuilder layers
        layers_data = list_all_web_app_layers()
        if not layers_data:
            log_message("No layers found to process", 'warning')
            return False
        
        # Print summary
        print_layer_summary(layers_data)
        
        # Export to files
        json_file, csv_file, summary_file = export_layers_to_files(layers_data, output_dir)
        
        log_message("Successfully completed Web AppBuilder layer listing")
        log_message(f"Files created:")
        log_message(f"  Layer details (JSON): {json_file}")
        log_message(f"  Layer details (CSV): {csv_file}")
        log_message(f"  Web App summary (CSV): {summary_file}")
        
        return True
        
    except Exception as e:
        log_message(f"Script failed with error: {e}", 'error')
        import traceback
        log_message(traceback.format_exc(), 'error')
        return False

if __name__ == '__main__':
    # No need for user input since we're processing all Web AppBuilder apps
    print("This script will process ALL Web AppBuilder applications in your organization.")
    print("It will exclude Esri's content and focus only on your organization's apps.")
    
    success = main()
    if success:
        print("Script completed successfully")
    else:
        print("Script failed - check log file for details")
        exit(1)
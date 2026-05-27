'''
Name: GetAllArcGISServiceMetadata.py
Developed by: Julie Tripp
Date: 09/20/2024

Summary:   This script retrieves all ArcGIS services from a specified ArcGIS Online or ArcGIS Enterprise portal and exports the service metadata to a JSON file.

Usage:     Run the script and follow the prompts to connect to the ArcGIS portal and export the service metadata to a JSON file.

'''
import requests
import json
import xmltodict
import getpass
import os
from arcgis.gis import GIS
from datetime import datetime
from tqdm import tqdm
from pprint import pprint
import pandas as pd
import traceback
import logging
import time

DEBUG_MODE = False
SUMMARY_ONLY = True


ARCGIS_URL = ''
BASE_URL = ''

TIMESTAMP = datetime.now().strftime('%Y%m%d%H%M%S')

FILENAME_BASE = 'ArcGIS_Items_'
SELECTED_PORTAL = None

gis = None
token = None
arcgis_username = None
arcgis_password = None
max_arcgis_items = 10000

# hard-coded list of ArcGIS item types that are Text/JSON or JSON from https://developers.arcgis.com/rest/users-groups-and-items/items-and-item-types/
# arcgis_items_w_json = ['Dashboard', 'Web Map', 'Feature Collection']
arcgis_items_w_json = ['Dashboard', 'Web Map', 'Feature Collection', '360 VR Experience', 'Map Area', 'Web Scene', 
                       'Feature Collection Template', 'Feature Service', 'Group Layer', 'Image Service', 'Map Service',
                       'Oriented Imagery Catalog', 'Relational Database Connection', '3DTilesService', 'Scene Service',
                       'Vector Tile Service', 'WFS', 'WMTS', 'Dashboard', 'Data Pipeline', 'Deep Learning Studio Project',
                       'Esri Classification Schema', 'Excalibur Imagery Project','GeoBIM Application', 'GeoBIM Project',
                       'Hub Event', 'Hub Initiative', 'Hub Initiative Template', 'Hub Page', 'Hub Project', 'Hub Site Application', 
                       'Insights Workbook', 'Insights Model', 'Insights Page', 'Insights Theme', 'Investigation', 'Knowledge Studio Project',
                       'Mission', 'Mobile Application', 'Ortho Mapping Project', 'Ortho Mapping Template', 'Solution', 'StoryMap',
                       'Web AppBuilder Widget', 'Web Experience', 'Web Experience Template', 'Web Mapping Application', 'Workforce Project', 
                       'Color Set', 'Content Category Set', 'StoryMap Theme', 'Style', 'Symbol Set']

user_folders = {}

CURRENT_DIR = os.getcwd()
OUTPUT_DIR = CURRENT_DIR
OUTPUT_DIR = os.path.join(CURRENT_DIR, 'Output')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
DUMP_OUTPUT_DIR = OUTPUT_DIR


logging.basicConfig(
        filename=os.path.join(OUTPUT_DIR, f"GetAllArcGISServiceMetadata_{TIMESTAMP}.log"),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
def log_message(message, log_level='info'):
    """Log a message to file and optionally print to console.
    
    Always prints ERROR and WARNING messages. Prints INFO messages to console
    so the user can see progress. DEBUG messages only print when DEBUG_MODE is True.
    """
    if log_level == 'debug' and not DEBUG_MODE:
        return
    try:
        if log_level.lower() == 'error':
            logging.error(message)
        elif log_level.lower() == 'warning':
            logging.warning(message)
        elif log_level.lower() == 'debug':
            logging.debug(message)
        else:
            logging.info(message)
        if DEBUG_MODE:
            print(f"DEBUG: {message}")
        elif log_level.lower() != 'info':
            print(f"{log_level.upper()}: {message}")
        # else:
        #     print(f"  {message}")
    except Exception as e:
        print(f"Failed to log message: {e}", 'error')

def convert_ms_timestamp(timestamp_ms, item_id='', field_name='timestamp'):
    # Convert a millisecond epoch timestamp to a formatted datetime string.
    # Returns None if the timestamp is invalid or out of range (before 1970 or after year 3000).
    if not timestamp_ms:
        return None
    try:
        timestamp_seconds = timestamp_ms / 1000
        if 0 <= timestamp_seconds <= 32503680000:  # Unix timestamp for year 3000
            return datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
        else:
            log_message(f"Invalid {field_name} timestamp for {item_id}: {timestamp_ms}", 'debug')
            return None
    except Exception as e:
        log_message(f"Failed to convert {field_name} timestamp of {timestamp_ms} for {item_id}: {e}", 'debug')
        return None

def get_user_folder_title(user, folder_id):
    """
    Get the folder title for a user and folder ID.
    """
    global user_folders
    # log_message(user)
    # log_message(folder_id)
    try:
        if user not in user_folders:
            user_folders[user] = {}
            gis_user = gis.users.get(username=user)
            # log_message(gis_user)
            # log_message(gis_user.folders)
            for folder in gis_user.folders:
                # log_message(folder)
                # log_message(folder['id'])
                # log_message(folder['title'])
                user_folders[user][folder['id']] = folder['title']
    except Exception as e:
        log_message(f"Failed to get user folders for {user}: {e}", 'error')
        
    return user_folders[user].get(folder_id, '')

def get_user_input(prompt, default_value='', value_to_check=''):
    # Prompt the user for input with an optional default value. Skips prompt if value_to_check is provided.
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    user_input = input(f"{input_prompt}: ")
    user_input = user_input.strip()
    if user_input == '' or user_input is None:
        user_input = default_value
    print(f"{prompt}: {user_input}")
    return user_input

def connect_to_arcgis():
    # Prompt the user to select a portal and authenticate. Returns True if connected successfully.
    global ARCGIS_URL, BASE_URL, SELECTED_PORTAL, FILENAME_BASE, gis, arcgis_username, arcgis_password
    connected = False

    # ArcGIS Online
    arcgis_url_agol = 'https://myorg.maps.arcgis.com'
    base_url_agol = 'https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services'
    # New ArcGIS Enterprise
    arcgis_url_org = 'https://gis.example.com/arcgisportal'
    base_url_org = 'https://gis.example.com/arcgisserver/rest/services'
    # base_url_org = 'https://gis.example.com/arcgisserver/rest/services/'
    # Old ArcGIS Enterprise
    arcgis_url_ent = 'https://gis2.example.com/portal'
    base_url_ent = 'https://gis2.example.com/server/rest/services'
    
    which_portal = get_user_input("Which ArcGIS portal (AGOL, ORG)", default_value='ORG')   # ENT, 
    which_portal = which_portal.upper()
    if which_portal.startswith('A'):
        ARCGIS_URL = arcgis_url_agol
        BASE_URL = base_url_agol
        SELECTED_PORTAL = 'AGOL'
        FILENAME_BASE = 'ArcGIS_Items_AGOL'
    else:
        ARCGIS_URL = arcgis_url_org
        BASE_URL = base_url_org
        SELECTED_PORTAL = 'ORG'
        FILENAME_BASE = 'ArcGIS_Items_ORG'
    '''
    elif which_portal.startswith('R'):
        ARCGIS_URL = arcgis_url_ent
        BASE_URL = base_url_ent
        SELECTED_PORTAL = 'ENT'
        FILENAME_BASE = 'ArcGIS_Items_ENT'
    '''
    
    # # Get ArcGIS URL from the user or default to 'https://gis.example.com/arcgisportal'
    # ARCGIS_URL = get_user_input("ArcGIS URL", default_value=ARCGIS_URL)
    
    # Get arcgis_username and password from the user
    arcgis_username = get_user_input("ArcGIS Username (not SSO)", default_value='gisadmin')
    arcgis_password = getpass.getpass(f"**  ArcGIS Password for {arcgis_username}: ")
    if arcgis_username == "" or arcgis_password == "":
        log_message("Missing username or password.", 'error')
    else:
        '''
        try:
            arcpy.SignInToPortal(ARCGIS_URL, arcgis_username, arcgis_password)
            connected = True
            log_message(f"Connected to {ARCGIS_URL} as {arcgis_username}")
        except Exception as e:
            log_message(f"Failed to connect to {ARCGIS_URL} using arcpy: {e}", 'error')
        '''
        try:
            gis = GIS(ARCGIS_URL, arcgis_username, arcgis_password)
            connected = True
            log_message(f"Connected to {ARCGIS_URL} using GIS")
        except Exception as e:
            log_message(f"Failed to connect to {ARCGIS_URL} using GIS: {e}", 'error')
    return connected

def get_arcgis_token():
    # Acquire a REST API token from the ArcGIS portal using stored credentials.
    global token, ARCGIS_URL, arcgis_username, arcgis_password
    if token != '' and token is not None:
        return token
    # username = input("Portal Username: ")
    arcgis_username = get_user_input("ArcGIS Username", default_value='gisadmin', value_to_check=arcgis_username)
    if arcgis_username == '':
        log_message("Username is required", 'error')
        return token
    if arcgis_password is None or arcgis_password == '':
        arcgis_password = getpass.getpass(f"Password for {arcgis_username}: ")
    if arcgis_password == '':
        log_message("Password is required", 'error')
        return token
    url = f"{ARCGIS_URL}/sharing/rest/generateToken"
    data = {
        'username': arcgis_username,
        'password': arcgis_password,
        'referer': ARCGIS_URL,
        'f': 'json'
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token = json.loads(response.text)['token']
        else:
            log_message(f"Failed to get token: {response.status_code}", 'error')
    except Exception as e:
        log_message(f"Failed to get token: {e}", 'error')
    return token

def get_headers():
    # Return authorization headers using the current REST API token.
    token = get_arcgis_token()
    if token == '':
        return {}
    return {"Authorization": f"Bearer {token}"}

def get_all_values_from_key(data, key):
    # Recursively search nested dicts/lists for all values matching the given key.
    values = []
    
    if data is None:
        return values
    
    try:
        if hasattr(data, 'to_dict'):
            data = data.to_dict()
    except Exception as e:
        data = data
        
    try:
        # If data is a dictionary, look for the key
        if isinstance(data, dict):
            # check if key is in the dictionary
            if key in data:
                for k, v in data.items():
                    if k == key:
                        values.append(v)
                    # Recursively search nested dictionaries or lists
                    if isinstance(v, (dict, list)):
                        values.extend(get_all_values_from_key(v, key))

        # If data is a list, iterate through the list and search each item
        elif isinstance(data, list):
            for item in data:
                values.extend(get_all_values_from_key(item, key))
    except Exception as e:
        log_message(f"Failed to get all values from key: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
            
    return values

def get_value_from_key(data, key):
    # Return a single value for the key if found once, a list if found multiple times, or None.
    value = get_all_values_from_key(data, key)
    try:
        if value is None or value == [] or value == '' or len(value) == 0:
            return None
        if len(value) == 1:
            return value[0]
        else:
            return value
    except Exception as e:
        return value

def get_all_gis_items():
    # Query the portal for all content items, extract relevant metadata, and export to JSON/CSV.
    log_message("Getting all GIS items")
    
    relevant_items = {}
    items = []
    error_count = 0
    
    if gis is None:
        return items
    try:
        query_string = ""
        # query_string = "item_type:('Geoprocesing Service', 'Image Service', 'Feature Service', 'Map Service', 'Vector Tile Package', 'Vector Tile Service', 'Web Map', 'CSV', 'CSV Collection', 'Dashboard', 'Feature Collection')"
        gis_items = gis.content.search(query=query_string, max_items=max_arcgis_items)
        log_message(f"Retrieved {len(gis_items)} GIS items")
        # export all gis_items to file
        gis_items_filename = f"{FILENAME_BASE}_{TIMESTAMP}_gis_items"
        gis_items_filepath = os.path.join(OUTPUT_DIR, f"{gis_items_filename}.json")
        gis_items_list = []
        for item in gis_items:
            gis_items_list.append(item)
        with open(gis_items_filepath, 'w') as f:
            json.dump(gis_items_list, f, indent=4)
        log_message(f"Exported GIS items to '{gis_items_filepath}'")
        # export as a csv file
        gis_items_df = pd.DataFrame(gis_items_list)
        gis_items_csv_filepath = os.path.join(OUTPUT_DIR, f"{gis_items_filename}.csv")
        gis_items_df.to_csv(gis_items_csv_filepath, index=False)
        log_message(f"Exported GIS items to '{gis_items_csv_filepath}'")
        # return items
        
        for item in tqdm(gis_items, desc="Retrieving GIS items"):
            # log_message(item)
            item_data = item
            
            # initialize relevant_item data
            item_id = None
            item_type = None
            item_owner = None
            owner_folder_name = None
            item_url = None
            item_title = None
            item_summary = None
            item_tags = None
            item_credits = None
            item_description = None
            item_size = None
            item_content_status = None
            item_categories = None
            item_group_categories = None
            item_num_views = None
            item_lastviewed = None
            item_created = None
            item_modified = None
            sourceUrl = None
            groups = []
            share_with_everyone = False
            share_with_org = False
            
            item_data_filename = None
            
            try:
                item_id = item_data.id
                if not SUMMARY_ONLY:
                    log_message(f"Getting item data for {item_id}", 'debug')
                    try:
                        item_data_get = gis.content.get(item_id)
                        # pprint(item_data_get)
                        if not SUMMARY_ONLY:
                            export_json_to_file(item_data_get, f"{FILENAME_BASE}_{item_id}_get")
                        item_data = item_data_get
                        log_message(f"Got item data for {item_id}", 'debug')
                    except Exception as e:
                        # just keep going with the item_data that was already retrieved
                        log_message(f"Failed to get item data from GIS.content for {item_id}: {e}", 'error')
                        log_message(traceback.format_exc(), 'debug')

                log_message(f"Pulling relevant item data for {item_id}", 'debug')
                try:
                    item_type = item_data.get('type', None)
                    item_owner = item_data.get('owner', None)
                    item_url = item_data.get('url', None)
                    item_title = item_data.get('title', None)
                    item_summary = item_data.get('snippet', None)
                    item_tags = item_data.get('tags', None)
                    item_credits = item_data.get('accessInformation', None)
                    item_description = item_data.get('description', None)
                    # pprint(sourceUrl)
                    item_size = item_data.get('size', None)
                    item_content_status = item_data.get('contentStatus', None)
                    item_categories = item_data.get('categories', None)
                    item_num_views = item_data.get('numViews', None)
                    item_lastviewed_ms = item_data.get('lastViewed', None)
                    item_group_categories = item_data.get('groupCategories', None)
                except Exception as e:
                    log_message(f"Failed to pull some relevant item data for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                
                try:
                    sourceUrl = get_value_from_key(item_data, 'sourceUrl')
                except Exception as e:
                    log_message(f"Failed to get sourceUrl for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                try:
                    owner_folder_name = get_user_folder_title(item_owner, item_data.get('ownerFolder', None))
                except Exception as e:
                    log_message(f"Failed to get owner folder name for {item_id}: {e}", 'warning')
                    log_message(traceback.format_exc(), 'warning')
                
                # Check for stored credentials and data source info
                has_stored_credentials = False
                data_source_info = None
                try:
                    # For Feature Services, check admin info
                    if item_type == 'Feature Service' and item_url:
                        admin_url = f"{item_url}/sources?f=json"
                        admin_data = get_json(admin_url)
                        if admin_data and 'sources' in admin_data:
                            for source in admin_data['sources']:
                                if 'connectionString' in source:
                                    data_source_info = source.get('name', 'Unknown source')
                                    # Check for authentication info
                                    if 'username' in str(source.get('connectionString', '')).lower():
                                        has_stored_credentials = True
                                        
                    # Also check the item's typeKeywords for credential indicators
                    type_keywords = item_data.get('typeKeywords', [])
                    if any('credential' in keyword.lower() for keyword in type_keywords):
                        has_stored_credentials = True
                except Exception as e:
                    log_message(f"Failed to check credentials for {item_id}: {e}", 'error')
                    log_message(traceback.format_exc(), 'debug')
                
                item_lastviewed = convert_ms_timestamp(item_lastviewed_ms, item_id, 'lastViewed')
                item_created = convert_ms_timestamp(item_data.get('created', None), item_id, 'created')
                item_modified = convert_ms_timestamp(item_data.get('modified', None), item_id, 'modified')
                
                try:
                    shared_with = item_data.shared_with
                    groups = shared_with.get("groups", [])
                    share_with_everyone = shared_with.get("everyone", False)
                    share_with_org = shared_with.get("org", False)
                except Exception as e:
                    log_message(f"Failed to get sharing info for {item_id}: {e}", 'warning')
                    shared_with = None
                    groups = []
                    share_with_everyone = False
                    share_with_org = False
                
                '''
                item_homepage = item_data.get('homePage', None)
                item_usage = item_data.get('usage', None)
                if item_usage is not None:
                    item_month_usage = item_usage.get('30D', None)
                    item_year_usage = item_usage.get('1Y', None)
                else:
                    item_month_usage = None
                    item_year_usage = None
                '''
                
                if not SUMMARY_ONLY:
                    if item_type in arcgis_items_w_json:
                        try:
                            # log_message("downloading item data to local file")
                        
                            # item download locally to C:\Users\JULIET~1\AppData\Local\Temp\
                            item_get_data = item.get_data()
                            if item_get_data is None or item_get_data == {} or item_get_data == '' or len(item_get_data) == 0:
                                item_get_data = item
                                # log_message("item data is None")
                            else:
                                # log_message("Got item data")
                                # pprint(item_get_data)
                                # export item_get_data to file
                                item_data_filename =  f"{FILENAME_BASE}_{item_id}_getdata.json"
                                item_data_filepath = os.path.join(DUMP_OUTPUT_DIR, item_data_filename)
                                with open(item_data_filepath, 'w') as f:
                                    try:
                                        if (not isinstance(item_get_data, dict)) and (not isinstance(item_get_data, list)):
                                            if hasattr(item_get_data, 'to_dict'):
                                                item_get_data = item_get_data.to_dict()
                                    except Exception as e:
                                        item_get_data = item_get_data
                                    
                                    if isinstance(item_get_data, dict) or isinstance(item_get_data, list):
                                        # if item_data is json
                                        json.dump(item_get_data, f, indent=4)
                                        if sourceUrl is None or sourceUrl == '' or sourceUrl == [] or sourceUrl == {} or len(sourceUrl) == 0:
                                            # sourceUrl = item_get_data.get('sourceUrl', None)
                                            sourceUrl = get_value_from_key(item_get_data, 'sourceUrl')
                                            # log_message("Got sourceUrl from item get data")
                                            # pprint(sourceUrl)
                                        
                                        # append item_get_data to item_data
                                        item_data.update(item_get_data)
                                        # exit()
                                    elif isinstance(item_get_data, str):
                                        # If it's a string, write it as-is
                                        f.write(item_get_data)
                                    else:
                                        # For other data types, convert to string before writing
                                        f.write(str(item_get_data))
                                # log_message(f"Exported item data to {item_data_filepath}")
                        except Exception as e:
                            log_message(f"Failed to get item data: {e}", 'error')
                            log_message(traceback.format_exc(), 'debug')
            except Exception as e:
                error_count += 1
                log_message(f"Failed to get relevant item data for {item_id}: {e}", 'error')
                log_message(traceback.format_exc(), 'debug')
            
            # record all above data
            relevant_item = {
                'SELECTED_PORTAL': SELECTED_PORTAL,
                'id': item_id,
                'type': item_type,
                'url': item_url,
                'title': item_title,
                'summary': item_summary,
                'tags': item_tags,
                'credits': item_credits,
                'description': item_description,
                'categories': item_categories,
                'group_categories': item_group_categories,
                'owner': item_owner,
                'owner_folder': owner_folder_name,
                'sourceUrl': sourceUrl,
                'has_stored_credentials': has_stored_credentials,
                'data_source_info': data_source_info,
                'size': item_size,
                'contentStatus': item_content_status,
                'num_views': item_num_views,
                'last_viewed': item_lastviewed,
                'created': item_created,
                'modified': item_modified,
                'groups': groups,
                'shared_with': "everyone" if share_with_everyone else "org" if share_with_org else "private"
            }
            # 'homepage': item_homepage, 'month_usage': item_month_usage, 'year_usage': item_year_usage
            if item_data_filename is not None:
                relevant_item['getdata_filename'] = item_data_filename
            # append relevant_item to relevant_items with item_url as key
            item_key = SELECTED_PORTAL + '_' + item_id
            relevant_items[item_key] = relevant_item
            
            try:
                if hasattr(item_data, 'to_dict'):
                    item_dict = item_data.to_dict()
                else:
                    item_dict = item_data
            except Exception as e:
                item_dict = item_data
                log_message(f"Failed to convert item data to dict: {e}", 'warning')
            
            try:
                if item_dict is not None:
                    # log_message(item_dict)
                    # remove 'layers' from item_dict before appending to items
                    if 'layers' in item_dict:
                        # check if layers equals [] or {} or None
                        if not(item_dict['layers'] == [] or item_dict['layers'] == {} or item_dict['layers'] is None):
                            item_dict.pop('layers')
                            # add laers back with a note that it was removed
                            item_dict['layers'] = 'removed from export'
                    if 'tables' in item_dict:
                        if not(item_dict['tables'] == [] or item_dict['tables'] == {} or item_dict['tables'] is None):
                            item_dict.pop('tables')
                            # add tables back with a note that it was removed
                            item_dict['tables'] = 'removed from export'
                    items.append(item_dict)
                    # log_message("Appended item to items")
            except Exception as e:
                log_message(f"Failed to append item_dict to items: {e}", 'error')
                log_message(traceback.format_exc(), 'debug')
            
            # # debugging only
            # if sourceUrl is not None:
            #   break
    except Exception as e:
        log_message(f"Failed to get all GIS items: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
        
    try:
        # Print summary of item types found
        type_counts = {}
        for ri in relevant_items.values():
            t = ri.get('type', 'Unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
        log_message(f"Finished processing {len(relevant_items)} items ({error_count} errors)")
        log_message("Item types found:")
        for item_type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            log_message(f"  {item_type_name}: {count}")
    except Exception as e:
        log_message(f"Unable to print summary of item types: {e}", 'warning')
    
    try:
        # print relevant_items to a file
        relevant_items_filename = f"{FILENAME_BASE}_{TIMESTAMP}_relevant_items"
        relevant_items_filepath = os.path.join(OUTPUT_DIR, f"{relevant_items_filename}.json")
        with open(relevant_items_filepath, 'w') as f:
            json.dump(relevant_items, f, indent=4)
            log_message(f"Exported relevant items to {relevant_items_filepath}")
        relevant_items_list = list(relevant_items.values())
        relevant_items_df = pd.DataFrame(relevant_items_list)
        relevant_items_filepath = os.path.join(OUTPUT_DIR, f"{relevant_items_filename}.csv")
        relevant_items_df.to_csv(relevant_items_filepath, index=False)
        log_message(f"Exported relevant items to {relevant_items_filepath}")
    except Exception as e:
        log_message(f"Failed to export relevant items to file: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
    
    return items

def get_json(url):
    # Fetch JSON from a URL using the portal token. Saves the response to a local file.
    headers = get_headers()
    if headers == {}:
        return None
    response_json = None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if response.content.strip():
                response_json = response.json()
                json_file_name = FILENAME_BASE
                try:
                    # if url starts with BASE_URL (not case sensitive), remove that part from the url
                    if url.lower().startswith(BASE_URL.lower()):
                        json_file_name = f"{json_file_name}_{url[len(BASE_URL):]}"
                    else:
                        json_file_name = f"{json_file_name}_{url}"
                except Exception as e:
                    json_file_name = f"{json_file_name}_{url}"
                    
                # clean up json_file_name
                if '?' in json_file_name:
                    json_file_name = json_file_name.split('?')[0]
                json_file_name = json_file_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
                json_file_name = json_file_name.replace('__', '_')
                if len(json_file_name) > 100:
                    json_file_name = json_file_name[-100:]
                    
                json_file_name = f"{json_file_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}_json"
                export_json_to_file(response_json, json_file_name)
            else:
                log_message(f"Failed to get JSON from {url}: Empty content", 'warning')
        else:
            log_message(f"Failed to get JSON from {url}: code ({response.status_code}) - text ({response.text})", 'error')
            log_message(traceback.format_exc(), 'debug')
    except Exception as e:
        log_message(f"Failed to get JSON from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
    return response_json

def get_json_from_xml(url):
    # Fetch XML from a URL, save raw XML, convert to dict via xmltodict, and save as JSON.
    headers = get_headers()
    if headers == {}:
        return None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if response.content.strip():
                # Save raw XML content first
                xml_file_name = FILENAME_BASE
                try:
                    # if url starts with BASE_URL (not case sensitive), remove that part from the url
                    if url.lower().startswith(BASE_URL.lower()):
                        xml_file_name = f"{xml_file_name}_{url[len(BASE_URL):]}"
                    else:
                        xml_file_name = f"{xml_file_name}_{url}"
                except Exception as e:
                    xml_file_name = f"{xml_file_name}_{url}"
                
                # clean up xml_file_name
                if '?' in xml_file_name:
                    xml_file_name = xml_file_name.split('?')[0]
                xml_file_name = xml_file_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
                xml_file_name = xml_file_name.replace('__', '_')
                if len(xml_file_name) > 100:
                    xml_file_name = xml_file_name[-100:]
                    
                # Save raw XML
                xml_filename = f"{xml_file_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                xml_filepath = os.path.join(DUMP_OUTPUT_DIR, f"{xml_filename}.xml")
                try:
                    with open(xml_filepath, 'w', encoding='utf-8') as f:
                        f.write(response.content.decode('utf-8'))
                    log_message(f"Exported raw XML to file '{xml_filepath}'", 'debug')
                except Exception as e:
                    log_message(f"Failed to export raw XML to file '{xml_filename}.xml': {e}", 'warning')
                
                # Convert XML to dict and save as JSON
                response_dict = xmltodict.parse(response.content)
                json_file_name = f"{xml_file_name}.json"
                export_json_to_file(response_dict, json_file_name)
                return xmltodict.parse(response.content)
            else:
                log_message(f"Failed to get JSON from {url}: Empty content")
                return None
        else:
            log_message(f"Failed to get JSON from {url}: {response.status_code}")
            return None
    except Exception as e:
        log_message(f"Failed to get JSON from XML from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
        return None

def get_service_data(service_url, service, folder):
    # Fetch service definition JSON and metadata XML for a single ArcGIS Server service.
    if service_url is None or service_url == '':
        return
    try:
        service_data_url = f"{service_url}?f=pjson"
        service_data = get_json(service_data_url)
        if service_data is not None:
            service['data'] = service_data
        # add folder to service data
        # service['folder'] = folder
        # service['url'] = service_url

        metadata_url = f"{service_url}/info/metadata"
        metadata_data = get_json_from_xml(metadata_url)
        if metadata_data is not None:
            if 'metadata' in metadata_data:
                service['metadata'] = metadata_data['metadata']
                if 'Esri' in metadata_data['metadata']:
                    if 'DataProperties' in metadata_data['metadata']['Esri']:
                        data_properties = metadata_data['metadata']['Esri']['DataProperties']
                        if data_properties:
                            if 'itemProps' in data_properties:
                                item_properties = data_properties['itemProps']
                                if item_properties:
                                    if 'itemName' in item_properties:
                                        item_name = item_properties['itemName']
                                        if item_name:
                                            service['metadata.itemName'] = item_name['#text']
                                    if 'itemLocation' in item_properties:
                                        item_location = item_properties['itemLocation']
                                        if item_location:
                                            if 'linkage' in item_location:
                                                linkage = item_location['linkage']
                                                if linkage:
                                                    service['metadata.linkage'] = linkage['#text']
                                            if 'protocol' in item_location:
                                                protocol = item_location['protocol']
                                                if protocol:
                                                    service['metadata.protocol'] = protocol['#text']
                            if 'coordRef' in data_properties:
                                coord_ref = data_properties['coordRef']
                                if coord_ref:
                                    if 'geogcsn' in coord_ref:
                                        geogcsn = coord_ref['geogcsn']
                                        if geogcsn:
                                            service['metadata.geogcsn'] = geogcsn['#text']
                if 'distInfo' in metadata_data['metadata']:
                    dist_info = metadata_data['metadata']['distInfo']
                    if dist_info:
                        if 'distFormat' in dist_info:
                            dist_format = dist_info['distFormat']
                            if dist_format:
                                if 'formatName' in dist_format:
                                    format_name = dist_format['formatName']
                                    if format_name:
                                        service['metadata.distFormat'] = format_name['#text']
            else:
                service['metadata'] = metadata_data
    except Exception as e:
        log_message(f"Failed to get service data from {service_url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')

def get_all_services_data(url):
    # Retrieve service definitions and metadata for all services (and folders) at the given REST endpoint.
    test_first_n_services = 0
    
    log_message('processing url: ' + url)
    data = get_json(url)
    try:
        if data is not None:
            if 'services' in data:
                if test_first_n_services > 0:
                    services = data['services'][:test_first_n_services]
                else:
                    services = data['services']
                for service in tqdm(services, desc="Retrieving service data"):
                    service_url = f"{BASE_URL}/{service['name']}/{service['type']}"
                    get_service_data(service_url, service, '')
                if 'folders' in data:
                    log_message(f'processing {len(data["folders"])} folders')
                    for folder in tqdm(data['folders'], desc="Retrieving folder data"):
                        try:
                            log_message('processing folder: ' + folder)
                            folder_url = f"{BASE_URL}/{folder}"
                            folder_data = get_json(f"{folder_url}?f=pjson")
                            if folder_data is not None:
                                if 'services' in folder_data:
                                    log_message(f'processing {len(folder_data["services"])} services in folder {folder}')
                                    if test_first_n_services > 0:
                                        folder_services = folder_data['services'][:test_first_n_services]
                                    else:
                                        folder_services = folder_data['services']
                                    for folder_service in tqdm(folder_services, desc="Retrieving folder service data"):
                                        folder_service_url = f"{BASE_URL}/{folder_service['name']}/{folder_service['type']}"
                                        get_service_data(folder_service_url, folder_service, folder)
                                    # add folder_service data to services so it can be exported to json as data in a single file
                                    services.extend(folder_services)
                        except Exception as e:
                            log_message(f"Failed to process folder '{folder}': {e}", 'error')
                            log_message(traceback.format_exc(), 'debug')
                data['services'] = services
    except Exception as e:
        log_message(f"Failed to process services data from {url}: {e}", 'error')
        log_message(traceback.format_exc(), 'debug')
    return data

def export_json_to_file(json_data, filename):
    # Write data to a JSON file (or .txt if not serializable). Filename should omit the extension.
    if (json_data is not None):
        try:
            if (not isinstance(json_data, dict)) and (not isinstance(json_data, list)):
                if hasattr(json_data, 'to_dict'):
                    json_data = json_data.to_dict()
        except Exception as e:
            json_data = json_data
            
        try:
            if isinstance(json_data, dict) or isinstance(json_data, list):
                filename = filename + '.json'
                filepath = os.path.join(DUMP_OUTPUT_DIR, filename)
                with open(filepath, 'w') as f:
                    json.dump(json_data, f, indent=4)
            else:
                filename = filename + '.txt'
                filepath = os.path.join(DUMP_OUTPUT_DIR, filename)
                with open(filepath, 'w') as f:
                    if isinstance(json_data, str):
                        # If it's a string, write it as-is
                        f.write(json_data)
                    else:
                        # For other data types, convert to string before writing
                        f.write(str(json_data))
            log_message(f"Exported JSON to file '{filepath}'", 'debug')
        except Exception as e:
            log_message(f"Failed to export JSON to file '{filename}': {e}", 'error')

def main():
    """Main entry point: connect to portal, retrieve items/services, and export results."""
    global OUTPUT_DIR, DUMP_OUTPUT_DIR
    
    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"  GetAllArcGISServiceMetadata.py")
    print(f"  Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'SUMMARY_ONLY' if SUMMARY_ONLY else 'FULL (with service data)'}")
    print(f"  Debug: {'ON' if DEBUG_MODE else 'OFF'}")
    print(f"{'='*60}\n")
    
    # def get_layerDefinition
    
    connected_to_arcgis = connect_to_arcgis()
    if not connected_to_arcgis:
        log_message("Failed to connect to ArcGIS")
        exit()
    
    # change OUTPUT_DIR to SELECTED_PORTAL directory within Output
    OUTPUT_DIR = os.path.join(OUTPUT_DIR, SELECTED_PORTAL)
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    log_message("Output directory: " + OUTPUT_DIR)
    DUMP_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'DataDump')
    if not os.path.exists(DUMP_OUTPUT_DIR):
        os.makedirs(DUMP_OUTPUT_DIR)
    
    all_gis_items = get_all_gis_items()
    # pprint(all_gis_items)
    export_json_to_file(all_gis_items, FILENAME_BASE + '_' + TIMESTAMP + '_all_gis_items')
    # exit()

    # NOTE: Previously there was a block here that iterated all_gis_items and called
    # get_service_data() for each item's URL. This has been superseded by the
    # get_all_services_data() call below (when SUMMARY_ONLY is False).
    
    '''
    for gis_item in all_gis_items:
        item_id = gis_item['id']
        service_url = gis_item['url']
        log_message(service_url)
        if service_url is None or service_url == '':
            # rest_service_url = https://myorg.maps.arcgis.com/home/item.html?id=1d1521a1fbff4cf887e21c5927a648fc&view=service
            # rest_service_url = f"{ARCGIS_URL}/home/item.html?id={item_id}&view=service"
            rest_service_url = f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}?f=json"
            log_message(rest_service_url)
            
            # get_service_data(f"{ARCGIS_URL}/sharing/rest/content/items/{item_id}", gis_item, '')
            
            rest_service_json = get_json(rest_service_url)
            if rest_service_json is not None:
                log_message(rest_service_json)
                if 'url' in rest_service_json:
                    service_url = rest_service_json['url']
                    get_service_data(service_url, gis_item, '')
                else:
                    log_message(f"Failed to get service URL from {rest_service_url}")
                    
        else:
            get_service_data(service_url, gis_item, '')
    export_json_to_file(all_gis_items, FILENAME_BASE + '_' + TIMESTAMP + '_services_data')
    # exit()
    '''
    
    if not SUMMARY_ONLY:
        url = f"{BASE_URL}/?f=pjson"
        all_services_data = get_all_services_data(url)
        export_json_to_file(all_services_data, FILENAME_BASE + '_' + TIMESTAMP + '_services_data')

    elapsed = time.time() - start_time
    elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
    print(f"\n{'='*60}")
    print(f"  Completed in {elapsed_str}")
    print(f"  Portal: {SELECTED_PORTAL} ({ARCGIS_URL})")
    print(f"  Items retrieved: {len(all_gis_items)}")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Log file: GetAllArcGISServiceMetadata_{TIMESTAMP}.log")
    print(f"{'='*60}\n")
    log_message('completed exporting all services data')

    # url = "https://gis2.example.com/server/rest/services/Hosted/?f=pjson"
    # all_services_data = get_all_services_data(url)

if __name__ == '__main__':
    main()
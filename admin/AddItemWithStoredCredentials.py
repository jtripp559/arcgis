# https://community.esri.com/t5/arcgis-online-questions/python-add-service-to-agol-with-stored-credentials/td-p/743194
# Import the GIS
from arcgis.gis import GIS
import os
import getpass
# import arcpy
import datetime
import logging
import chardet
import csv

portal_item_ids_to_add = []
# portal_item_ids_to_add = ['f96ef04d862c4df0ba8784727444ca3c','e7e5268c903a4aec9f18d4fc620eeaf9']

# Timestamp for unique naming
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# set the output_path to the Output directory within the script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(current_dir, 'Output')
if not os.path.exists(output_path):
    os.makedirs(output_path)

output_csv_path = os.path.join(output_path, f"AddedArcGISItem_{timestamp}.csv")
# Write the header to the CSV file
with open(output_csv_path, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['portal_item_id', 'portal_item_url', 'new_agol_item_id', 'new_agol_item_url', 'item_type', 'item_title', 'has_error'])

# initialize the logging general_logger and error_logger to empty
general_logger = None
error_logger = None
general_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_{timestamp}.log")
error_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_Errors_{timestamp}.log")

portal_gis = None
portal_url = None
portal_username = None
portal_password = None
agol_gis = None
agol_url = None
agol_username = None
portal_password = None

# initialize the log_hist_data variable to an empty list
log_hist_data = []
error_count = 0

def init_logging():
    global general_logger, error_logger
    
    # Create a general logger
    general_logger = logging.getLogger('general')
    general_logger.setLevel(logging.INFO)

    # Create a file handler for the general logger
    general_handler = logging.FileHandler(general_log_file_path, mode='a', encoding='utf-8')
    general_handler.setLevel(logging.INFO)

    # Add the handler to the general logger
    general_logger.addHandler(general_handler)

    # Create an error logger
    error_logger = logging.getLogger('error')
    error_logger.setLevel(logging.ERROR)

    # Create a file handler for the error logger
    error_handler = logging.FileHandler(error_log_file_path, mode='a', encoding='utf-8')
    error_handler.setLevel(logging.ERROR)

    # Add the handler to the error logger
    error_logger.addHandler(error_handler)

def log_by_type(message, log_level='info', tab_count=1):
    try:
        if message:
            msg_tabs = '\t' * tab_count
            if isinstance(message, dict):
                for key, value in message.items():
                    # print(msg)
                    msg = msg_tabs + f'key: {key}'
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
                    new_tab_count = tab_count + 1
                    log_by_type(value, log_level, new_tab_count)
            elif isinstance(message, list):
                for detail in message:
                    # print(detail)
                    msg = msg_tabs + detail
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
            else:
                # print('\t' + message)
                msg = msg_tabs + str(message)
                general_logger.info(msg)
                if log_level == 'error':
                    error_logger.error(msg)
    except Exception as e:
        log_message(f"Failed to log message by type: {e}", 'info')

def log_message(message, log_level='', message_details=None, reset_log_hist=False):
    if message == '':
        return
    global general_logger, error_logger, log_hist_data, error_count
    if log_level == 'error':
        error_count += 1
        # cycle through log_hist_data and print each message to error_logger
        for msg in log_hist_data:
            error_logger.error(msg)
    # record message to a global variable storing all the messages since reset_log_hist was set to True
    if reset_log_hist or log_level == 'error':
        # restart the log_hist_data list
        log_hist_data = []
    if log_level != 'error':
        log_hist_data.append(message)
    if log_level == '' or log_level == 'error':
        print(message)
    if log_level == '':
        log_level = 'info'
    general_logger.info(message)
    if log_level == 'error':
        error_logger.error(message)
    log_by_type(message_details, log_level)
    
def get_file_encoding(file_path):
    encoding = 'ISO-8859-1'
    try:
        with open(file_path, 'rb') as f:
            rawdata = f.read()
        result = chardet.detect(rawdata)
        encoding = result['encoding']
        log_message(f"Detected file encoding for '{file_path}': {encoding}", 'info')
    except Exception as e:
        log_message(f"Failed to get file encoding for '{file_path}': {e}", 'info')
    return encoding

def get_user_input(prompt, default_value='', value_to_check=''):
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
    log_message(f"{prompt}: {user_input}", 'info')
    return user_input

def connect_to_arcgis():
    global portal_url, portal_gis, portal_username, portal_password
    global agol_url, agol_gis, agol_username
    
    connected = False
    
    # Get portal URL from the user or default to 'https://gis.example.com/arcgisportal'
    portal_url = get_user_input("ArcGIS portal URL", default_value='https://gis.example.com/arcgisportal', value_to_check=portal_url)
    
    # Get portal_username and password from the user
    portal_username = get_user_input("ArcGIS Portal Username", default_value='GPUser', value_to_check=portal_username)
    portal_password = getpass.getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    if portal_username == "" or portal_password == "":
        log_message("Missing portal username or password.", 'error')
    else:
        '''
        try:
            arcpy.SignInToPortal(portal_url, portal_username, portal_password)
            connected = True
            log_message(f"Connected to {portal_url} as {portal_username}")
        except Exception as e:
            log_message(f"Failed to connect to {portal_url}: {e}", 'error')
        '''
        try:
            portal_gis = GIS(portal_url, portal_username, portal_password)
            connected = True
        except Exception as e:
            log_message(f"Failed to connect to arcgis portal: {e}", 'error')
    
    if connected:
        connected = False
    agol_url = get_user_input("ArcGIS Online URL", default_value='https://myorg.maps.arcgis.com/', value_to_check=agol_url)
    agol_username = get_user_input("ArcGIS Online Username", value_to_check=agol_username)
    agol_password = getpass.getpass(f"**  ArcGIS Online Password for {agol_username}: ")
    if agol_username == "" or agol_password == "":
        log_message("Missing AGOL username or password.", 'error')
    else:
        try:
            agol_gis = GIS(agol_url, agol_username, agol_password)
            connected = True
        except Exception as e:
            log_message(f"Failed to connect to {agol_url}: {e}", 'error')
    return connected

init_logging()

if not connect_to_arcgis():
    exit()

agol_user = agol_gis.properties.user.username
agol_token = agol_gis._con.token
log_message("--->Logged into AGOL as {}".format(agol_user))

# Login to Enterprise Portal

# Using Pro Instance for Example
portal_user = portal_gis.properties.user.username
log_message("--->Logged into Portal as {}".format(portal_user))

if portal_item_ids_to_add != []:
    items_to_add = [portal_gis.content.get(item_id) for item_id in portal_item_ids_to_add]
else:
    # Generate a List of Items to Add to AGOL from Portal
    # Search for the group by name
    group_name = "Coverage Share"
    groups = portal_gis.groups.search(group_name)
    group_id = groups[0].id if groups else None
    if group_id is not None:
        items_to_add = [item for item in portal_gis.content.search(query=f"group:{group_id}", max_items=1000, sort_field='modified', sort_order='desc')
                        if not any(tag.lower() == 'test' for tag in item.tags)]
    else:
        log_message(f"Group not found in Portal: {group_name}", 'error')

# Add the Portal Items to AGOL
for item in items_to_add:
    try:
        if item.owner == 'esri_livingatlas' or item.owner == 'esri':
            continue
        csv_error = ''
        item_title = item.title
        # append " - ORG" to the title
        if item.owner == 'gisadmin':
            item_title = item_title + " - ORG"
        item_id = item.id
        item_type = item.type
        item_url = item.url
        item_summary = item.snippet
        item_description = item.description
        item_credits = item.accessInformation
        item_tags = item.tags
        
        log_message(f"Adding item to AGOL: {item_title} ({item_id})")

        # Add additional tags
        if "by reference" not in item_tags:
            item_tags.append("by reference")
        if "stored credentials" not in item_tags:
            item_tags.append("stored credentials")
        
        # Check if the item already exists in AGOL
        agol_item = None
        try:
            qry = 'title:"' + item_title + '"'
            agol_items = agol_gis.content.search(query=qry, max_items=10, sort_field='modified', sort_order='desc')
            if agol_items and (agol_items is not None):
                agol_item = agol_items[0]
        except Exception as e:
            log_message(f"Item not found in AGOL: {e}")
        if agol_item is None:
            item_properties = {"title": item_title,
                               "tags": item_tags,
                               "url": item_url,
                               "type": item.type,
                               "snippet": item_summary,
                               "description": item_description,
                               "accessInformation": item_credits,
                               "serviceUsername": portal_user,
                               "servicePassword": portal_password,
                               "token": agol_token}
            owner = agol_user
            item_properties = item_properties
            
            agol_item = agol_gis.content.add(data=item_url, 
                                            owner=owner, 
                                            item_properties=item_properties)
            log_message(f"Item added to AGOL: {item_title}")
            
            agol_item_id = agol_item.id
            agol_item_url = agol_item.url
        else:
            agol_item_id = agol_item.id
            agol_item_url = agol_item.url
            csv_error = 'Item already exists'
            log_message(f"Item already exists in AGOL: {item_title}")
        log_message(f"AGOL Item ID: {agol_item_id}")
        log_message(f"AGOL Item URL: {agol_item_url}")
    except Exception as e:
        log_message(f"Failed to add item to AGOL: {e}", 'error')
        csv_error = f"Failed to add item to AGOL: {e}"
        
    with open(output_csv_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([item_id, item_url, agol_item_id, agol_item_url, item_type, item_title, csv_error])

log_message("Script completed successfully.")
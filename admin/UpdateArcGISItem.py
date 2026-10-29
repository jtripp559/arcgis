# UpdateArcGISItem.py
#
# Developed by: Julie Tripp
#               julie.tripp@rrgnbs.com
# Date:  06/05/2024
#
# Description: This script publishes raster datasets as image services to an ArcGIS Enterprise portal.
#
# Env File:
#   The script can be run with an optional .env file in the same directory as the script with the following variables:
#   Note: Any missing variables or empty values will be prompted for during script execution.
#    CSV_IMPORT_FILE_PATH=
#    WORKSPACE_TYPE_FILEGDB_OR_SDE=
#    WORKSPACE_FULL_PATH=
#    ARCGIS_SERVER_MANAGER_DB_NAME=
#    DATABASE_NAME=
#    DATABASE_OWNER_NAME=
#    ARCGIS_PORTAL_FOLDER_NAME=
#    ARCGIS_SERVER_FOLDER_NAME=
# #    INSTANCE_TYPE_SHARED_OR_DEDICATED=
#    RECYCLE_START_HOUR=
#    RECYCLE_START_MIN=
#    PORTAL_URL=
#    PORTAL_USERNAME=
#    REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING=
#
# Script execution options:
# 1. Run the script from the command line with the following command:
#    python UpdateArcGISItem.py
# 2. Run the script from the command line with the following command, providing the csv import file as an argument:
#    python UpdateArcGISItem.py "C:\path\to\import.csv"
#
# User Prompts (if empty/missing from .env file or command line argument):
# 2. ArcPy Environment Prompts:
#   - Workspace type (Options: FileGDB or SDE) - Default to SDE
#   - Full path to the workspace (e.g. T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde)
#   - Name for the database in Server Manager (e.g. sde.DEFAULT (NBS-APP1), Beisa_Datastore.gdb, dbo.DEFAULT (NBS-APP1)
#       - TIP: This is the name that will be displayed when you click on the "service" icon.
#               If you're not sure what this should be, but you know of another service that you published from Pro directly, 
#               then you can find it in the SVCManifest > Databases > SVCDatabase > Name tag of the manifest.xml file in the
#               extracted directory of the \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput directory for that service.
#           E.g. \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput\AnnualDepthToGroundwater_BasinATLAS_lev09.MapServer\extracted\
# 3. Portal Connection Prompts:
#   - Federated Server URL - Default to 'https://maps.rrgnbs.com/arcgisserver'
#   - Portal URL - Default to 'https://maps.rrgnbs.com/arcgisportal'
#   - Portal Username - Cannot be SSO enabled
#   - Portal Password
# 4. Raster Dataset Prompts:
#   - Import from CSV file (Y/N)
#     - If "Y", path to the import file
#     - If "N", name of the raster dataset(s) separated by commas (e.g. ActualEvapotranspiration2021_SSEBop, NDVI2021_SSEBop)
#        - If no raster names entered, confirm to use all raster datasets in the workspace
# 5. Database and Database Owner Name Prompts (conditional, if not a FileGDB workspace )
#   - "Database Name (e.g. NBS-APP1):"
#   - "Database Owner Name (e.g. dbo):"
#   - Prepended to the raster dataset name to create the full dataset name (e.g. NBS-APP1.dbo.ActualEvapotranspiration2021_SSEBop)
# # 6. Shared Instance - Default to Y
# 7. Portal and Server Folder Prompts (optional)
# 9. Missing Data Prompts (Conditional, if missing data in raster dataset)
#   - Title
#   - Summary
#   - Description
#   - Tags
#
# Overview:
# 1. Gather rasters to publish (either from a CSV file or from the database)
# 2. Create a local service definition draft (sddraft) file using arcpy.CreateImageSDDraft
# 3. Build pyramids and calculate statistics for the raster dataset, if needed
# 4. Manually update the service definition draft DOM with additional raster details
# 5. Stage the local service definition draft to a local service definition (sd) file using arcpy.StageService_server
# 6. Upload the local service definition to the server using arcpy.UploadServiceDefinition_server
# 7. Validate and correct the Title of the published service in the portal
#
import arcpy
import os
import datetime
import getpass
import logging
import pandas as pd
from arcgis.gis import GIS
import sys
# conda install python-dotenv
from dotenv import find_dotenv, load_dotenv
import chardet

# ******
# testing variables only
remove_sddraft_files = True    # set to True to remove the sddraft files after successful upload; False is useful for troubleshooting; set using REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING in the .env file
backup_sddraft_files = False    # set to True to backup the sddraft file before each update to the DOM
remove_sd_files = True          # set to True to remove the sd file, if created
stageService = True             # set to True to stage the service, i.e. create a local service definition (sd) file
uploadToServer = True           # set to True to upload the service definition (sd file) to the server
limit_to_first_n_datasets = 0   # limit the number of datasets to process to the first n datasets retreived from workspace
# ******
if stageService == False:
     uploadToServer = False

# set the output_path to the Output directory within the script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(current_dir, 'Output')
if not os.path.exists(output_path):
    os.makedirs(output_path)

# Timestamp for unique naming
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# initialize the all_json_data dictionary
all_json_data = {}

# initialize the logging general_logger and error_logger to empty
general_logger = None
error_logger = None
general_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_{timestamp}.log")
error_log_file_path = os.path.join(output_path, f"UpdateArcGISItem_Errors_{timestamp}.log")

# initialize the log_hist_data variable to an empty list
log_hist_data = []
error_count = 0

# Global variable to store the df built from the data in the import csv file
import_df = pd.DataFrame()

# Global dictionary to store portal group names and ids
portal_group_dict = {}

# All of the following variables can be set in the .env file
recycleStartHour = 20   # must be between 0 and 23
recycleStartMin = 0 # must be a multiple of 15, up to 45
portal_url = '' # 'https://maps.rrgnbs.com/arcgisportal'
# server_connection_file_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_arcgisserver_server_connection.ags"
portal_username = ''
workspace_type = ""
workspace_factory = ""
server_manager_db_name = ""
workspace_full_path = ""
instance_type = ''
arcgisPortalFolderName = ''
arcgisServerFolderName = ''
database_name = ''
database_owner_name = ''
csv_import_file_path = ''

# initilaize gis variable
gis = None

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

def init_global_variables():
    global portal_url, portal_username, database_name, database_owner_name, recycleStartHour, recycleStartMin, workspace_type, server_manager_db_name, workspace_full_path
    global csv_import_file_path, instance_type, arcgisPortalFolderName, arcgisServerFolderName, remove_sddraft_files
    has_env_file = False
    try:
        env_file = find_dotenv()
        if env_file:
            # Load variables from the .env file, if any
            # This .env file must be in the same directory as this script
            load_dotenv()
            has_env_file = True
            portal_url = os.getenv('PORTAL_URL','')
            portal_username = os.getenv('PORTAL_USERNAME','')
            
            workspace_type = os.getenv('WORKSPACE_TYPE_FILEGDB_OR_SDE','')
            # validate workspace_type is either FILEGDB or SDE and set to upper
            workspace_type = workspace_type.upper()
            if workspace_type not in ['FILEGDB', 'SDE']:
                workspace_type = ''
                
            server_manager_db_name = os.getenv('ARCGIS_SERVER_MANAGER_DB_NAME','')
            workspace_full_path = os.getenv('WORKSPACE_FULL_PATH','')
            database_name = os.getenv('DATABASE_NAME','')
            database_owner_name = os.getenv('DATABASE_OWNER_NAME','')
            csv_import_file_path = os.getenv('CSV_IMPORT_FILE_PATH','')
            '''
            instance_type = os.getenv('INSTANCE_TYPE_SHARED_OR_DEDICATED','')
            # validate instance type is either SHARED or DEDICATED and set to lower
            instance_type = instance_type.lower()
            if instance_type not in ['shared', 'dedicated']:
                instance_type = ''
            '''
                
            arcgisPortalFolderName = os.getenv('ARCGIS_PORTAL_FOLDER_NAME','')
            # arcgisServerFolderName = os.getenv('ARCGIS_SERVER_FOLDER_NAME','')
                
            recycleStartHour = int(os.getenv('RECYCLE_START_HOUR', '20'))
            # validate the recycleStartHour
            if recycleStartHour < 0 or recycleStartHour > 23:
                recycleStartHour = 20
                
            recycleStartMin = int(os.getenv('RECYCLE_START_MIN', '0'))
            # validate the recycleStartMin
            if recycleStartMin % 15 != 0:
                recycleStartMin = 0
            
            remove_sddraft_files_str = os.getenv('REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING', str(remove_sddraft_files))
            if remove_sddraft_files_str.lower() == 'true':
                remove_sddraft_files = True
            else:
                remove_sddraft_files = False
            
            # print all the values from the .env file
            log_message(f"Values from the .env file:", 'info')
            log_message(f"\tPortal URL: {portal_url}", 'info')
            log_message(f"\tPortal Username: {portal_username}", 'info')
            log_message(f"\tWorkspace Type: {workspace_type}", 'info')
            log_message(f"\tServer Manager DB Name: {server_manager_db_name}", 'info')
            log_message(f"\tWorkspace Full Path: {workspace_full_path}", 'info')
            log_message(f"\tDatabase Name: {database_name}", 'info')
            log_message(f"\tDatabase Owner Name: {database_owner_name}", 'info')
            log_message(f"\tCSV Import File Path: {csv_import_file_path}", 'info')
            log_message(f"\tInstance Type: {instance_type}", 'info')
            log_message(f"\tRecycle Start Hour: {recycleStartHour}", 'info')
            log_message(f"\tRecycle Start Minute: {recycleStartMin}", 'info')
    except Exception as e:
        log_message(f"Failed to load environment variables from the .env file: {e}", 'info')
    return has_env_file

'''
# Function to check if the workspace is registered with the server  # Not needed
def is_workspace_registered_with_server(workspace, server_connection_file):
    server = arcpy.mapping.ListWorkspaces(server_connection_file, "FROM_CONNECTION_FILE")[0]
    registered_workspaces = [item.path for item in arcpy.ListDataStoreItems(server, "DATABASE")]
    return workspace in registered_workspaces
'''

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

def get_recycle_time():
    global recycleStartHour, recycleStartMin
    recycleStartMin += 15
    if recycleStartMin > 59:
        recycleStartMin = 0
        recycleStartHour += 1
    if recycleStartHour > 23:
        recycleStartHour = 0
    return str(recycleStartHour).zfill(2) + ":" + str(recycleStartMin).zfill(2)

def remove_non_ascii(text):
    if pd.isnull(text):
        text = ''
    else:
        text = str(text)
    if text is None or text == '':
        return ''
    # replace non-ascii characters with a space 
    # except for the dash-like characters which are replaced with a hyphen
    return_text = ''.join(i if ord(i) < 128 else '-' if ord(i) in {8211, 8212, 8722, 8209, 8210} else ' ' for i in text)
    # return_text = saxutils.escape(return_text)
    if return_text != text:
        log_message(f"Replaced non-ascii characters in '{text}' with '{return_text}'", 'info')
    return return_text

def set_arcpy_environment():
    global workspace_type, workspace_factory, server_manager_db_name, workspace_full_path
    env_set = True
    
    return env_set

def connect_to_portal():
    global portal_url, gis, portal_username
    connected = False
    
    # Get portal URL from the user or default to 'https://maps.rrgnbs.com/arcgisportal'
    portal_url = get_user_input("ArcGIS portal URL", default_value='https://maps.rrgnbs.com/arcgisportal', value_to_check=portal_url)
    
    # Get portal_username and password from the user
    portal_username = get_user_input("ArcGIS Portal Username (not SSO)", default_value='rrgadmin', value_to_check=portal_username)
    portal_password = getpass.getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    if portal_username == "" or portal_password == "":
        log_message("Missing portal username or password.", 'error')
    else:
        try:
            arcpy.SignInToPortal(portal_url, portal_username, portal_password)
            connected = True
            log_message(f"Connected to {portal_url} as {portal_username}")
        except Exception as e:
            log_message(f"Failed to connect to {portal_url}: {e}", 'error')
        try:
            gis = GIS(portal_url, portal_username, portal_password)
        except Exception as e:
            log_message(f"Failed to connect to arcgis: {e}", 'error')
    return connected

def get_arcgis_items():
    global import_df, csv_import_file_path
    arcgis_items = []

    if csv_import_file_path == '':
        print('\t*** CSV columns names: item_id,raster_name,title,summary,description,tags,credits,instance,portal_groups,categories,group_categories')
        print("\t*** Optional columns: instance,portal_groups,categories,group_categories")
        # print("\t*** 'instance' may contain 'shared' or 'dedicated' or nothing. Nothing will default to 'shared'.")
        # get the csv file path from the user
        csv_import_file_path = get_user_input("Full path to the import file")
        if csv_import_file_path == "":
            log_message("No import file provided. Exiting...", 'error')
            return arcgis_items
    if not os.path.exists(csv_import_file_path):
        log_message(f"Import file {csv_import_file_path} does not exist. Exiting...", 'error')
        return arcgis_items
    if csv_import_file_path.split('.')[-1].lower() != 'csv':
        log_message(f"Invalid CSV file provided: {csv_import_file_path}. Exiting...", 'error')
        return arcgis_items
    try:
        import_df = pd.read_csv(csv_import_file_path, encoding=get_file_encoding(csv_import_file_path))
        # set arcgis_items to the item_id values in the import_df
        arcgis_items = import_df['item_id'].tolist()
    except Exception as e:
        log_message(f"Failed to read the import file {csv_import_file_path}: {e}", 'error')
    return arcgis_items

def update_portal_item(current_item_id = None, new_title = None, new_description=None, portal_group_names=None, categories=None, group_categories=None):
    global portal_group_dict
    
    if current_item_id is None:
        log_message("Missing required parameters for updating portal item", 'error')
        return
    
    gis_item = None
    
    '''
    if current_item_id is None:
        try:
            log_message(f"Searching for portal item with title '{raster_name}' or '{new_title}'", 'info')
            qry = 'title:"' + raster_name + '"' + ' OR title:"' + new_title + '"'
            gis_items = gis.content.search(query=qry, max_items=10, sort_field='modified', sort_order='desc')
            if gis_items or gis_items is not None:
                # get the first result
                gis_item = gis_items[0]
        except Exception as e:
            log_message(f"Failed to find portal item: {e}", 'error')
            return None
    else:
    '''
    
    try:
        log_message(f"Getting portal item with id {current_item_id}", 'info')
        gis_item = gis.content.get(current_item_id)
    except Exception as e:
        log_message(f"Failed to get portal item: {e}", 'error')
        return None
    
    item_id = gis_item.get('id', '')
    if item_id != '' and item_id is not None:
        log_message(f"Found portal item {item_id}", 'info')
        
        try:
            item_title = gis_item.get('title', '')
            if (new_title is not None) and new_title != '':
                if item_title == ''or item_title is None or item_title != new_title:
                    gis_item.update({'title': new_title})
                    log_message(f"\tUpdated item title to '{new_title}' from '{item_title}'", 'info')
        except Exception as e:
            log_message(f"Failed to update item title: {e}", 'error')
        
        try:
            if (new_description is not None) and new_description != '':
                item_description = gis_item.get('description', '')
                if item_description == '' or item_description != new_description or item_description is None:
                    gis_item.update({'description': new_description})
                    log_message(f"\tUpdated item description to \n\r\t'{new_description}' \n\r\tfrom \n\r\t'{item_description}'", 'info')
        except Exception as e:
            log_message(f"Failed to update item description: {e}", 'error')
        
        try:
            if (categories is not None) and categories != '':
                category_list = []
                if isinstance(categories, str):
                    category_list = categories.split(',')
                elif isinstance(categories, list):
                    category_list = categories
                else:
                    # try to convert categories to a string
                    try:
                        categories_str = str(categories)
                        category_list = categories_str.split(',')
                    except:
                        category_list = [categories]
                if category_list != []:
                    # prepend /Categories/ to every item in category_list if it does not already start with /Categories/
                    category_list = [cat if cat.startswith('/Categories/') else '/Categories/' + cat for cat in category_list]
                    gis_item.update(item_properties={"categories": category_list})
                    log_message(f"\tUpdated item categories to {category_list}", 'info')
        except Exception as e:
            log_message(f"Failed to update item categories: {e}", 'error')
        
        
        try:
            if (group_categories is not None) and group_categories != '':
                group_category_list = []
                if isinstance(group_categories, str):
                    group_category_list = group_categories.split(',')
                elif isinstance(group_categories, list):
                    group_category_list = group_categories
                else:
                    # try to convert group_categories to a string
                    try:
                        group_categories_str = str(group_categories)
                        group_category_list = group_categories_str.split(',')
                    except:
                        group_category_list = [group_categories]
                if group_category_list != []:
                    # prepend /Categories/ to every item in group_category_list if it does not already start with /Categories/
                    group_category_list = [cat if cat.startswith('/Categories/') else '/Categories/' + cat for cat in group_category_list]
                    
                    gis_item.update(item_properties={"groupCategories": group_category_list})
                    log_message(f"\tUpdated item groupCategories to {group_category_list}", 'info')
        except Exception as e:
            log_message(f"Failed to update item groupCategories: {e}", 'error')
        
        
        
        try:
            if (portal_group_names is not None) and portal_group_names != '':
                portal_group_ids = []
                sharing_portal_group_ids = []
                if isinstance(portal_group_names, str):
                    portal_group_names_list = portal_group_names.split(',')
                elif isinstance(portal_group_names, list):
                    portal_group_names_list = portal_group_names
                else:
                    # try to convert portal_group_names to a string
                    try:
                        portal_group_names_str = str(portal_group_names)
                        portal_group_names_list = portal_group_names_str.split(',')
                    except:
                        portal_group_names_list = [portal_group_names]
                for portal_group_name in portal_group_names_list:
                    # Search for the group by name and get its ID
                    portal_group_name = portal_group_name.strip()
                    # lookup the portal group id in the global dictionary
                    portal_group = portal_group_dict.get(portal_group_name, None)
                    if portal_group is None:
                        # search for the portal group by name
                        group_search = gis.groups.search(portal_group_name)
                        if group_search:
                            portal_group = group_search[0]
                            # log_message('group_search return:', 'info', portal_group)
                            if portal_group:
                                # store the portal group name and id in the global dictionary
                                portal_group_dict[portal_group_name] = portal_group
                                
                    if portal_group:
                        # log_message('group id: ', log_level='info', message_details=portal_group.get('id', ''))
                        # log_message('group capabilities: ', log_level='info', message_details=portal_group.get('capabilities', []))
                        group_capabilities = portal_group.get('capabilities', [])
                        if group_capabilities != []:
                            if 'updateitemcontrol' in group_capabilities:
                                sharing_portal_group_ids.append(portal_group.get('id', ''))
                                continue
                        portal_group_ids.append(portal_group.get('id', ''))
                if portal_group_ids != [] or sharing_portal_group_ids != []:
                    if portal_group_ids != []:
                        log_message(f"Sharing portal item with groups", 'info', message_details=portal_group_ids)
                        gis_item.share(groups=portal_group_ids)
                    if sharing_portal_group_ids != []:
                        log_message(f"Sharing portal item with shared update capable groups", 'info', message_details=sharing_portal_group_ids)
                        gis_item.share(groups=sharing_portal_group_ids, allow_members_to_edit=True)
                    log_message(f"Updated portal item with groups: {portal_group_names}", 'info')
        except Exception as e:
            log_message(f"Failed to update item groups: {e}", 'error')
            
        '''
        try:
            # Attempt to update popupInfo title in order to enable the Data JSON
            popupModified = False
            hasLayers = False
            if 'layers' in gis_item:
                for layer in gis_item.layers:
                    # Update popupInfo title for each layer
                    hasLayers = True
                    try:
                        if 'popupInfo' in layer:
                            popup_info = layer.popupInfo
                            popup_info['title'] = new_title
                            layer.manager.update_definition({'popupInfo': popup_info})
                            popupModified = True
                            log_message(f"\tUpdated popupInfo title to '{new_title}' for layer {layer.name}", 'info')
                        elif 'popupInfo' in layer.properties:
                            popup_info = layer.properties.popupInfo
                            popup_info['title'] = new_title
                            layer.manager.update_definition({'popupInfo': popup_info})
                            popupModified = True
                            log_message(f"\tUpdated popupInfo title to '{new_title}' for layer {layer.properties.name}", 'info')
                    except Exception as e:
                        log_message(f"Failed to update popupInfo title: {e}", 'error')
            else:
                log_message(f"Item does not have layers", 'info')
            if not popupModified:
                if hasLayers:
                    log_message(f"Failed to update popupInfo title for any layer", 'error')
                else:
                    log_message(f"Item does not have layers", 'info')
                    # attempt to create a new layer
                    img_svc_url = gis_item.url
                    new_lyr = Service(url_or_item=img_svc_url, server=gis)
        except Exception as e:
            log_message(f"Failed to update popupInfo title: {e}", 'error')
        '''
    
    return item_id


# Begin Main

init_logging()

init_global_variables()

env_set = set_arcpy_environment()
if not env_set:
    exit()

connected_to_portal = connect_to_portal()
if not connected_to_portal:
    exit()

arcgis_items = get_arcgis_items()
if arcgis_items == []:
    log_message("No datasets found. Exiting...", 'error')
    exit()
    
'''
if instance_type == 'dedicated':
    is_shared_instance = False
elif instance_type == 'shared':
    is_shared_instance = True
else:
    # prompt user for is_shared_instance
    publish_as_shared = get_user_input("Published as shared instance(s) by default (Y/N)?", default_value='Y')
    if publish_as_shared.upper() == 'Y':
        is_shared_instance = True
    else:
        is_shared_instance = False    
# get portal and server folder names to publish to from the user
arcgisPortalFolderName = get_user_input("ArcGIS Portal folder name, e.g. 'RRG_Enterprise' (or press enter to publish to root)", value_to_check=arcgisPortalFolderName)
'''

# cycle through all datasets in arcgis_items
len_arcgis_items = len(arcgis_items)
log_message(f"Processing {len_arcgis_items} datasets")
for item_id in arcgis_items:
    log_message(f"****************************************************", 'info', message_details=None, reset_log_hist=True)
    
    item_id = str(item_id)
    
    tags = ''
    summary = ''
    title = ''
    description = ''
    credits = ''
    # item_is_shared_instance = is_shared_instance
    portal_groups = ''
    categories = ''
    group_categories = ''
    spatialReference = ''
    
    # get data from the import file
    # item_row = import_df.loc[import_df['raster_name'] == raster_name]
    item_row = import_df.loc[import_df['item_id'] == item_id]
    title = item_row['title'].values[0]
    summary = item_row['summary'].values[0]
    description = item_row['description'].values[0]
    tags = item_row['tags'].values[0]
    credits = item_row['credits'].values[0]
    '''
    if 'instance' in item_row:
        instance = item_row['instance'].values[0].lower()
        if instance == 'dedicated':
            item_is_shared_instance = False
    '''
    if 'portal_groups' in item_row:
        portal_groups = item_row['portal_groups'].values[0]
    if 'categories' in item_row:
        categories = item_row['categories'].values[0]
    if 'group_categories' in item_row:
        group_categories = item_row['group_categories'].values[0]

    title = remove_non_ascii(title)
    summary = remove_non_ascii(summary)
    description = remove_non_ascii(description)
    credits = remove_non_ascii(credits)
    tags = remove_non_ascii(tags)
    
    log_message(f"Item: {item_id}", 'info')
    log_message(f"\tTitle: {title}", 'info')
    log_message(f"\tSummary: {summary}", 'info')
    log_message(f"\tDescription: {description}", 'info')
    log_message(f"\tTags: {tags}", 'info')
    # log_message(f"\tIs Shared Instance: {item_is_shared_instance}", 'info')
    
    update_portal_item(current_item_id=item_id,
                       new_title=title, 
                       new_description=description, 
                       portal_group_names=portal_groups, 
                       categories=categories,
                       group_categories=group_categories)
    
# log_message('portal_groups:', 'info', message_details=portal_group_dict)

log_message(f'Script completed. See log file for details: {general_log_file_path}')
if error_count > 0:
    log_message(f"Errors occurred. Please see error log file for details: {error_log_file_path}", 'error')
else:
    # close error_logger
    for handler in error_logger.handlers[:]:
        handler.close()
    error_logger.removeHandler(handler)
    # if error_log_file_path exists, delete it
    if os.path.exists(error_log_file_path):
        os.remove(error_log_file_path)
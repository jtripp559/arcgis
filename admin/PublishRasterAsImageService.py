# PublishRasterAsImageService.py
#
# Developed by: Julie Tripp
#
# Date:  06/05/2024
#
# NOTE: sddraft files created from sharing in ArcGIS Pro can be found here:
#       C:\Users\userName\AppData\Local\ESRI\ArcGISPro\Staging\SharingProcesses
#
# Description: This script publishes raster datasets as image services to an ArcGIS Enterprise portal.
#
# Env File:
#   The script can be run with an optional .env file in the same directory as the script with the following variables:
#   Note: Any missing variables or empty values will be prompted for during script execution.
#    REPOSITORY_ID=
#    CSV_IMPORT_FILE_PATH=
#    WORKSPACE_TYPE_FILEGDB_OR_SDE=
#    WORKSPACE_FULL_PATH=
#    ARCGIS_SERVER_MANAGER_DB_NAME=
#    DATABASE_NAME=
#    DATABASE_OWNER_NAME=
#    ARCGIS_PORTAL_FOLDER_NAME=
#    ARCGIS_SERVER_FOLDER_NAME=
#    INSTANCE_TYPE_SHARED_OR_DEDICATED=
#    DEFAULT_TAGS=
#    RECYCLE_START_HOUR=
#    RECYCLE_START_MIN=
#    SPECIFIC_RASTERS_TO_IMPORT=
#    FEDERATED_SERVER_URL=
#    PORTAL_URL=
#    PORTAL_USERNAME=
#    REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING=
#
# Script execution options:
# 1. Run the script from the command line with the following command:
#    python PublishRasterAsImageService.py
# 2. Run the script from the command line with the following command, providing the csv import file as an argument:
#    python PublishRasterAsImageService.py "C:\path\to\import.csv"
#
# User Prompts (if empty/missing from .env file or command line argument):
# 1. Repository ID: 
#   - Find the RepositoryID in the manifest.xml of a service manually published to Portal from Pro for the same connection. See \\org-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput.
# 2. ArcPy Environment Prompts:
#   - Workspace type (Options: FileGDB or SDE) - Default to SDE
#   - Full path to the workspace (e.g. D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde)
#   - Name for the database in Server Manager (e.g. sde.DEFAULT (ORG-APP1), GenericProj1_Datastore.gdb, dbo.DEFAULT (ORG-APP1)
#       - TIP: This is the name that will be displayed when you click on the "service" icon.
#               If you're not sure what this should be, but you know of another service that you published from Pro directly, 
#               then you can find it in the SVCManifest > Databases > SVCDatabase > Name tag of the manifest.xml file in the
#               extracted directory of the \\org-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput directory for that service.
#           E.g. \\org-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput\AnnualDepthToGroundwater_BasinATLAS_lev09.MapServer\extracted\
# 3. Portal Connection Prompts:
#   - Federated Server URL - Default to 'https://gis.example.com/arcgisserver'
#   - Portal URL - Default to 'https://gis.example.com/arcgisportal'
#   - Portal Username - Cannot be SSO enabled
#   - Portal Password
# 4. Raster Dataset Prompts:
#   - Import from CSV file (Y/N)
#     - If "Y", path to the import file
#     - If "N", name of the raster dataset(s) separated by commas (e.g. ActualEvapotranspiration2021_SSEBop, NDVI2021_SSEBop)
#        - If no raster names entered, confirm to use all raster datasets in the workspace
# 5. Database and Database Owner Name Prompts (conditional, if not a FileGDB workspace )
#   - "Database Name (e.g. ORG-APP1):"
#   - "Database Owner Name (e.g. dbo):"
#   - Prepended to the raster dataset name to create the full dataset name (e.g. ORG-APP1.dbo.ActualEvapotranspiration2021_SSEBop)
# 6. Shared Instance - Default to Y
# 7. Portal and Server Folder Prompts (optional)
# 8. Default Tags for all Rasters (optional)
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
import json
from xml.dom import minidom as DOM
import logging
import shutil
from pprint import pprint
import pandas as pd
from arcgis.gis import GIS
import sys
# conda install python-dotenv
from dotenv import find_dotenv, load_dotenv
import chardet
# from arcgis.layers import Service
import xml.sax.saxutils as saxutils

# ******
# testing variables only
remove_sddraft_files = False    # set to True to remove the sddraft files after successful upload; False is useful for troubleshooting; set using REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING in the .env file
backup_sddraft_files = False    # set to True to backup the sddraft file before each update to the DOM
remove_sd_files = True          # set to True to remove the sd file, if created
stageService = True             # set to True to stage the service, i.e. create a local service definition (sd) file
uploadToServer = True           # set to True to upload the service definition (sd file) to the server
limit_to_first_n_datasets = 0   # limit the number of datasets to process to the first n datasets retreived from workspace
# ******
if stageService == False:
     uploadToServer = False
if uploadToServer == False:
    remove_sd_files = False
    remove_sddraft_files = False

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
general_log_file_path = os.path.join(output_path, f"PublishRasterAsImageService_{timestamp}.log")
error_log_file_path = os.path.join(output_path, f"PublishRasterAsImageService_Errors_{timestamp}.log")

# initialize the log_hist_data variable to an empty list
log_hist_data = []
error_count = 0

# Global variable to store the df built from the data in the import csv file
raster_import_df = pd.DataFrame()

# Global dictionary to store portal group names and ids
portal_group_dict = {}

# All of the following variables can be set in the .env file
recycleStartHour = 20   # must be between 0 and 23
recycleStartMin = 0 # must be a multiple of 15, up to 45
federated_server_url = '' # "https://gis.example.com/arcgisserver"
portal_url = '' # 'https://gis.example.com/arcgisportal'
# server_connection_file_path = r"D:\GenericArcGISConnectionsDir\ORG_arcgisserver_server_connection.ags"
portal_username = ''
workspace_type = ""
workspace_factory = ""
server_manager_db_name = ""
workspace_full_path = ""
repository_id = ''
instance_type = ''
arcgisPortalFolderName = ''
arcgisServerFolderName = ''
database_name = ''
database_owner_name = ''
csv_import_file_path = ''
specific_rasters_to_import = ''
default_tags = ''

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
    global federated_server_url, portal_url, portal_username, database_name, database_owner_name, recycleStartHour, recycleStartMin, workspace_type, server_manager_db_name, workspace_full_path
    global csv_import_file_path, specific_rasters_to_import, repository_id, instance_type, arcgisPortalFolderName, arcgisServerFolderName, default_tags, remove_sddraft_files
    has_env_file = False
    try:
        env_file = find_dotenv()
        if env_file:
            # Load variables from the .env file, if any
            # This .env file must be in the same directory as this script
            load_dotenv()
            has_env_file = True
            federated_server_url = os.getenv('FEDERATED_SERVER_URL','')
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
            specific_rasters_to_import = os.getenv('SPECIFIC_RASTERS_TO_IMPORT','')
            default_tags = os.getenv('DEFAULT_TAGS','')
            repository_id = os.getenv('REPOSITORY_ID','')
            instance_type = os.getenv('INSTANCE_TYPE_SHARED_OR_DEDICATED','')
            # validate instance type is either SHARED or DEDICATED and set to lower
            instance_type = instance_type.lower()
            if instance_type not in ['shared', 'dedicated']:
                instance_type = ''
                
            arcgisPortalFolderName = os.getenv('ARCGIS_PORTAL_FOLDER_NAME','')
            arcgisServerFolderName = os.getenv('ARCGIS_SERVER_FOLDER_NAME','')
                
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
            log_message(f"\tFederated Server URL: {federated_server_url}", 'info')
            log_message(f"\tPortal URL: {portal_url}", 'info')
            log_message(f"\tPortal Username: {portal_username}", 'info')
            log_message(f"\tWorkspace Type: {workspace_type}", 'info')
            log_message(f"\tServer Manager DB Name: {server_manager_db_name}", 'info')
            log_message(f"\tWorkspace Full Path: {workspace_full_path}", 'info')
            log_message(f"\tDatabase Name: {database_name}", 'info')
            log_message(f"\tDatabase Owner Name: {database_owner_name}", 'info')
            log_message(f"\tCSV Import File Path: {csv_import_file_path}", 'info')
            log_message(f"\tSpecific Rasters to Import: {specific_rasters_to_import}", 'info')
            log_message(f"\tDefault Tags: {default_tags}", 'info')
            log_message(f"\tRepository ID: {repository_id}", 'info')
            log_message(f"\tInstance Type: {instance_type}", 'info')
            log_message(f"\tArcGIS Portal Folder Name: {arcgisPortalFolderName}", 'info')
            log_message(f"\tArcGIS Server Folder Name: {arcgisServerFolderName}", 'info')
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

def remove_file(file_path):
    success = False
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            log_message(f"Removed file: '{file_path}'", 'info')
        success = True
    except Exception as e:
        log_message(f"Failed to remove file '{file_path}': {e}", 'info')
    return success

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

def get_all_json_data():
    global all_json_data, all_json_data_file_path
    if all_json_data == {}:
        if os.path.exists(all_json_data_file_path):
            # load all_json_data from the pre-processed json file
            with open(all_json_data_file_path, 'r') as f:
                all_json_data = json.load(f)
        else:
            # piece together all_json_data from the json files in the input directory
            query_results = {}
            json_query_results_file_path = os.path.join(input_path, 'ENTImageLayers_all.json')
            with open(json_query_results_file_path, 'r') as f:
                query_results_json = json.load(f)
            for query_results_record in query_results_json['results']:
                if 'url' in query_results_record:
                    url = query_results_record.get('url', '')
                    if url != '':
                        # store record in global dictionary with url as key
                        key = url.lower()
                        query_results[key] = query_results_record
                
            json_file_path = os.path.join(input_path, 'ENTEnterprise_all_services_data.json')
            with open(json_file_path, 'r') as f:
                data = json.load(f)
            for record in data['services']:
                key = None
                url = ''
                if 'url' in record:
                    url = record['url'].lower()
                    # remove ?f=pjson from the end of the url
                    if url.endswith('?f=pjson'):
                        url = url[:-8]
                if 'metadata.itemName' in record:
                    # store record in global dictionary with metadata.itemName as key
                    key = record['metadata.itemName'].lower()
                else:
                    # store record in global dictionary with url as key
                    key = url
                if key and key != '':
                    record['org_results'] = query_results.get(url, {})
                    
                    # pull out relevant information from the record
                    # tags, summary, title, description
                    if record['org_results'] != {}:
                        tags = record['org_results'].get('tags', [])
                        record['org_summary'] = record['org_results'].get('snippet', '')
                        record['org_title'] = record['org_results'].get('title', '')
                        record['org_description'] = record['org_results'].get('description', '')
                    else:
                        if 'metadata' in record:
                            if 'dataIdInfo' in record['metadata']:
                                if 'searchKeys' in record['metadata']['dataIdInfo']:
                                    tags = record['metadata']['dataIdInfo']['searchKeys'].get('keyword', [])
                                    record['org_summary'] = record['metadata']['dataIdInfo'].get('idPurp', '')
                                    if 'idCitation' in record['metadata']['dataIdInfo']:
                                        if 'resTitle' in record['metadata']['dataIdInfo']['idCitation']:
                                            if '#text' in record['metadata']['dataIdInfo']['idCitation']['resTitle']:
                                                record['org_title'] = record['metadata']['dataIdInfo']['idCitation']['resTitle']['#text']
                                            else:
                                                record['org_title'] = record['metadata']['dataIdInfo']['idCitation']['resTitle']
                        record['org_description'] = ''
                    if record.get('org_title', '') == '':
                        record['org_title'] = key
                    if record.get('org_summary', '') == '':
                        record['org_summary'] = record['org_title']
                    record['org_tags'] = ','.join(tags)
                    record['org_dataLocation'] = record.get('metadata.linkage', '')
                    record['org_dataFormat'] = record.get('metadata.distFormat', '')
                    record['org_spatialReference'] = record.get('metadata.geogcsn', '')
                    all_json_data[key] = record
            # export all_json_data to a json file
            with open(all_json_data_file_path, 'w') as f:
                json.dump(all_json_data, f, indent=4)
            log_message(f'Exported all_json_data to {all_json_data_file_path}')
    return all_json_data

def find_json_data(dataset):
    return_json = None
    json_data = get_all_json_data()
    if json_data != None:
        lower_dataset = dataset.lower()
        # get the name from the dataset
        lower_name = lower_dataset.split('.')[-1]
        if json_data.get(lower_dataset):
            return_json = json_data[lower_dataset]
        else:
            # look for the name.lower() in the key of the json_data dictionary
            for key in json_data.keys():
                if lower_name in key:
                    return_json = json_data[key]
                    break
    if return_json == None:
        log_message(f"No json data found for {dataset}", 'info')
    return return_json

def get_recycle_time():
    global recycleStartHour, recycleStartMin
    recycleStartMin += 15
    if recycleStartMin > 59:
        recycleStartMin = 0
        recycleStartHour += 1
    if recycleStartHour > 23:
        recycleStartHour = 0
    return str(recycleStartHour).zfill(2) + ":" + str(recycleStartMin).zfill(2)

def get_parent_element(doc, parentPath):
    parent_element = None
    if parentPath == []:
        return None
    for tag in parentPath:
        if parent_element is None:
            elements = doc.getElementsByTagName(tag)
        else:
            elements = parent_element.getElementsByTagName(tag)
        if elements:
            parent_element = elements[0]
        else:
            return None
    return parent_element

def add_element_under_nested_parent(doc, elementTagName, value='', nestedParentPath=[], attribute={}):
    if elementTagName == '':
        return
    parent_element = None
    search_elements = []
    if nestedParentPath == []:
        search_elements = doc.getElementsByTagName(elementTagName)
    else:
        parent_element = get_parent_element(doc, nestedParentPath)
        if parent_element:
            search_elements = parent_element.getElementsByTagName(elementTagName)
    element = None
    if search_elements:
        # setup to update the existing element
        element = search_elements[0]
    else:
        # create a new element
        element = doc.createElement(elementTagName)
    if element:
        if value != '':
            if element.firstChild:
                element.firstChild.nodeValue = value
            else:
                element_text = doc.createTextNode(value)
                element.appendChild(element_text)
        # set attributes if any
        for attr_name, attr_value in attribute.items():
            element.setAttribute(attr_name, attr_value)
    if parent_element:
        parent_element.appendChild(element)

def add_key_value_element_under_nested_parent(doc, elementTagName, key, value, nestedParentPath=[], elementAttributes={}, keyAttributes={}):
    if elementTagName == '' or key == '' or value == '' or nestedParentPath == []:
        return
    parent_element = get_parent_element(doc, nestedParentPath)
    if parent_element:
        new_element = doc.createElement(elementTagName)
        for attr_name, attr_value in elementAttributes.items():
            new_element.setAttribute(attr_name, attr_value)
        new_key = doc.createElement('Key')
        new_key_text = doc.createTextNode(key)
        new_key.appendChild(new_key_text)
        new_element.appendChild(new_key)
        new_value = doc.createElement('Value')
        for attr_name, attr_value in keyAttributes.items():
            new_value.setAttribute(attr_name, attr_value)
        new_value_text = doc.createTextNode(value)
        new_value.appendChild(new_value_text)
        new_element.appendChild(new_value)
        parent_element.appendChild(new_element)

def add_databases_to_sddraft_dom(doc, connectionString, datasetOnPremisePath):
    dataset_name = datasetOnPremisePath.split('.')[-1]
    
    # prompt for DB Name for Server Manger e.g. sde.DEFAULT (ORG-APP1),  dbo.DEFAULT (ORG-APP1), GenericProj1_Datastore.gdb
    
    databases_xml = f'''
    <Databases xsi:type='typens:ArrayOfSVCDatabase' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xs='http://www.w3.org/2001/XMLSchema' xmlns:typens='http://www.esri.com/schemas/ArcGIS/3.2.0'>
        <SVCDatabase xsi:type='typens:SVCDatabase'>
            <ID/>
            <Name>{server_manager_db_name}</Name>
            <OnPremisePath/>
            <ServerPath/>
            <InPackagePath/>
            <OnPremiseWorkspaceFactoryProgID>{workspace_factory}</OnPremiseWorkspaceFactoryProgID>
            <OnPremiseConnectionString>{connectionString}</OnPremiseConnectionString>
            <InPackageWorkspaceFactoryProgID/>
            <Datasets xsi:type='typens:ArrayOfSVCDataset'>
                <SVCDataset xsi:type='typens:SVCDataset'>
                    <ID/>
                    <Name>{dataset_name}</Name>
                    <OnPremisePath>{datasetOnPremisePath}</OnPremisePath>
                    <ServerPath/>
                    <InPackagePath/>
                    <OnServerName>{dataset_name}</OnServerName>
                    <DatasetType>esriDTRasterDataset</DatasetType>
                </SVCDataset>
            </Datasets>
            <Replicas xsi:type='typens:ArrayOfSVCReplica'/>
            <SwizzledOnClient>false</SwizzledOnClient>
            <ByReference>true</ByReference>
            <OnServerWorkspaceFactoryProgID>{workspace_factory}</OnServerWorkspaceFactoryProgID>
            <OnServerConnectionString>{connectionString}</OnServerConnectionString>
            <OnServerName>{server_manager_db_name}</OnServerName>
        </SVCDatabase>
    </Databases>
    '''
    log_message(f'server_manager_db_name: {server_manager_db_name}', 'info')
    log_message(f'workspace_factory: {workspace_factory}', 'info')
    log_message(f'dataset_name: {dataset_name}', 'info')
    log_message(f'datasetOnPremisePath: {datasetOnPremisePath}', 'info')
    log_message(f'connectionString: {connectionString}', 'info')
    log_message(f"databases_xml: {databases_xml}", 'info')
    
    databases_node = DOM.parseString(databases_xml).documentElement
    # Remove temporary namespace declarations after parsing
    databases_node.removeAttribute('xmlns:xsi')
    databases_node.removeAttribute('xmlns:xs')
    databases_node.removeAttribute('xmlns:typens')
    
    # replace <Databases xsi:type='typens:ArrayOfSVCDatabase'/> with databases_xml
    databases_elements = doc.getElementsByTagName('Databases')
    if databases_elements:
        databases_element = databases_elements[0]
        parent_node = databases_element.parentNode
        parent_node.replaceChild(databases_node, databases_element)
    else:
        # add new Databases element
        doc.documentElement.appendChild(databases_node)
        
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

def update_sddraft_dom(sd_file_path, raster_name, title, description, credits='', is_shared_instance=True, repository_id='0'):
    # Specifics of ESRI sddraft files:
    #   - StagingSettings.PropertyArray.PropertySetProperty.Key = 'PortalFolderName'    => Value = # Name of the folder in the portal where the service will be published
    #   - Configurations.SVCConfiguration.ServiceFolder = # Name of the folder in the server where the service will be published
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'recycleInterval'   => Value = # Time in minutes between recycling the service
    #   FOR SHARED INSTANCES
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MinInstances'       => Value = 0
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MaxInstances'       => Value = 0
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'provider'           => Value = 'ArcObjectsRasterRendering'
    #   FOR DEDICATED INSTANCES
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MinInstances'       => Value = # Minimum number of instances of the service
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MaxInstances'       => Value = # Maximum number of instances of the service
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'provider'           => Value = 'ArcObjects11'
    
    log_message(f"Updating sddraft DOM", 'info')

    # Read the contents of the draft into an xml parser
    doc = DOM.parse(sd_file_path)
    # print(doc.toprettyxml())
    
    # Replace unsupported character with a space in title and description
    title = remove_non_ascii(title)
    description = remove_non_ascii(description)
    credits = remove_non_ascii(credits)
        
    # Update the feature specific information
    add_element_under_nested_parent(doc, 'Name', raster_name, ['ItemInfo'])
    add_element_under_nested_parent(doc, 'Title', title, ['ItemInfo'])
    add_element_under_nested_parent(doc, 'Description', description, ['ItemInfo'])
    add_element_under_nested_parent(doc, 'Credits', credits, ['ItemInfo'])

    # Locate the ItemInfo element
    item_info_elements = doc.getElementsByTagName('ItemInfo')
    if item_info_elements:
        item_info = item_info_elements[0]
        # print(item_info.toprettyxml())
        
        # Replace underscore with space in all String elements within the Tags element
        elements = item_info.getElementsByTagName('Tags')
        if elements:
            for element in elements:
                string_elements = element.getElementsByTagName('String')
                for string_element in string_elements:
                    if string_element.firstChild:
                        if string_element.firstChild.nodeValue != 'ENT_Enterprise':
                            string_element.firstChild.nodeValue = string_element.firstChild.nodeValue.replace("_", " ")
                
    recycleInterval = '264'
    
    found_IncludeDataInSDFile = False
    found_PortalFolderName = False
    found_AllowCopy = False
    found_Provider = False
    found_ServiceTitle = False
    connectionString = ''

    if is_shared_instance:
        provider_value = 'ArcObjectsRasterRendering'
        min_instances = '0'
        max_instances = '0'
    else:
        provider_value = 'ArcObjects11'
        min_instances = '1'
        max_instances = '2'
    
    # Locate the PropertySetProperty elements
    property_set_properties = doc.getElementsByTagName('PropertySetProperty')
    for property_set_property in property_set_properties:
        key_elements = property_set_property.getElementsByTagName('Key')
        if key_elements and key_elements[0].firstChild:
            key = key_elements[0].firstChild.nodeValue
            if key in ['MaxImageWidth', 'MaxImageHeight']:
                # Update the value
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements and value_elements[0].firstChild:
                    current_value = int(value_elements[0].firstChild.nodeValue)
                    new_value = current_value * 10  # Add one extra 0
                    # print(f'Updating {key} from {current_value} to {new_value}')
                    value_elements[0].firstChild.nodeValue = str(new_value)
            elif key == 'recycleInterval':
                # set the recycleInterval property
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = recycleInterval
                    else:
                        text_node = doc.createTextNode(recycleInterval)
                        value_elements[0].appendChild(text_node)
            elif key == 'recycleStartTime':
                # get recycleStartTime as 15 minutes after the current recycleStartTime
                recycleStartTime = get_recycle_time()
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = recycleStartTime
                    else:
                        text_node = doc.createTextNode(recycleStartTime)
                        value_elements[0].appendChild(text_node)
            elif key == 'CallingContext':
                # set the property value to 0
                value = '0'
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
            elif key == 'minInstances':
                value = min_instances
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
            elif key == 'maxInstances':
                value = max_instances
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
            elif key == 'ServerConnectionString':
                # Update ServerConnectionString to
                #   - remove /services and 
                #   - replace esriAGSConnectionModeConsumer with esriAGSConnectionModePublisher
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        current_value = value_elements[0].firstChild.nodeValue
                        # replace esriAGSConnectionModeConsumer with esriAGSConnectionModePublisher in current_value to get value
                        value = current_value.replace('esriAGSConnectionModeConsumer', 'esriAGSConnectionModePublisher')
                        value = value.replace('/services', '')
                        value_elements[0].firstChild.nodeValue = value
            elif key == 'IncludeDataInSDFile':
                found_IncludeDataInSDFile = True
            elif key == 'PortalFolderName':
                found_PortalFolderName = True
            elif key == 'AllowCopy':
                found_AllowCopy = True
                # set the property value to false
                value = 'false'
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
            elif key == 'Provider':
                found_Provider = True
                value = provider_value
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
            elif key == 'ConnectionString':
                # get the value and store it in connectionString variable
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        connectionString = value_elements[0].firstChild.nodeValue
            elif key == 'ServiceTitle':
                found_ServiceTitle = True
                value = title
                value_elements = property_set_property.getElementsByTagName('Value')
                if value_elements:
                    if value_elements[0].firstChild:
                        value_elements[0].firstChild.nodeValue = value
                    else:
                        text_node = doc.createTextNode(value)
                        value_elements[0].appendChild(text_node)
    if (not found_IncludeDataInSDFile):
        add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'IncludeDataInSDFile', 'false', ['ConfigurationProperties', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:boolean'})
    if (not found_PortalFolderName) and arcgisPortalFolderName != '':
        add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'PortalFolderName', arcgisPortalFolderName, ['StagingSettings', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
    if (not found_AllowCopy):
        add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'AllowCopy', 'false', ['ConfigurationProperties', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:boolean'})
    if (not found_Provider):
        add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'Provider', provider_value, ['Props', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
    if (not found_ServiceTitle):
        add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'ServiceTitle', title, ['StagingSettings', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
    
    # Update the RecyclingInterval
    add_element_under_nested_parent(doc, 'RecyclingInterval', recycleInterval, ['Configurations', 'SVCConfiguration', 'Definition'])
    
    if arcgisServerFolderName != '':
        # Update ServiceFolder to user specified arcgisServerFolderName.
        add_element_under_nested_parent(doc, 'ServiceFolder', arcgisServerFolderName, ['Configurations', 'SVCConfiguration'])
        
    add_element_under_nested_parent(doc, 'RepositoryID', repository_id, ['Resources','SVCResource'])
    
    if workspace_type == 'FILEGDB':
        connectionString = 'DATABASE=' + arcpy.env.workspace

    if connectionString != '':
        resources_elements = doc.getElementsByTagName('Resources')
        if resources_elements:
            resources_onPremisePath_elements = resources_elements[0].getElementsByTagName('OnPremisePath')
            if resources_onPremisePath_elements:
                if resources_onPremisePath_elements[0].firstChild:
                    resources_onPremisePath = resources_onPremisePath_elements[0].firstChild.nodeValue
                    add_databases_to_sddraft_dom(doc, connectionString, resources_onPremisePath)
    
    if backup_sddraft_files:
        # save current sd_file_path to a backup file
        backup_sd_file_path = sd_file_path.replace('.sddraft', '_backup.sddraft')
        try:
            shutil.copyfile(sd_file_path, backup_sd_file_path)
            log_message(f"Backup saved to {backup_sd_file_path}")
        except Exception as e:
            log_message(f"Failed to backup {sd_file_path} to {backup_sd_file_path}: {e}", 'info')
    
    # Write the changes back to the sddraft
    with open(sd_file_path, 'w') as f:
        doc.writexml(f)
    
    # analysis = arcpy.mapping.AnalyzeForSD(sd_file_path)
    # if analysis['errors'] != {}:
    #    log_message('AnalyzeForSD Errors', 'error', analysis['errors'])
    #    return False
    return True

def set_arcpy_environment():
    global workspace_type, workspace_factory, server_manager_db_name, workspace_full_path
    env_set = True
    
    # prompt for DB Name for Server Manger e.g. sde.DEFAULT (ORG-APP1),  dbo.DEFAULT (ORG-APP1), GenericProj1_Datastore.gdb
    
    # Ask the user if they are utlizing a FileGDB or SDE
    workspace_type = get_user_input("Workspace type (FileGDB or SDE)", default_value='SDE', value_to_check=workspace_type)
    workspace_type = workspace_type.upper()
    if workspace_type not in ['FILEGDB', 'SDE']:
        log_message(f"Invalid workspace type {workspace_type}. Exiting...", 'error')
        env_set = False
    else:
        if workspace_type == 'FILEGDB':
            example_workspace_path = r"\\org-app2\D$\GenericArcGISDataDir\GIS\Example\GenericProj2\GenericProj1\GenericProj1_Datastore.gdb"
            workspace_factory = 'esriDataSourcesGDB.FileGDBWorkspaceFactory'
            # prompt for DB Name for Server Manger e.g. sde.DEFAULT (ORG-APP1),  dbo.DEFAULT (ORG-APP1), GenericProj1_Datastore.gdb
            example_server_manager_db_name = 'GenericProj1_Datastore.gdb'
        else:
            example_workspace_path = r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde"
            workspace_factory = 'esriDataSourcesGDB.SdeWorkspaceFactory'
            example_server_manager_db_name = 'sde.DEFAULT (ORG-APP1)'
        
        workspace_full_path = get_user_input("Full path to the workspace", default_value=example_workspace_path, value_to_check=workspace_full_path)
        if workspace_full_path == "":
            log_message("No workspace path provided. Exiting...", 'error')
            env_set = False
        elif not os.path.exists(workspace_full_path):
            log_message(f"Database connection file {workspace_full_path} does not exist. Exiting...", 'error')
            env_set = False
        
        if server_manager_db_name == '':
            print('NOTE: The name for the database in Server Manager displays on the Reference tab in the service.')
            server_manager_db_name = get_user_input("Name for the database in ArcGIS Server Manager", default_value=example_server_manager_db_name, value_to_check=server_manager_db_name)
    
    if env_set:
        try:
            # Set the workspace to your enterprise geodatabase connection
            arcpy.env.workspace = workspace_full_path
            log_message(f"Workspace set to {workspace_full_path}")
        except Exception as e:
            log_message(f"Failed to set the workspace to {workspace_full_path}: {e}", 'error')
            env_set = False
    
    return env_set

def connect_to_portal():
    global portal_url, gis, portal_username
    connected = False
    
    # Get portal URL from the user or default to 'https://gis.example.com/arcgisportal'
    portal_url = get_user_input("ArcGIS portal URL", default_value='https://gis.example.com/arcgisportal', value_to_check=portal_url)
    
    # Get portal_username and password from the user
    portal_username = get_user_input("ArcGIS Portal Username (not SSO)", default_value='gisadmin', value_to_check=portal_username)
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

def format_raster_name(raster_name):
    if workspace_type == 'FILEGDB':
        return raster_name
    
    global database_name, database_owner_name
    raster_dataset = ''
    period_count = raster_name.count('.')
    if period_count >= 2:
        # assume the raster name is fully qualified
        raster_dataset = raster_name
    else:
        if database_name == '':
            # get the database name from the user
            database_name = get_user_input("Name of the database", default_value='ORG_WS', value_to_check=database_name)
            if database_name == "":
                log_message("Missing database name.", 'error')
                return raster_dataset
        if period_count == 1:
            # assume schema name is included in the raster name
            raster_dataset = f"{database_name}.{raster_name}"
        else:
            if database_owner_name == "":
                # get the schema name from the user
                database_owner_name = get_user_input("Name of the database user", default_value='sde', value_to_check=database_owner_name)
                if database_owner_name == "":
                    log_message("Missing schema name.", 'error')
                    return raster_dataset
            raster_dataset = f"{database_name}.{database_owner_name}.{raster_name}"
    return raster_dataset

def get_raster_datasets():
    global raster_import_df, csv_import_file_path, specific_rasters_to_import
    raster_datasets = []
    
    if csv_import_file_path != '':
        # check if import file path initialized from env file
        import_file = 'Y'
    else:
        # check if script executed with an import file as the first argument
        if len(sys.argv) > 1:
            csv_import_file_path = sys.argv[1]
            # if right of the last period is csv, then it is an import file
            if csv_import_file_path.split('.')[-1].lower() == 'csv':
                import_file = 'Y'
                log_message(f"Import file provided as argument: {csv_import_file_path}", 'info')
            else:
                log_message(f"Invalid import file provided as argument: {csv_import_file_path}. Prompting user for file.", 'info')
                csv_import_file_path = ''
        if csv_import_file_path == '':
            import_file = get_user_input("Import from a csv file (Y/N)?", default_value='Y')
    if import_file.upper() == 'Y':
        if csv_import_file_path == '':
            print('\t*** CSV columns names: raster_name,title,summary,description,tags,credits,instance,portal_groups,categories')
            print("\t*** Optional columns: instance,portal_groups,categories")
            print("\t*** 'instance' may contain 'shared' or 'dedicated' or nothing. Nothing will default to 'shared'.")
            # get the csv file path from the user
            csv_import_file_path = get_user_input("Full path to the import file")
            if csv_import_file_path == "":
                log_message("No import file provided. Exiting...", 'error')
                return raster_datasets
        if not os.path.exists(csv_import_file_path):
            log_message(f"Import file {csv_import_file_path} does not exist. Exiting...", 'error')
            return raster_datasets
        if csv_import_file_path.split('.')[-1].lower() != 'csv':
            log_message(f"Invalid CSV file provided: {csv_import_file_path}. Exiting...", 'error')
            return raster_datasets
        try:
            raster_import_df = pd.read_csv(csv_import_file_path, encoding=get_file_encoding(csv_import_file_path))
            # set raster_datasets to the raster_name values in the import_df
            raster_datasets = raster_import_df['raster_name'].tolist()
        except Exception as e:
            log_message(f"Failed to read the import file {csv_import_file_path}: {e}", 'error')
    else:
        # get raster database information from the user
        specific_rasters_to_import = get_user_input("Name of the raster dataset(s) separated by commas", value_to_check=specific_rasters_to_import)
        if specific_rasters_to_import == "":
            print('\t*** Workspace:', arcpy.env.workspace)
            publish_all = get_user_input("Publish all raster datasets from the workspace (Y/N)?", default_value='N')
            if publish_all.upper() == 'Y':
                # determine all raster datasets in the geodatabase specified by workspace_full_path
                log_message('Gathering all rasters known to the geodatabase...')
                try:
                    raster_datasets = arcpy.ListRasters()
                    # print length of raster_datasets
                    log_message(f"Found {len(raster_datasets)} raster datasets in the workspace", 'info')
                    if limit_to_first_n_datasets > 0:
                        raster_datasets = raster_datasets[:limit_to_first_n_datasets]
                except Exception as e:
                    log_message(f"Failed to get the raster datasets: {e}", 'error')
        else:
            if ',' in specific_rasters_to_import:
                for raster in specific_rasters_to_import.split(','):
                    raster_datasets.append(format_raster_name(raster.strip()))
            else:
                raster_datasets = [format_raster_name(specific_rasters_to_import)]
    return raster_datasets

def stage_service(sddraft_filepath, sd_filepath):
    if os.path.exists(sd_filepath):
        log_message(f"Service definition file exists: {sd_filepath}. Skipping staging...", 'info')
        return True
    log_message("Start Staging")
    service_staged = False
    stage_service = True
    while stage_service and not service_staged:
        try:
            arcpy.StageService_server(sddraft_filepath, sd_filepath)
            warnings = arcpy.GetMessages(1)
            errors = arcpy.GetMessages(2)
            log_message(warnings, 'info')
            log_message(errors, 'error')
            if errors != '' or errors:
                return service_staged
            # If data store is not registered
            if "24011" in warnings:
                # # Register data store
                # register_res = register_datastore_item(portal_url, portal_username, portal_password, sde_conn_file, data_store_name, federated_server_url)
                # if not register_res:
                log_message("Unable to register the data store with portal. Stopping all publishing!", 'error')
                exit()
                # # Stage the service again
                # stage_service = True
                stage_service = False
            else:
                stage_service = False
            if warnings == '':
                if os.path.exists(sd_filepath):
                    service_staged = True
        except arcpy.ExecuteError:
            log_message(arcpy.GetMessages(2), 'error')
            return service_staged
        except Exception as e:
            log_message(f"Failed to stage service: {e}", 'error')
            return service_staged
    return service_staged

def validate_and_update_portal_item(current_title, new_title, portal_group_names='', categories=''):
    global portal_group_dict
    log_message(f"Validating and updating portal item for {current_title} to {new_title}", 'info')
    item_id = ''
    try:
        qry = 'title:"' + current_title + '"' + ' OR title:"' + new_title + '"'
        gis_items = gis.content.search(query=qry, max_items=10, sort_field='modified', sort_order='desc')
        if gis_items or (not gis_items is None):
            # get the first result
            gis_item = gis_items[0]
            item_id = gis_item.get('id', '')
            if item_id != '':
                try:
                    item_title = gis_item.get('title', '')
                    log_message(f"Found portal item {item_id} with title '{item_title}'", 'info')
                    if new_title != current_title:
                        if item_title == '' or item_title == current_title:
                            gis_item.update({'title': new_title})
                            log_message(f"\tUpdated item title to '{new_title}'", 'info')
                except Exception as e:
                    log_message(f"Failed to update item title: {e}", 'error')
                    
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
                try:
                    if categories != '':
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
                            gis_item.update(item_properties={"categories": category_list})
                            log_message(f"\tUpdated item categories to {category_list}", 'info')
                except Exception as e:
                    log_message(f"Failed to update item categories: {e}", 'error')
                
                try:
                    if portal_group_names != '':
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
    except Exception as e:
        log_message(f"Failed to update item '{new_title}' ({item_id}): {e}", 'error')
    if item_id != '':
        log_message(f"Validated portal item '{new_title}' ({item_id})")
    return item_id


# Begin Main

init_logging()

init_global_variables()

repository_id_error = False
if repository_id == '':
    repository_id_known = get_user_input("Do you know the repository ID (Y/N)?", default_value='Y')
    if repository_id_known.upper() == 'Y':
        repository_id = get_user_input("Repository ID", default_value='0')
    else:
        use_default_repository_id = get_user_input("Would you like to use '0' as the repository ID (Y/N)?", default_value='N')
        if use_default_repository_id.upper() == 'Y':
            repository_id = '0'
        else:
            repository_id_error = True
if repository_id != '':
    repository_id_error = False
    try:
        repository_id_int = int(repository_id)
        if repository_id_int < 0:
            repository_id_error = True
    except:
        repository_id_error = True
if repository_id_error:
    log_message('\t*** Find the RepositoryID in the manifest.xml of a service manually published to Portal from Pro for the same connection. See \\org-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput.')
    get_user_input('Press enter to quit...')
    if repository_id == '':
        log_message('\t*** RepositoryID is required.', 'error')
    else:
        log_message("\t*** Invalid repository ID '{repository_id}'", 'error')
    exit()
    
env_set = set_arcpy_environment()
if not env_set:
    exit()

if stageService:
    # prompt to use https://gis.example.com/arcgisserver as the federated_server_url or input a different url
    federated_server_url = get_user_input("Federated server URL", default_value='https://gis.example.com/arcgisserver', value_to_check=federated_server_url)
    connected_to_portal = connect_to_portal()
    if not connected_to_portal:
        exit()

raster_datasets = get_raster_datasets()
if raster_datasets == []:
    log_message("No raster datasets found. Exiting...", 'error')
    exit()

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
arcgisPortalFolderName = get_user_input("ArcGIS Portal folder name, e.g. 'ENT_Enterprise' (or press enter to publish to root)", value_to_check=arcgisPortalFolderName)
arcgisServerFolderName = get_user_input("ArcGIS Server folder name, e.g. 'ENT_Enterprise' (or press enter to publish to root)", value_to_check=arcgisServerFolderName)

default_empty_tags = "raster"
default_tags = get_user_input("Tags to be appended to all rasters in this import, e.g. 'raster' (or press enter for none)", value_to_check=default_tags)
if default_tags != "":
    default_empty_tags = default_tags
    
if raster_import_df.empty:
    # JSON data to import will come from the ENTEnterprise_all_json_data.json file within the Input directory
    # set the input_path to the Input directory within the script's directory
    input_path = current_dir
    # Create the Input directory if it does not exist
    if os.path.exists(os.path.join(current_dir, 'Input')):
        input_path = os.path.join(current_dir, 'Input')
    all_json_data_file_path = os.path.join(input_path, 'ENTEnterprise_all_json_data.json')

# cycle through all raster datasets in raster_datasets
len_raster_datasets = len(raster_datasets)
log_message(f"Processing {len_raster_datasets} raster datasets")
for raster_dataset in raster_datasets:
    log_message(f"****************************************************", 'info', message_details=None, reset_log_hist=True)
    
    raster_dataset = str(raster_dataset)
    
    # Output locations for the service definition draft and final .sd file
    sddraft_output_filepath = os.path.join(output_path, f"{raster_dataset}.sddraft")
    sd_output_filepath = sddraft_output_filepath.replace('.sddraft', '.sd')
    log_message(sddraft_output_filepath, 'info')
    log_message(sd_output_filepath, 'info')
    
    tags = ''
    summary = ''
    title = ''
    description = ''
    credits = ''
    raster_is_shared_instance = is_shared_instance
    portal_groups = ''
    categories = ''
    spatialReference = ''
    data_found = False
    raster_name = raster_dataset.split(".")[-1]
    
    if raster_import_df.empty:
        raster_dataset_DBpath = raster_dataset
        raster_dataset_json = find_json_data(raster_dataset)
        if raster_dataset_json:
            data_found = True
            raster_name = raster_dataset_json.get('name', raster_name)
            title = raster_dataset_json.get('org_title', '')
            summary = raster_dataset_json.get('org_summary', '')
            description = raster_dataset_json.get('org_description', '')
            tags = raster_dataset_json.get('org_tags', '')
            spatialReference = raster_dataset_json.get('org_spatialReference', '')
        else:
            log_message('Summary set to raster name', 'info')
            summary = raster_name
    else:
        # get data from the import file
        data_found = True
        raster_dataset_DBpath = format_raster_name(raster_name)
        raster_dataset_row = raster_import_df.loc[raster_import_df['raster_name'] == raster_name]
        title = raster_dataset_row['title'].values[0]
        summary = raster_dataset_row['summary'].values[0]
        description = raster_dataset_row['description'].values[0]
        tags = raster_dataset_row['tags'].values[0]
        credits = raster_dataset_row['credits'].values[0]
        if 'instance' in raster_dataset_row:
            instance = raster_dataset_row['instance'].values[0].lower()
            if instance == 'dedicated':
                raster_is_shared_instance = False
        if 'portal_groups' in raster_dataset_row:
            portal_groups = raster_dataset_row['portal_groups'].values[0]
        if 'categories' in raster_dataset_row:
            categories = raster_dataset_row['categories'].values[0]
    
    if not data_found:
        if len_raster_datasets < 10:
            log_message("Prompt user for missing data", 'info')
            print(f'Enter the following information for {raster_name}:')
            title = get_user_input("Title", default_value=raster_name)
            summary = get_user_input("Summary", default_value=title)
            description = get_user_input("Description", default_value=summary)
            tags = get_user_input("Tags", default_value=default_empty_tags)
        else:
            log_message(f"\tERROR: No json data found for {raster_name}", 'error')
            continue
    
    title = remove_non_ascii(title)
    summary = remove_non_ascii(summary)
    description = remove_non_ascii(description)
    credits = remove_non_ascii(credits)
    tags = remove_non_ascii(tags)
    if spatialReference != '':
        if spatialReference == 'GCS_WGS_1984':
            spatialReference = 'WGS84,wkid4326'
        if tags == "" or tags is None:
            tags = spatialReference
        else:
            tags = tags + ',' + spatialReference
    elif tags == "" or tags is None:
        log_message(f"Empty Tags set to '{default_empty_tags}'", 'info')
        tags = default_empty_tags
    else:
        if default_tags != "":
            tags += ',' + default_tags
    
    log_message(f"Raster: {raster_dataset_DBpath}", 'info')
    log_message(f"\tImageSDDraft: {sddraft_output_filepath}", 'info')
    log_message(f"\tRaster Name: {raster_name}", 'info')
    log_message(f"\tTitle: {title}", 'info')
    log_message(f"\tSummary: {summary}", 'info')
    log_message(f"\tDescription: {description}", 'info')
    log_message(f"\tTags: {tags}", 'info')
    log_message(f"\tIs Shared Instance: {raster_is_shared_instance}", 'info')
    
    if title == "" or summary == "" or description == "" or title is None or summary is None or description is None:
        if title == "" or title is None:
            title = raster_name
        if summary == "" or summary is None:
            summary = title
        if description == "" or description is None:
            description = summary
        if title == "" or summary == "" or description == "" or title is None or summary is None or description is None:
            log_message(f"\tMissing title, summary or description.", 'error')
            continue
    
    errors = {}
    warnings = {}
    messages = {}
    total_warnings = 0
    if os.path.exists(sddraft_output_filepath):
        log_message(f"Using existing Image Service Draft")
    else:
        sddraft_result = {}
        try:
            # ensure the raster_name does not have any spaces
            raster_name = raster_name.replace(" ", "_")
            tags = tags.replace(" ", "_")
            # append database name and schema name to raster_name to get raster_dataset_path
            raster_dataset_path = os.path.join(arcpy.env.workspace, raster_dataset_DBpath)
            if not arcpy.Exists(raster_dataset_path):
                log_message(f"Raster dataset {raster_dataset_path} does not exist. Skipping...", 'error')
                continue
            else:
                log_message(f"Creating Image Service Draft for {raster_name}", 'info')
                # Create an Image Service Draft
                '''
                sddraft_result = arcpy.CreateImageSDDraft(raster_or_mosaic_layer=raster_dataset_path, 
                                                    out_sddraft=sddraft_output_filepath, 
                                                    service_name=raster_name, 
                                                    server_type="FEDERATED_SERVER",
                                                    connection_file_path=server_connection_file_path,
                                                    copy_data_to_server=False, 
                                                    summary=summary, 
                                                    tags=tags)
                '''
                sddraft_result = arcpy.CreateImageSDDraft(raster_or_mosaic_layer=raster_dataset_path, 
                                                    out_sddraft=sddraft_output_filepath, 
                                                    service_name=raster_name, 
                                                    server_type="ARCGIS_SERVER",
                                                    connection_file_path=None,
                                                    copy_data_to_server=False, 
                                                    summary=summary, 
                                                    tags=tags)
        except Exception as e:
            errors = {f"Failed to create Image Service Draft for {raster_name}": str(e)}
            log_message(f"Failed to create Image Service Draft: {e}", 'error')
        
        total_warnings = 0
        build_pyramids = False
        calculate_statistics = False
        
        if (sddraft_result and sddraft_result != {}) or errors != {}:
            log_message('CreateImageSDDraft Errors, Warnings, and Messages', 'info')
            
            if errors != {}:
                # append errors from sddraft_result to errors
                errors.update(sddraft_result.get('errors', {}))
            else:
                errors = sddraft_result.get('errors', {})
            messages = sddraft_result.get('messages', {})
            warnings = sddraft_result.get('warnings', {})
            
            if messages != {}:
                log_message("Messages:", 'info', messages)
                
            if warnings == {}:
                total_warnings = 0
            else:
                log_message("WARNINGS:", 'info', warnings)
                total_warnings = len(warnings)
                if any(code == 10029 for (message, code), details in warnings.items()):
                    build_pyramids = True
                    # log_message("+++++++++++++++ Build Pyramids", 'info')
                if any(code == 10010 for (message, code), details in warnings.items()):
                    calculate_statistics = True
                    # log_message("+++++++++++++++ Calculate Statistics", 'info')
            
            if errors != {}:
                log_message("ERRORS:", 'error', errors)
                continue
        else:
            log_message(f"Created Image Service Draft for {raster_name}")
            
        if build_pyramids:
            log_message('Building pyramids', 'info')
            try:
                # Build pyramids with specific parameters
                arcpy.management.BuildPyramids(in_raster_dataset=raster_dataset_path,
                                                pyramid_level="-1",
                                                SKIP_FIRST="NONE",
                                                resample_technique="BILINEAR",
                                                compression_type="DEFAULT",
                                                compression_quality=75,
                                                skip_existing="SKIP_EXISTING")
                log_message(f"Pyramids built for {raster_name}", message_details=arcpy.GetMessages())
                total_warnings = total_warnings - 1
            except arcpy.ExecuteError:
                log_message(arcpy.GetMessages(2), 'error')
            except Exception as e:
                log_message(f"Failed to build pyramids: {e}", 'error')
            
        if calculate_statistics:
            log_message('Calculating Statistics', 'info')
            try:
                arcpy.management.CalculateStatistics(raster_dataset_path)
                log_message(f"Statistics Calculated for {raster_name}", message_details=arcpy.GetMessages())
                total_warnings = total_warnings - 1
            except arcpy.ExecuteError:
                log_message(arcpy.GetMessages(2), 'error')
            except Exception as e:
                log_message(f"Failed to Calculate Statistics: {e}", 'error')
    
    if os.path.exists(sddraft_output_filepath):
        if not update_sddraft_dom(sddraft_output_filepath, raster_name, title, description, credits, is_shared_instance=raster_is_shared_instance, repository_id=repository_id):
            continue
    else:
        errors = {f"Failed to create Image Service Draft for {raster_name}": "No sddraft file found"}
        log_message(f"Failed to create Image Service Draft for {raster_name}", 'error')
        continue
    
    if stageService:
        if (errors == {}) and (total_warnings == 0):
            if backup_sddraft_files:
                # backup sddraft_output_filepath
                backup_sddraft_output_filepath = sddraft_output_filepath.replace('.sddraft', '_backup_2.sddraft')
                try:
                    shutil.copyfile(sddraft_output_filepath, backup_sddraft_output_filepath)
                    log_message(f"Backup saved to {backup_sddraft_output_filepath}")
                except Exception as e:
                    log_message(f"Failed to backup {sddraft_output_filepath} to {backup_sddraft_output_filepath}: {e}", 'info')
            
            uploaded = False
            # Stage and upload the service
            service_staged = stage_service(sddraft_output_filepath, sd_output_filepath)
            if service_staged:
                if uploadToServer:
                    try:
                        log_message("Start Publishing Image Service", 'info')
                        arcpy.UploadServiceDefinition_server(sd_output_filepath, federated_server_url)
                        log_message(f"Finished Publishing Image Service for {raster_name}")
                        uploaded = True
                    except Exception as e:
                        log_message(f"Failed to upload service: {e}", 'error')
                    
                    if uploaded == True:
                        validate_and_update_portal_item(raster_name, title, portal_groups, categories)
                        if remove_sddraft_files:
                            remove_file(sddraft_output_filepath)
                        
                    if remove_sd_files:
                        remove_file(sd_output_filepath)
                else:
                    log_message(f"Service Definition file created: {sd_output_filepath}")
    else:
        log_message(f"Service Definition file created: {sd_output_filepath}")

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
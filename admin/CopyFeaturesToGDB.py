
# CopyFeaturesToGDB.py
#
# Developed by: Julie Tripp
#               julie.tripp@rrgnbs.com
# Date:  04/04/2025
#
# Description: This script copies features from ArcGIS Feature Services to a local SDE geodatabase.
#
# CSV file format:
# feature_service_url,database_owner_name,feature_name,workspace_full_path
# Example CSV file:
# https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/0,SDE,Cacao_Impact_Gradient_2050s,T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde
#
# Script execution options:
# 1. Run the script from the command line with the following command:
#    python CopyFeaturesToGDB.py
# 2. Run the script from the command line with the following command, providing the csv import file as an argument:
#    python CopyFeaturesToGDB.py "C:\path\to\import.csv"
#
import arcpy
import os
import logging
from datetime import datetime
import getpass
import sys
import chardet
import pandas as pd
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection
import traceback
import requests
import json
import math
import csv

# from copyFeaturesFromService import copyData

gis = None

# workspace_full_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde"
workspace_full_path = ''

workspace_paths = {
    'W': r"T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde",
    'M': r"T:\ArcGISDataset\Enterprise\Connections\NBS_MaxEnt_sde.sde",
    'B': r"T:\ArcGISDataset\Enterprise\Connections\NBS_WaterBalance_sde.sde",
    'G': r"T:\ArcGISDataset\Enterprise\Connections\NBS_Gen_Ref_sde.sde",
    'C': r"T:\ArcGISDataset\Enterprise\Connections\NBS_ClimateSimilarity_sde.sde"
}

'''
failed:
    ("https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services/RioOsoParcels/FeatureServer/0", "SDE.CA_Sutter_Yuba_County"),
    ("https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services/RioOsoParcels/FeatureServer/1", "SDE.CA_Yuba_County"),
    ("https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services/RioOsoParcels/FeatureServer/2", "SDE.CA_Sutter_County"),
    ("https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services/Kern_Parcels_GT90_Acres/FeatureServer/0", "SDE.Kern_Parcels_GT90_Acres"),
'''
# add urls and db table name to a list
features_list = [
    ("https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/0", "SDE.Cacao_Impact_Gradient_2050s", None),
    ("https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/1", "SDE.Cacao_Impact_Gradient_2030s", None),
    ("https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/2", "SDE.Cacao_Agroclimatic_Zones_2050s", None),
    ("https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/3", "SDE.Cacao_Agroclimatic_Zones_2030s", None),
    ("https://services.arcgis.com/P8Cok4qAP1sTVE59/ArcGIS/rest/services/ZonasAgroclimaticasCacaoV1/FeatureServer/4", "SDE.Cacao_Agroclimatic_Zones", None)
]

# init logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = os.path.dirname(os.path.realpath(__file__))
log_dir = os.path.join(log_dir, "output")
if not os.path.exists(log_dir):
    os.mkdir(log_dir)
logFilePath = os.path.join(log_dir, f"CopyFeaturesToGDB_{timestamp}")
errFilePath = logFilePath + ".err"
logFilePath += ".log"
logging.basicConfig(filename=logFilePath, level=logging.DEBUG, format='%(message)s')
error_handler = logging.FileHandler(errFilePath)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(error_handler)

def log_message(msg, level='info', print_msg=True):
    if level == 'info':
        logging.info(msg)
    elif level == 'error':
        print_msg = True
        msg = f"ERROR: {msg}"
        logging.error(msg)
    elif level == 'warning':
        msg = f"WARNING: {msg}"
        logging.warning(msg)
    else:
        logging.debug(msg)
    if print_msg:
        print(msg)
        
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
    print(f"{prompt}: {user_input}")
    return user_input

def connect_to_arcgis():
    global gis, arcgis_url, arcgis_username, arcgis_password
    # global arcgis_url, base_url, selected_portal, filename_base, gis, arcgis_username, arcgis_password
    connected = False

    # ArcGIS Online
    arcgis_url_agol = 'https://rrg.maps.arcgis.com'
    # base_url_agol = 'https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services'
    # Old ArcGIS Enterprise
    arcgis_url_rrg = 'https://gis.renewablegroup.com/portal'
    # base_url_rrg = 'https://gis.renewablegroup.com/server/rest/services'
    # New ArcGIS Enterprise
    arcgis_url_nbs = 'https://maps.rrgnbs.com/arcgisportal'
    # base_url_nbs = 'https://maps.rrgnbs.com/arcgisserver/rest/services/'
    
    which_portal = get_user_input("Which ArcGIS portal (AGOL, RRG, NBS)", default_value='NBS')
    which_portal = which_portal.upper()
    if which_portal.startswith('A'):
        arcgis_url = arcgis_url_agol
        # base_url = base_url_agol
        # selected_portal = 'AGOL'
    elif which_portal.startswith('R'):
        arcgis_url = arcgis_url_rrg
        # base_url = base_url_rrg
        # selected_portal = 'RRG'
    else:
        arcgis_url = arcgis_url_nbs
        # base_url = base_url_nbs
        # selected_portal = 'NBS'
    
    # # Get ArcGIS URL from the user or default to 'https://maps.rrgnbs.com/arcgisportal'
    # arcgis_url = get_user_input("ArcGIS URL", default_value=arcgis_url)
    
    # Get arcgis_username and password from the user
    arcgis_username = get_user_input("ArcGIS Username (not SSO)", default_value='rrgadmin')
    arcgis_password = getpass.getpass(f"**  ArcGIS Password for {arcgis_username}: ")
    if arcgis_username == "" or arcgis_password == "":
        log_message("Missing username or password.", 'error')
    else:
        try:
            arcpy.SignInToPortal(arcgis_url, arcgis_username, arcgis_password)
            log_message(f"Connected to {arcgis_url} as {arcgis_username}", 'info')
            log_message("ActivePortal: " + arcpy.GetActivePortalURL(), 'info')
            connected = True
            try:
                gis = GIS(arcgis_url, arcgis_username, arcgis_password)
                log_message(f"Connected to {gis.url} using GIS", 'info')
                connected = True
            except Exception as e:
                log_message(f"Failed to connect to {arcgis_url} using GIS: {e}", 'error')
        except Exception as e:
            log_message(f"Failed to connect to {arcgis_url} using arcpy: {e}", 'error')
    return connected

def init_arcpy(workspace_path=None):
    global workspace_full_path
    try:
        log_message("Initializing arcpy...")
        if workspace_path is None:
            # ask the user which sde to use
            # create sde_prompt_string from the workspace_paths dictionary
            sde_prompt_string = "Which SDE (OPTIONS - "
            for key, value in workspace_paths.items():
                sde_prompt_string += f"{key}: {value}, "
            sde_prompt_string = sde_prompt_string[:-2] + ")"
            sde_path = get_user_input(sde_prompt_string)
            sde_path = sde_path.upper().strip()[0]
            workspace_full_path = workspace_paths.get(sde_path, workspace_full_path)
            if workspace_full_path == '' or workspace_full_path is None:
                # ask user to enter the full path
                workspace_full_path = get_user_input("Enter the full path to the workspace")
            if workspace_full_path == '' or workspace_full_path is None or (not os.path.exists(workspace_full_path)):
                log_message(f"Workspace {workspace_full_path} does not exist.", 'error')
                return False
        else:
            workspace_full_path = workspace_path
            
        # Set the workspace environment
        arcpy.env.mask = r"T:\ArcGISDataset\GIS\General GIS Data\Worldwide\World.shp"
        arcpy.env.cellSize = "MINOF"
        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = workspace_full_path
        # arcpy.env.workspace = arcpy.env.scratchGDB
        log_message(f"Workspace {workspace_full_path}", 'info')
        log_message(f"Workspace Exists: {arcpy.Exists(workspace_full_path)}", 'info')
    except Exception as e:
        log_message(f"Error initializing arcpy: {e}", 'error')
        return False
    return True


def get_json(url, params=None, trans_type='post'):
    try:
        log_message(f"Fetching JSON from {url} with params {params}")
        if trans_type == 'post':
            if params:
                response = requests.post(url, params=params)
            else:
                response = requests.post(url)
        else:
            if params:
                response = requests.get(url, params=params)
            else:
                response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Log the error message
        log_message(f"Error fetching JSON from {url} with params {params}: {e}", level='error')
        return None

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

def remove_non_ascii(text, replace_spaces=False):
    if pd.isnull(text):
        text = ''
    else:
        text = str(text)
    if text is None or text == '':
        return ''
    # replace non-ascii characters with a space 
    # except for the dash-like characters which are replaced with a hyphen
    return_text = ''.join(i if ord(i) < 128 else '-' if ord(i) in {8211, 8212, 8722, 8209, 8210} else ' ' for i in text)
    if replace_spaces:
        return_text = return_text.replace(' ', '_')
    # return_text = saxutils.escape(return_text)
    if return_text != text:
        log_message(f"Replaced non-ascii characters in '{text}' with '{return_text}'", 'info')
    return return_text

def get_service_info(service, token=None):
    recordCount = 0
    maxOID = None
    minOID = None
    OIDFieldName = None
    service_type = None
    maxRecordCount = 1000
    objectIDs = []
    
    try:
        arcpy.env.workspace = workspace_full_path
        if arcpy.Exists(service):
            log_message(f"{service} exists.")
            try:
                # get object id info from the feature class
                desc = arcpy.Describe(service)
                OIDFieldName = desc.oidFieldName
                objectIDs = [r[0] for r in arcpy.da.SearchCursor(service, ["OID@"])]
                service_type = desc.dataType
            except Exception as e:
                log_message(f"Failed to get object id info from {service}: {e}", level='error')
                return (recordCount, maxOID, minOID, OIDFieldName, service_type, maxRecordCount)
        else:
            if service.lower().startswith('http'):
                if token is None:
                    token = gis._con.token
                    if token is None:
                        log_message('Token is None. Cannot get ObjectIDs info from service.', level='error')
                        return (recordCount, maxOID, minOID, OIDFieldName, service_type, maxRecordCount)
                
                try:
                    params = {'token': token, 'f': 'json'}
                    # Get the service info
                    service_metadata = get_json(service, params)
                    if service_metadata is not None:
                        service_type = service_metadata.get('type', None)
                        maxRecordCount = service_metadata.get('maxRecordCount', 1000)
                except Exception as e:
                    log_message(f"Failed to get service metadata: {e}")
                
                log_message("Getting ObjectID info from service.")
                # service url with '/query' appended
                baseURL = f'{service}/query'
                
                # Get the ObjectIDs from the service
                params = {'where': '1=1', 'returnIdsOnly': 'true', 'token': token, 'f': 'json'}
                data = get_json(baseURL, params)
                if data is None:
                    log_message('Failed to retrieve data from service')
                    return (recordCount, maxOID, minOID, OIDFieldName, service_type, maxRecordCount)
                
                # Get the ObjectIDs from the service
                objectIDs = data.get('objectIds', [])
                OIDFieldName = data.get('objectIdFieldName', None)
            else:
                log_message(f"{service} does not exist.")
                
        recordCount = len(objectIDs)
        if recordCount > 0:
            try:
                objectIDs.sort()
                maxOID = int(objectIDs[-1])
                minOID = int(objectIDs[0]) # - 1
            except Exception as e:
                tbE = sys.exc_info()[2]
                logMsg = '\nFailed objectIDs parse at Line %i \n' % tbE.tb_lineno
                logMsg += 'Error: {}'.format(str(e))
                log_message(logMsg, level='error')
    except Exception as e:
        log_message(f'Failed objectIDs parse at with Error: {str(e)}', level='error')
    
    log_message(f'ObjectID field name: {OIDFieldName}')
    log_message(f'Number of features: {recordCount}')
    log_message(f'Max ObjectID: {maxOID}')
    log_message(f'Min ObjectID: {minOID}')
    log_message(f'Service type: {service_type}')
    log_message(f'Max Record Count: {maxRecordCount}')
    
    return (recordCount, maxOID, minOID, OIDFieldName, service_type, maxRecordCount)


# Function to copy features from a map or feature service to a feature class
def copyData(sourceService, dataDestination, token, maxRecordCount=1000):
    """ Function to copy features from a map or feature service to a feature class.
        service = the URL for the map/feature service. You must include the number at the end (/0).
        dataDestination = the output location and name of the layer you are copying data to.
    """
    # Adapted by Julie Tripp from the ArcGIS Online Feature Service Extract Tool
    # https://community.esri.com/docs/DOC-6496-download-arcgis-online-feature-service-or-arcgis-server-featuremap-service
    try:
        log_message('Attempting to copy data from {} to {}'.format(sourceService, dataDestination))

        (recordCount, maxOID, minOID, OIDFieldName, service_type, maxRecordCount) = get_service_info(sourceService, token)
        if recordCount == 0:
            log_message(f'No records found in service {sourceService}. Exiting.', level='error')
            return
        minOID = minOID - 1
        
        if service_type not in ['Feature Layer', 'Table']:
            log_message(f"Unsupported service type: {service_type}. Exiting.", level='error')
            return
        
        if service_type == 'Table':
            geometry_field = None
        else:
            geometry_field = 'SHAPE@'
        
        (recordCount_dest, maxOID_dest, minOID_dest, OIDFieldName_dest, service_type_dest, maxRecordCount_dest) = get_service_info(dataDestination, token)
        if recordCount_dest > 0:
            initialCopy = False
            log_message(f"Destination '{dataDestination}' already exists with {maxOID_dest} max ObjectID.")
            minOID = maxOID_dest
        else:
            log_message(f"Destination '{dataDestination}' does not exist. Creating new {service_type}.")
            initialCopy = True
            
        if recordCount <= recordCount_dest:
            log_message(f"Destination '{dataDestination}' already contains all records from service {sourceService}. Exiting.", level='info')
        else:
            copySuccess = False
            if recordCount_dest == 0:
                try:
                    if geometry_field:
                        # Feature Layer
                        if arcpy.Exists(sourceService):
                            log_message(f"Copying with arcpy: {sourceService} to {dataDestination}")
                            try:
                                arcpy.management.CopyFeatures(
                                    in_features=sourceService,
                                    out_feature_class=dataDestination,
                                    config_keyword="",
                                    spatial_grid_1=None,
                                    spatial_grid_2=None,
                                    spatial_grid_3=None
                                )
                                copySuccess = True
                            except arcpy.ExecuteError as e:
                                log_message(f"Failed to copy with CopyFeatures: {e}")
                                log_message(arcpy.GetMessages(2), 'info')
                            except Exception as e:
                                log_message(f"Failed to copy with CopyFeatures: {e}")
                                log_message("Attempting using arcpy ExportFeatures")
                            if not copySuccess:
                                try:
                                    arcpy.conversion.ExportFeatures(
                                        in_features=sourceService,
                                        out_features=dataDestination
                                    )
                                    copySuccess = True
                                except arcpy.ExecuteError as e:
                                    log_message(f"Failed to copy with ExportFeatures: {e}")
                                    log_message(arcpy.GetMessages(2), 'info')
                                except Exception as e:
                                    log_message(f"Failed to copy with ExportFeatures: {e}")
                                    log_message(f"Traceback: {traceback.format_exc()}")
                    else:
                        log_message(f"Copying table with arcpy: {sourceService} to {dataDestination}")
                        arcpy.management.CopyRows(
                            in_rows=sourceService,
                            out_table=dataDestination,
                            config_keyword=""
                        )
                        copySuccess = True
                except Exception as e:
                    log_message(f"Error using arcpy to copy: {e}")
                
            if not copySuccess:
                if not sourceService.lower().startswith('http'):
                    log_message(f"Service {sourceService} not found.", level='error')
                else:
                    # # from arcpy import env
                    # # overwite output
                    # # env.overwriteOutput = True
                    # scratch workspace
                    # http://pro.arcgis.com/en/pro-app/tool-reference/environment-settings/scratch-gdb.htm
                    arcpy.env.workspace = arcpy.env.scratchGDB
                    # overwite output
                    arcpy.env.overwriteOutput = True
                    
                    try:
                        # Determine type of workspace for feature class
                        log_message('Determining workspace type for {}'.format(os.path.dirname(dataDestination)))
                        desc = arcpy.Describe(os.path.dirname(dataDestination))
                        workspaceType = desc.workspaceFactoryProgID
                        log_message(f'Workspace type: {workspaceType}')
                    except Exception as e:
                        log_message(f'Unable to determine workspace type. Error: {e}', level='error')
                        workspaceType = None

                    # service url with '/query' appended
                    baseURL = f'{sourceService}/query'
                    
                    # Copy features from sourceService
                    if recordCount < maxRecordCount:
                        x = maxOID
                        y = minOID
                        # where = OIDFieldName + '>' + str(y) + 'AND ' + OIDFieldName + '<=' + str(x)
                        where = "1=1"
                        fields ='*'

                        params = f"?where={where}&outFields={fields}&returnGeometry={'true' if geometry_field else 'false'}&f=json&token={token}"
                        sourceURL = baseURL + params
                        log_message('Query URL: {}'.format(sourceURL))
                        
                        loadError = False
                        if geometry_field:
                            fs = arcpy.FeatureSet()
                            try:
                                # load sourceService
                                fs.load(sourceURL)
                            except Exception as e:
                                loadError = True
                                logMsg = 'Failed FeatureSet Load with Error loading features: {}.'.format(str(e))
                                log_message(logMsg, level='error')
                            if not loadError:
                                # Copy features
                                log_message('Copying features with ObjectIDs from {} to {} of {}'.format(str(y), str(x), str(maxOID)))
                                try:
                                    if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                                        # If the workspace is an SDE workspace, use the feature class name without the path
                                        dataDestination2 = dataDestination.split(".")[-1]
                                    else:
                                        dataDestination2 = os.path.basename(dataDestination)
                                    arcpy.FeatureClassToFeatureClass_conversion(fs, os.path.dirname(dataDestination), dataDestination2)
                                except Exception as e:
                                    logMsg = 'Failed FeatureClassToFeatureClass with Error: {}'.format(str(e))
                                    log_message(logMsg, level='error')
                        else:
                            tableData = get_json(sourceURL)
                            # export tableData to CSV
                            if tableData is not None and 'features' in tableData:
                                # set csv file path as output directory plus table name plus .csv
                                tableOutputPath = log_dir
                                if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                                    tableOutputPath = os.path.join(log_dir, dataDestination.split(".")[-1])
                                else:
                                    tableOutputPath = os.path.join(log_dir, os.path.basename(dataDestination))
                                tableOutputPath += '.csv'
                                log_message(f"Exporting table data to '{tableOutputPath}'.")
                                features = tableData['features']
                                if features:
                                    fieldnames = list(features[0]['attributes'].keys())
                                    with open(tableOutputPath, 'w', encoding='utf-8') as f:
                                        # json.dump(tableData, f, ensure_ascii=False)
                                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                                        writer.writeheader()
                                        for feature in features:
                                            writer.writerow(feature['attributes'])
                                    log_message(f"Exported table data to '{tableOutputPath}'.")
                                    
                                    if arcpy.Exists(dataDestination):
                                        # use arcpy append to append the csv table data to the destination
                                        log_message(f"Appending table data to {dataDestination}.")
                                        try:
                                            arcpy.management.Append(
                                                inputs=tableOutputPath,
                                                target=dataDestination,
                                                schema_type="TEST",
                                                field_mapping=None,
                                                subtype="",
                                                expression="",
                                                match_fields=None,
                                                update_geometry="NOT_UPDATE_GEOMETRY"
                                            )
                                        except Exception as e:
                                            logMsg = 'Failed Append with Error: {}'.format(str(e))
                                            log_message(logMsg, level='error')
                                    else:
                                        # use arcpy to copy the csv table data to the destination
                                        log_message(f"Copying table data to {dataDestination}.")
                                        try:
                                            arcpy.management.CopyRows(
                                                in_rows=tableOutputPath,
                                                out_table=dataDestination,
                                                config_keyword=""
                                            )
                                        except Exception as e:
                                            logMsg = 'Failed CopyRows with Error: {}'.format(str(e))
                                            log_message(logMsg, level='error')
                                            
                                    # delete tableOutputPath
                                    if os.path.exists(tableOutputPath):
                                        os.remove(tableOutputPath)

                    else:
                        newIteration = (math.ceil(maxOID/maxRecordCount) * maxRecordCount)
                        log_message('Number of features exceeds maxRecordCount. Splitting into {} iterations.'.format(newIteration))
                        x = minOID + maxRecordCount
                        y = minOID

                        while y <= newIteration and x <= maxOID:
                            if x > maxOID:
                                x = maxOID
                            where = OIDFieldName + '>' + str(y) + 'AND ' + OIDFieldName + '<=' + str(x)
                            fields ='*'

                            params = f"?where={where}&outFields={fields}&returnGeometry={'true' if geometry_field else 'false'}&f=json&token={token}"
                            sourceURL = baseURL + params
                            log_message('Query URL: {}'.format(sourceURL))

                            loadError = False
                            if geometry_field:
                                fs = arcpy.FeatureSet()
                                try:
                                    # load sourceService
                                    fs.load(sourceURL)
                                except Exception as e:
                                    loadError = True
                                    log_message(f'Failed Loading Service with Error: {str(e)}', level='error')
                                    
                                if not loadError:
                                    log_message('Copying features with ObjectIDs from {} to {} of {}'.format(str(y), str(x), str(maxOID)))
                                    if initialCopy:
                                        try:
                                            if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                                                # If the workspace is an SDE workspace, use the feature class name without the path
                                                dataDestination2 = dataDestination.split(".")[-1]
                                            else:
                                                dataDestination2 = os.path.basename(dataDestination)
                                            log_message(f'Destination feature class: {dataDestination2}')
                                            arcpy.FeatureClassToFeatureClass_conversion(fs, os.path.dirname(dataDestination), dataDestination2)
                                        except Exception as e:
                                            log_message(f'Failed FeatureClassToFeatureClass with Error: {str(e)}', level='error')

                                        initialCopy = False
                                    else:
                                        if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                                            try:
                                                insertRows = arcpy.da.InsertCursor(dataDestination, ["*","SHAPE@"])
                                                searchRows = arcpy.da.SearchCursor(fs, ["*","SHAPE@"])
                                                for searchRow in searchRows:
                                                    fieldList = list(searchRow)
                                                    insertRows.insertRow(fieldList)
                                            except Exception as e:
                                                log_message(f'Failed Inserting Rows with Error: {str(e)}', level='error')
                                            finally:
                                                try:
                                                    del searchRow, searchRows, insertRows
                                                except:
                                                    pass
                                        elif workspaceType == '':
                                            try:
                                                arcpy.Append_management(fs, dataDestination, "NO_TEST")
                                            except Exception as e:
                                                log_message(f'Failed Append_management ("NO_TEST") with Error: {str(e)}', level='error')
                                        else:
                                            try:
                                                arcpy.Append_management(fs, dataDestination)
                                            except Exception as e:
                                                log_message(f'Failed Append_management with Error: {str(e)}', level='error')
                            else:
                                # Table
                                tableData = get_json(sourceURL)
                                # export tableData to CSV
                                if tableData is not None:
                                    # set csv file path as output directory plus table name plus .csv
                                    tableOutputPath = log_dir + '/'
                                    if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                                        tableOutputPath += dataDestination.split(".")[-1]
                                    else:
                                        tableOutputPath += os.path.basename(dataDestination)
                                    tableOutputPath += '_' + (str(x)) + '.csv'
                                    log_message(f"Exporting table data to {tableOutputPath}.")
                                    features = tableData['features']
                                    if features:
                                        fieldnames = list(features[0]['attributes'].keys())
                                        with open(tableOutputPath, 'w', encoding='utf-8', newline='') as f:
                                            # json.dump(tableData, f, ensure_ascii=False)
                                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                                            writer.writeheader()
                                            for feature in features:
                                                writer.writerow(feature['attributes'])
                                    
                                        if not initialCopy:
                                            # use arcpy append to append the csv table data to the destination
                                            log_message(f"Appending table data to {dataDestination}.")
                                            try:
                                                arcpy.management.Append(
                                                    inputs=tableOutputPath,
                                                    target=dataDestination,
                                                    schema_type="TEST",
                                                    field_mapping=None,
                                                    subtype="",
                                                    expression="",
                                                    match_fields=None,
                                                    update_geometry="NOT_UPDATE_GEOMETRY"
                                                )
                                            except Exception as e:
                                                logMsg = 'Failed Append with Error: {}'.format(str(e))
                                                log_message(logMsg, level='error')
                                        else:
                                            # use arcpy to copy the csv table data to the destination
                                            log_message(f"Copying table data to {dataDestination}.")
                                            try:
                                                arcpy.management.CopyRows(
                                                    in_rows=tableOutputPath,
                                                    out_table=dataDestination,
                                                    config_keyword=""
                                                )
                                                initialCopy = False
                                            except Exception as e:
                                                logMsg = 'Failed CopyRows with Error: {}'.format(str(e))
                                                log_message(logMsg, level='error')
                                        if os.path.exists(tableOutputPath):
                                            os.remove(tableOutputPath)

                            x += maxRecordCount
                            y += maxRecordCount

    except Exception as e:
        logMsg = 'CopyData Failed with Error: {}'.format(str(e))
        log_message(logMsg, level='error')
    finally:
        arcpy.env.workspace = workspace_full_path
        log_message('CopyData completed.')


def load_features_and_workspace_from_csv(csv_file_path):
    # CSV columns: feature_name,feature_service_url,database_owner_name,workspace_full_path
    features = []
    try:
        csv_import_df = pd.read_csv(csv_file_path, encoding=get_file_encoding(csv_file_path))
        # Check if the CSV file has the required columns
        required_columns = ['feature_name', 'feature_service_url', 'database_owner_name']
        # optional column: workspace_full_path, item_id
        if not all(col in csv_import_df.columns for col in required_columns):
            log_message(f"CSV file '{csv_file_path}' does not contain the required columns: {required_columns}", 'error')
            return features
        csv_import_df = csv_import_df.sort_values(by=['workspace_full_path', 'feature_service_url'])
        # Read the CSV file and extract the feature URLs and workspace paths
        for index, row in csv_import_df.iterrows():
            feature_url = row.get('feature_service_url')
            feature_table_name = row.get('database_owner_name', 'SDE') + '.' + row.get('feature_name')
            item_id = row.get('item_id', None)
            workspace_path = row.get('workspace_full_path', None)
            if feature_url and feature_table_name:
                features.append((feature_url, feature_table_name, item_id, workspace_path))
    except Exception as e:
        log_message(f"Error reading CSV file {csv_file_path}: {e}", 'error')
    return features

def query_in_chunks(feature_layer, chunk_size=1000, feature_table_name=None):
    # Query features in chunks to avoid memory issues.
    # Returns a JSON array of features.
    features = []
    offset = 0
    total_count = feature_layer.query(where='1=1', return_count_only=True)
    log_message(f"Total features to process: {total_count}", 'info')
    
    if feature_table_name is None:
        feature_table_name = remove_non_ascii(feature_layer.properties['name'], replace_spaces=True)
        feature_table_name = feature_table_name.upper()
        if not feature_table_name[0].isalpha():
            feature_table_name = 'NBS_' + feature_table_name
        if not feature_table_name.startswith('SDE.'):
            feature_table_name = 'SDE.' + feature_table_name
        if len(feature_table_name) > 128:
            feature_table_name = feature_table_name[:128]
        feature_table_name = os.path.join(workspace_full_path, feature_table_name)
    log_message(f"Feature table name: {feature_table_name}", 'info')
    log_message(f"Chunk size: {chunk_size}", 'info')
    
    # if total_count <= chunk_size:
    # log_message(f"Total features {total_count} <= chunk size {chunk_size}. Copying all features at once.", 'info')
    
    directCopyFailed = False
    
    copyFeaturesFailed = False
    try:
        log_message("Attempting to copy feature_layer using CopyFeatures")
        arcpy.management.CopyFeatures(
            in_features=feature_layer,
            out_feature_class=feature_table_name,
            config_keyword="",
            spatial_grid_1=None,
            spatial_grid_2=None,
            spatial_grid_3=None
        )
    except arcpy.ExecuteError as e:
        log_message(f"Failed to copy feature_layer with CopyFeatures: {e}")
        log_message(arcpy.GetMessages(2), 'info')
        copyFeaturesFailed = True
    except Exception as e:
        log_message(f"Failed to copy feature_layer with CopyFeatures: {e}")
        log_message(f"Traceback: {traceback.format_exc()}")
        copyFeaturesFailed = True
        
    if copyFeaturesFailed:
        log_message("Attempting to copy feature_layer using ExportFeatures")
        try:
            arcpy.conversion.ExportFeatures(
                in_features=feature_layer,
                out_features=feature_table_name
            )
        except Exception as e:
            log_message(f"Failed to copy with ExportFeatures: {e}")
            log_message(f"Traceback: {traceback.format_exc()}")
            directCopyFailed = True
            
    if directCopyFailed:
        log_message(f"Direct copy failed. Querying features in chunks...", 'info')
        
        OIDFieldName = feature_layer.properties.get('objectIdField', 'OBJECTID')
        '''
        try:
            descFeature = arcpy.Describe(feature_layer)
            OIDFieldName = descFeature.OIDFieldName
        except Exception as e:
            log_message(f"Failed to get OIDFieldName from Describe: {e}")
        '''
        log_message(f"OIDFieldName: {OIDFieldName}", 'info')
        
        allOIDs_results = feature_layer.query(where='1=1', return_ids_only=True)
        # log_message(f"allOIDs_results: {allOIDs_results.keys()}", 'info')
        # dict_keys(['objectIdFieldName', 'objectIds'])
        allOIDs = allOIDs_results['objectIds']
        # get the minimum and maximum OID values
        minOID = min(allOIDs)
        log_message(f"Minimum OID: {minOID}", 'info')
        # maxOID = max(allOIDs)
        
        # check if feature_table_name exists
        if arcpy.Exists(feature_table_name):
            firstExport = False
            log_message(f"{feature_table_name} already exists.")
        else:
            firstExport = True
            log_message(f"{feature_table_name} does not exist. Creating new feature class.")
        
        # retries = 5
        while offset < total_count: # and retries > 0:
            if total_count <= chunk_size:
                where_clause = '1=1'
            else:
                x = minOID + offset
                y = x + chunk_size - 1
                log_message(f"Processing features {x} to {y}", 'info')
                where_clause = OIDFieldName + ' >= ' + str(x) + ' AND ' + OIDFieldName + ' <= ' + str(y)
            log_message(f"Exporting features with where clause: {where_clause}", 'info')
            # log_message(f"Querying features from offset {offset} to {offset + chunk_size - 1}", 'info')
            '''
            try:
                # results are returend as a FeatureSet
                feature_set = feature_layer.query(where='1=1', 
                                                    out_fields='*', 
                                                    return_geometry=True, 
                                                    result_offset=offset, 
                                                    result_record_count=chunk_size)
                log_message(f"FeatureSet type: {type(feature_set)}", 'info')
                log_message(f"FeatureSet length: {len(feature_set.features)}", 'info')
                if len(feature_set.features) == 0:
                    log_message(f"No more features found at offset {offset}.", 'info')
                    break
                
                # features.extend(feature_set.features)
                features += feature_set.features
            except Exception as e:
                # if 429 in error or too many requests, wait 5 seconds and retry
                if '429' in str(e) or 'too many requests' in str(e):
                    log_message(f"Rate limit exceeded. Waiting for 61 seconds before retrying...", 'warning')
                    time.sleep(61)
                    retries -= 1
                    continue
                else:
                    log_message(f"Error querying features: {e}", 'error')
                    break
            '''
            if firstExport:
                log_message(f"Copying features to {feature_table_name}...", 'info')
                try:
                    arcpy.conversion.ExportFeatures(
                        in_features=feature_layer,
                        out_features=feature_table_name,
                        where_clause=where_clause
                    )
                except Exception as e:
                    log_message(f"Failed to copy feature_layer with ExportFeatures for chunk: {e}")
                    log_message(f"Traceback: {traceback.format_exc()}")
                    try:
                        log_message("Getting features using query...")
                        feature_set = feature_layer.query(where=where_clause,
                                                          out_fields='*',
                                                          return_geometry=True)
                        if len(feature_set.features) == 0:
                            log_message(f"No more features found at offset {offset}.", 'info')
                            break
                        log_message(f"FeatureSet length: {len(feature_set.features)}", 'info')
                        log_message(f"FeatureSet type: {type(feature_set)}", 'info')
                    except Exception as e:
                        log_message(f"Failed to query feature_layer with where clause: {e}", 'error')
                        log_message(f"Traceback: {traceback.format_exc()}", 'error')
                        del feature_set
                        break
                    copyFeaturesFailed = False
                    try:
                        log_message(f"Copying features to {feature_table_name} using CopyFeatures...", 'info')
                        arcpy.management.CopyFeatures(
                            in_features=feature_set,
                            out_feature_class=feature_table_name,
                            config_keyword="",
                            spatial_grid_1=None,
                            spatial_grid_2=None,
                            spatial_grid_3=None
                        )
                    except arcpy.ExecuteError as e:
                        log_message(f"Failed to copy feature_set with CopyFeatures for chunk: {e}")
                        log_message(arcpy.GetMessages(2))
                        copyFeaturesFailed = True
                    except Exception as e:
                        log_message(f"Failed to copy feature_set with CopyFeatures for chunk: {e}")
                        log_message(f"Traceback: {traceback.format_exc()}")
                        copyFeaturesFailed = True
                    if copyFeaturesFailed:
                        try:
                            log_message("Attempting using arcpy ExportFeatures")
                            arcpy.conversion.ExportFeatures(
                                in_features=feature_set,
                                out_features=feature_table_name
                            )
                        except arcpy.ExecuteError as e:
                            log_message(f"Failed to copy feature_set with ExportFeatures for chunk: {e}", 'error')
                            log_message(arcpy.GetMessages(2), 'error')
                            del feature_set
                            break
                        except Exception as e:
                            log_message(f"Failed to copy feature_set with ExportFeatures for chunk: {e}", 'error')
                            log_message(f"Traceback: {traceback.format_exc()}", 'error')
                            del feature_set
                            break
                    del feature_set
                log_message(f"Successfully copied features to {feature_table_name} with where clause: {where_clause}", 'info')
                firstExport = False
            else:
                log_message(f"Appending features to {feature_table_name}...", 'info')
                feature_set = feature_layer.query(where=where_clause, 
                                                  out_fields='*', 
                                                  return_geometry=True)
                if len(feature_set.features) == 0:
                    log_message(f"No more features found at offset {offset}.", 'info')
                    break
                try:
                    arcpy.management.Append(
                        inputs=feature_set,
                        target=feature_table_name,
                        schema_type="NO_TEST"
                    )
                    log_message(f"Successfully appended features to {feature_table_name} with where clause: {where_clause}", 'info')
                except Exception as e:
                    log_message(f"Failed to append features to {feature_table_name}: {e}", 'error')
                    log_message(f"Traceback: {traceback.format_exc()}", 'error')
                    del feature_set
                    break
                del feature_set
            
            offset += chunk_size
        '''
        if retries <= 0:
            log_message("Max retries reached. Exiting...", 'error')
        else:
            log_message(f"Total features retrieved: {len(features)}", 'info')
        '''
    return features
'''
def create_arcpy_featureset_from_feature_list(feature_list, spatial_reference_wkid=3857):
    """
    Convert an accumulated list of feature dictionaries into an arcpy.FeatureSet.
    
    Parameters:
      feature_list (list): A list of feature dictionaries (each with "attributes" and "geometry").
      spatial_reference_wkid (int): The spatial reference wkid (default is 3857).
      
    Returns:
      arcpy.FeatureSet: A FeatureSet object loaded with the provided features.
    """
    if not feature_list:
        raise ValueError("Feature list is empty; cannot create FeatureSet.")
    
    # Use the first feature to derive the fields and geometry type.
    sample_feature = feature_list[0]
    if "geometry" not in sample_feature or not sample_feature["geometry"]:
        raise ValueError("Sample feature does not have valid geometry.")
    
    # You might extract geometry type from the sample feature.
    # For this example, we assume the geometry dictionary has a "type" key.
    geometry_type = sample_feature["geometry"].get("type", "esriGeometryPoint")
    
    # Derive fields from the keys in the attributes dictionary.
    fields = list(sample_feature.get("attributes", {}).keys())
    
    # Build a simple FeatureSet JSON dictionary. A more robust version would
    # determine field types and include additional schema info.
    feature_set_dict = {
         "displayFieldName": "",
         "fieldAliases": {field: field for field in fields},
         "fields": [{"name": field, "type": "esriFieldTypeString", "alias": field} for field in fields],
         "features": feature_list,
         "geometryType": geometry_type,
         "spatialReference": {"wkid": spatial_reference_wkid}
    }
    
    # Convert the dictionary to a JSON string.
    feature_set_json = json.dumps(feature_set_dict)
    
    # Create a new arcpy.FeatureSet and load the JSON.
    fs = arcpy.FeatureSet()
    fs.loadJSON(feature_set_json)
    
    return fs
'''

def enable_export(item_id, feature_table_name=None):
    item_capabilities_orig = None
    maxRecordCount = None
    feature_sets = []
    wkid = None
    if item_id is not None:
        try:
            item = gis.content.get(item_id)
            if item:
                item_flc = FeatureLayerCollection.fromitem(item)
                # log_message(f"item properties: {item_flc.properties}", 'info')
                item_capabilities_orig = item_flc.properties['capabilities']
                log_message(f"original item capabilities: {item_capabilities_orig}", 'info')
                
                if 'Extract' not in item_flc.properties['capabilities']:
                    # append 'Extract' to item_capabilities
                    item_capabilities = item_capabilities_orig + ',Extract'
                    item_flc.manager.update_definition({'capabilities': item_capabilities})
                    log_message(f"Export enabled for item {item.title} ({item.id})", 'info')
                else:
                    item_capabilities_orig = None
                    
                maxRecordCount = item_flc.properties['maxRecordCount']
                log_message(f"maxRecordCount: {maxRecordCount}", 'info')
                
                spatial_ref = item_flc.properties.get('spatialReference', {})
                wkid = spatial_ref.get('latestWkid', spatial_ref.get('wkid', 3857))
                
                # log found number of layers
                log_message(f"Number of layers: {len(item_flc.layers)}", 'info')
                for layer in item_flc.layers:
                    # print everything about the layer
                    log_message(f"Layer properties: {layer.properties}", 'info')
                    try:
                        log_message(f"Layer ID: {layer.properties['id']}, Layer Name: {layer.properties['name']}", 'info')
                        # feature_set = layer.query(where='1=1', out_fields='*', return_geometry=True)
                        # feature_set = query_in_chunks(layer, maxRecordCount)
                        query_in_chunks(layer, maxRecordCount)
                        # feature_sets.append(feature_set)
                    except Exception as e:
                        log_message(f"Failed to query layer: {e}", 'error')
                
                if item_capabilities_orig is not None:
                    # restore original capabilities
                    item_flc.manager.update_definition({'capabilities': item_capabilities_orig})
                    log_message(f"Restored original capabilities", 'info')
                    
            else:
                log_message(f"Item with ID {item_id} not found.", 'error')
        except Exception as e:
            log_message(f"Failed to enable export for item {item_id}: {e}", 'error')
            return feature_sets # (item_capabilities_orig, maxRecordCount)
    return (feature_sets, wkid) # (item_capabilities_orig, maxRecordCount)

def copy_feature_in_chunks():
    log_message("Copying features in chunks...")

def download_feature(feature_url, gis_token):
    log_message(f"Downloading feature from {feature_url}...")
    try:
        feature_layer = FeatureLayerCollection(feature_url, gis_token=gis_token)
        features = feature_layer.query(where='1=1', out_fields='*', return_geometry=True)
        return features
    except Exception as e:
        log_message(f"Failed to download features from {feature_url}: {e}", 'error')
        return None

def get_unique_name(feature_table_name):
    increment = 1
    this_feature_table_name = feature_table_name
    # loop until a unique name is found
    while arcpy.Exists(this_feature_table_name):
        this_feature_table_name = feature_table_name + f"_{increment}"
        increment += 1
    return this_feature_table_name


# Main script execution

if not connect_to_arcgis():
    log_message("Failed to connect to ArcGIS. Exiting.", 'error')
    exit()
    
gis_token = gis._con.token
if not gis_token:
    log_message("Failed to get GIS token. Exiting.", 'error')
    exit()

# if features_list only has two columns, add the workspace_full_path to the features_list
if len(features_list) > 0 and len(features_list[0]) == 3:
    for i in range(len(features_list)):
        feature_url, feature_table_name, item_id = features_list[i]
        features_list[i] = (feature_url, feature_table_name, item_id, None)

# Load features and workspace from CSV argument if provided
if len(sys.argv) > 1:
    csv_file_path = sys.argv[1]
    if csv_file_path.split('.')[-1].lower() == 'csv':
        log_message(f"Loading features and workspace from CSV file: {csv_file_path}")
        features_list = load_features_and_workspace_from_csv(csv_file_path)
        if not features_list:
            log_message("No valid features or workspace found in the CSV file.", 'error')
            exit()
    else:
        log_message("Invalid file type. Please provide a CSV file.", 'error')
        exit()
else:
    log_message("Using hardcoded features list and workspace paths.")
    


prev_workspace_path = None
for feature in features_list:
    feature_url, feature_table_name, item_id, this_workspace_path = feature
    
    if this_workspace_path is None:
        if workspace_full_path is None:
            if not init_arcpy(workspace_full_path):
                log_message("Failed to initialize arcpy and connect to ArcGIS", 'error')
                exit()
    else:
        if prev_workspace_path is None or prev_workspace_path != this_workspace_path:
            if not init_arcpy(this_workspace_path):
                log_message(f"Failed to initialize arcpy and connect to ArcGIS for workspace {this_workspace_path}", 'error')
                exit()
    prev_workspace_path = workspace_full_path
    
    '''
    # Append the token to the feature_url
    if feature_url.startswith('http'):
        feature_url = feature_url + "?token=" + gis_token
    '''
    
    # add workspace to feature_table_name
    feature_table_name = os.path.join(workspace_full_path, feature_table_name)
    
    try:
        '''
        if arcpy.Exists(feature_table_name):
            log_message(f"{feature_table_name} already exists. Copy did not complete.", 'warning')
        else:
            if item_id is not None:
                (feature_sets, wkid) = enable_export(item_id, feature_table_name)
                if feature_sets is None or len(feature_sets) == 0:
                    log_message(f"Failed to get feature sets for item {item_id}", 'error')
                    continue
                
                log_message(f"Number of feature sets: {len(feature_sets)}", 'info')
                
                for feature_set in feature_sets:
                    this_feature_table_name = get_unique_name(feature_table_name)
                    try:
                        log_message(f"Copying to {this_feature_table_name}...")
                        arcpy.management.CopyFeatures(
                            in_features=feature_set,
                            out_feature_class=this_feature_table_name,
                            config_keyword="",
                            spatial_grid_1=None,
                            spatial_grid_2=None,
                            spatial_grid_3=None
                        )
                        log_message(f"Successfully copied to {this_feature_table_name}")
                    except Exception as e:
                        log_message(f"Failed to copy with CopyFeatures: {e}", 'error')
                del feature_sets
                continue
            if not arcpy.Exists(feature_url):
                log_message(f"Feature URL {feature_url} does not exist. Skipping.", 'warning')
                continue
            
            log_message(f"Copying {feature_url} to {feature_table_name}")
            copyFeaturesFailed = False
            try:
                arcpy.management.CopyFeatures(
                    in_features=feature_url,
                    out_feature_class=feature_table_name,
                    config_keyword="",
                    spatial_grid_1=None,
                    spatial_grid_2=None,
                    spatial_grid_3=None
                )
            except arcpy.ExecuteError as e:
                log_message(f"Failed to copy with CopyFeatures: {e}")
                log_message(arcpy.GetMessages(2), 'info')
                copyFeaturesFailed = True
            except Exception as e:
                log_message(f"Failed to copy with CopyFeatures: {e}")
                log_message("Attempting using arcpy ExportFeatures")
                copyFeaturesFailed = True
            if copyFeaturesFailed:
                try:
                    arcpy.conversion.ExportFeatures(
                        in_features=feature_url,
                        out_features=feature_table_name
                    )
                except arcpy.ExecuteError as e:
                    log_message(f"Failed to copy with ExportFeatures: {e}")
                    log_message(arcpy.GetMessages(2), 'info')
                    continue
                except Exception as e:
                    log_message(f"Failed to copy with ExportFeatures: {e}")
                    log_message(f"Traceback: {traceback.format_exc()}")
                    continue
        '''
            
        copyData(sourceService=feature_url, 
                    dataDestination=feature_table_name,
                    token=gis_token, 
                    maxRecordCount=1000)
        
        log_message(f"Successfully copied {feature_url} to {feature_table_name}")
    except Exception as e:
        log_message(f"Failed to copy {feature_url} to {feature_table_name}: {e}", 'error')

log_message("Script completed successfully.")

logging.shutdown()
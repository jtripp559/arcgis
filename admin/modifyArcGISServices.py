from arcgis.gis import GIS
from getpass import getpass
import json
import os
import requests
import datetime
import pandas as pd
import pprint
from arcgis.features.managers import FeatureLayerCollectionManager
from arcgis.raster._layer import ImageryLayerCacheManager
from arcgis.mapping._types import MapImageLayerManager
from arcgis.gis.server.admin._services import Service as AdminService

rest_url = "https://maps.rrgnbs.com/arcgisserver/rest/services/"
portal_url = "https://maps.rrgnbs.com/arcgisportal"
portal_username = "rrgadmin"

output_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(output_dir, 'output')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
output_dir = os.path.join(output_dir, 'services')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

recycle_hour = 0
recycle_minute = 0

# Timestamp for unique naming
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# initialize logging for INFO and above in a file in the output directory
import logging
logging.basicConfig(
    filename=os.path.join(output_dir, f'modifyArcGISServices_{timestamp}.log'), 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def log_message(message, log_level='info'):
    if message is None:
        return
    if log_level == '' or log_level == 'error':
        print(message)
    if log_level == '':
        log_level = 'info'
    if log_level == 'error':
        message = f"!!!!!!! ERROR: {message}"
        logger.error(message)
    elif log_level == 'warning':
        message = f"WARNING: {message}"
        logger.warning(message)
    elif log_level == 'info':
        logger.info(message)
    elif log_level == 'debug':
        message = f"DEBUG: {message}"
        logger.debug(message)

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
    return user_input

def get_file_path(filebasename, fileappend=None, extension='json'):
    filepath = None
    if fileappend is not None:
        filebasename += f"_{fileappend}"
    fileincrement = 1
    filename = f"{filebasename}_{fileincrement}.{extension}"
    # while file exists, increment the filename
    while os.path.exists(os.path.join(output_dir, filename)):
        if extension == 'json':
            # read the json file
            with open(os.path.join(output_dir, filename), 'r') as f:
                existing_data = json.load(f)
            # check if the existing json file has a key "error"
            if 'error' in existing_data:
                # delete the file
                os.remove(os.path.join(output_dir, filename))
                break
            else:
                log_message(f"File already exists: {filename}", 'debug')
                return filepath
        fileincrement += 1
        filename = f"{filebasename}_{fileincrement}.{extension}"
    filepath = os.path.join(output_dir, filename)
    return filepath

def print_to_file(data, filebasename, fileappend=None, unique_record_column_name=None, additional_dict=None):
    # initialize a return pandas DataFrame
    df = pd.DataFrame()
    try:
        converted_data = data
        # print the type of the data
        log_message(f"{filebasename} data type: {type(data)}", 'debug')
        try:
            # try to convert data to dict
            if isinstance(data, str):
                converted_data = json.loads(data)
            else:
                converted_data = dict(data)
        except Exception as e:
            log_message(f"Error converting data to dict: {e}", 'warning')
            converted_data = data
        log_message(f"converted data type: {type(converted_data)}", 'debug')
        
        if isinstance(converted_data, dict):
            datatype = 'dict'
            extension = 'json'
        elif isinstance(converted_data, list):
            datatype = 'list'
            extension = 'txt'
        elif isinstance(converted_data, str):
            datatype = 'str'
            extension = 'txt'
        else:
            return df
        
        filepath = get_file_path(filebasename, fileappend, extension)
        if filepath is None:
            return df
        
        if datatype == 'dict':
            data_json = json.dumps(converted_data, indent=4)
            with open(filepath, 'w') as f:
                f.write(data_json)
            try:
                log_message("Convert to pandas DataFrame", 'debug')
                df = pd.json_normalize(converted_data)
                for col in df.columns:
                    if df[col].apply(lambda x: isinstance(x, list)).any():
                        log_message(f"Exploding column: {col}", 'debug')
                        df = df.explode(col).reset_index(drop=True)
                        # if the exploded column is a list of dicts, convert to pandas DataFrame
                        if df[col].apply(lambda x: isinstance(x, dict)).any():
                            normalized_col = pd.json_normalize(df[col])
                            normalized_col.columns = [f"{col}.{sub_col}" for sub_col in normalized_col.columns]
                            df = pd.concat([df.drop(columns=[col]), normalized_col], axis=1)
                if additional_dict is not None:
                    for key, value in additional_dict.items():
                        df[key] = value
                log_message("Converted to pandas DataFrame", 'debug')
                csv_export_path = os.path.join(output_dir, f"{filebasename}_{timestamp}.csv")
                log_message(f"Looking for existing CSV file: {csv_export_path}", 'debug')
                if os.path.exists(csv_export_path):
                    log_message(f"Found existing CSV file: {csv_export_path}", 'debug')
                    csv_df = pd.read_csv(csv_export_path)
                    log_message(f"Concatenating dataframes", 'debug')
                    df = pd.concat([csv_df, df])
                    try:
                        log_message("Dropping duplicates", 'debug')
                        if unique_record_column_name in df.columns:
                            df.drop_duplicates(inplace=True, subset=[unique_record_column_name])
                        else:
                            df.drop_duplicates(inplace=True)
                    except Exception as e:
                        log_message(f"Error dropping duplicates: {e}", 'warning')
                log_message("Exporting to CSV", 'debug')
                df.to_csv(csv_export_path, index=False, header=True)
                log_message(f"Exported to '{csv_export_path}'", 'debug')
            except Exception as e:
                log_message(f"Error exporting to CSV '{csv_export_path}': {e}", 'error')
            
        elif datatype == 'list':
            # export to a txt file
            with open(filepath, 'w') as f:
                for rec in converted_data:
                    # log_message(f"{filebasename} record data type: {type(rec)}", 'debug')
                    if isinstance(rec, dict):
                        rec = json.dumps(rec, indent=4)
                    elif isinstance(rec, list):
                        for r in rec:
                            if isinstance(r, dict):
                                r = json.dumps(r, indent=4)
                            elif isinstance(r, list):
                                r = str(r)
                            else:
                                r = str(r)
                            f.write(f"{r}\n")
                    else:
                        rec = str(rec)
                    f.write(f"{rec}\n")
        elif datatype == 'str':
            # export to a txt file
            with open(filepath, 'w') as f:
                f.write(converted_data)
        log_message(f"Exported to '{filepath}'", 'debug')
    except Exception as e:
        log_message(f"Error exporting data to file '{filepath}': {e}", 'error')
    return df

def increment_recycle():
    global recycle_hour, recycle_minute
    recycle_minute += 15
    if recycle_minute >= 60:
        recycle_minute = 0
        recycle_hour += 1
    if recycle_hour >= 24:
        recycle_hour = 0
    return f"{recycle_hour:02d}:{recycle_minute:02d}"

def get_services_info():
    log_message("Getting services information")
    
    # Get list of federated servers (requires admin privileges)
    servers = gis.admin.servers.list()
    if not servers:
        log_message("No servers found in your portal admin. Ensure you have sufficient privileges.", 'error')
        return
    print_to_file(data=servers, filebasename="servers")
    # print servers record count
    log_message(f"Number of servers: {len(servers)}", 'info')

    for server in servers:
        print_to_file(data=server, filebasename="server")
        # log_message(f"\n--- Server: {server.url} ---", 'debug')
        # List all services on the server
        services = server.services.list()
        if not services:
            log_message("  No services found on this server.", 'error')
            continue
        
        # print the number of services
        log_message(f"Number of services: {len(services)}", 'info')
        
        print_to_file(data=services, filebasename="services")

        for svc in services:
            try:
                # Retrieve the service definition via the service manager
                # definition = svc.manager.get_definition()
                svc_properties = svc.properties
                service_name = svc_properties.serviceName
                service_type = svc_properties.type
                # if service_name != 'Cacao_Cocoa_2030_Suitability_Regions_in_Central_America':
                # continue
                
                log_message(f"Service: {service_name} ({service_type})") #, 'info')
                
                additional_dict = None
                try:
                    service_url = svc.url
                    log_message(f"  Service URL: {service_url}", 'info')
                    additional_dict = {'SERVICE_URL': service_url}
                except Exception as e:
                    log_message(f"Error retrieving service URL: {e}", 'warning')
                
                # get_rest_service_json(service_name, service_type, gis._con.token, server.url)
                
                print_to_file(data=svc_properties, filebasename="service_properties", fileappend=service_name, unique_record_column_name="serviceName", additional_dict=additional_dict)
                
                # Determine instance type:
                #   For shared, minInstances & maxInstances are typically both 0.
                min_inst = svc_properties.get('minInstancesPerNode', 0)
                max_inst = svc_properties.get('maxInstancesPerNode', 0)
                instance_type = "Shared" if max_inst == 0 else "Dedicated"
                
                # Recycle configuration values
                recycle_interval = svc_properties.get('recycleInterval', "Not set")
                recycle_start = svc_properties.get('recycleStartTime', "Not set")
                
                log_message(f"Service: {service_name}")
                log_message(f"  Type: {service_type}")
                log_message(f"  Instance: {instance_type} (minInstances: {min_inst}, maxInstances: {max_inst})")
                log_message(f"  Recycle Interval: {recycle_interval}, Recycle Start Time: {recycle_start}")
                
                # print type of svc
                log_message(f"  svc type: {type(svc)}", 'debug')
                log_message(f"  svc properties type: {type(svc_properties)}", 'debug')
                try:
                    svc_properties_dict = dict(svc_properties)
                except Exception as e:
                    svc_properties_dict = None
                    log_message(f"Error converting svc_properties to dict: {e}", 'warning')
                
                service_type = service_type.lower()
                if service_type not in ['featureserver', 'imageserver', 'mapserver']:
                    continue
                
                updateNeeded = False
                if svc_properties_dict is not None:
                    recycle_time_desired = increment_recycle()
                    if recycle_time_desired != recycle_start:
                        log_message(f"  Updating recycleStartTime to {recycle_time_desired}", 'info')
                        svc_properties_dict['recycleStartTime'] = recycle_time_desired
                        updateNeeded = True
                    if recycle_interval != 264:
                        log_message(f"  Updating recycleInterval to 264", 'info')
                        svc_properties_dict['recycleInterval'] = 264
                        updateNeeded = True
                    # check if lower service_name contains "ethiopia"
                    if 'ethiopia' in service_name.lower():
                        if instance_type != "Shared":
                            log_message(f"  Updating instance type to Shared", 'info')
                            svc_properties_dict['minInstancesPerNode'] = 0
                            svc_properties_dict['maxInstancesPerNode'] = 0
                            updateNeeded = True
                try:
                    if updateNeeded:
                        log_message(f"  Updating service properties", 'info')
                        
                        # NOTE: This worked, but it caused errors on the server!!!!!!
                        # This code requires a restart of the server service.
                        # arcgis_service = AdminService(url=service_url, gis=gis, initialize=True)
                        # res = arcgis_service.edit(svc_properties_dict)
                        # log_message(f"  Service update response: {res}", 'info')
                        
                        '''
                        if service_type == 'featureserver':
                            # use url and gis to get FeatureLayerCollectionManager
                            flc = FeatureLayerCollectionManager(service_url, gis)
                            flc.update_definition({'recycleInterval': 264})
                        elif service_type == 'imageserver':
                            ilc = ImageryLayerCacheManager(service_url, gis)
                            # ilc.update_definition({'recycleInterval': 264})
                            arcgis_service = AdminService(url=service_url, gis=gis, initialize=True)
                            # arcgis_service._recycleInterval = 264
                        elif service_type == 'mapserver':
                            # use url and gis to get MapImageLayerManager
                            milc = MapImageLayerManager(service_url, gis)
                            # milc.update_definition({'recycleInterval': 264})
                        # svc.manager.update_definition({'recycleInterval': 264})
                        # svc_properties['recycleInterval'] = 264
                        '''
                except Exception as e:
                    log_message(f"Error updating Service: {e}", 'error')
                    
                # break
            except Exception as e:
                log_message(f"Error retrieving information from service {svc}: {e}", 'error')
                
def get_rest_service_json(service_name, service_type, token):
    filepath = get_file_path(filebasename="service_rest", fileappend=service_name, extension='json')
    if filepath is None:
        return
    try:
        service_url = f"{rest_url}/{service_name}/{service_type}?f=json&token={token}"
        log_message(f"Service: {service_name} ({service_type})", 'info')
        service_response = requests.get(service_url) # , verify=False)
        service_response.raise_for_status()
        if service_response is not None:
            
            # if service_response can be converted to json
            log_message(f"Service response: {service_response}", 'debug')
            service_response_json = service_response.json()
            # if service_response contains "error" key, log the error
            if 'error' in service_response_json:
                log_message(f"Error in service response: {service_response_json}", 'error')
                return
            
            # log_message(json.dumps(service_response_json, indent=4), 'debug')
            print_to_file(data=service_response_json, filebasename="service_rest", fileappend=service_name, unique_record_column_name="name")
    except Exception as e:
        log_message(f"Error retrieving service definition for {service_name}: {e}", 'error')
    # return service_response_json

def get_rest_services_info(token):
    """
    Fetch the full definitions of all services in ArcGIS Enterprise.
    """
    services_url = f"{rest_url}?f=json&token={token}"
    response = requests.get(services_url) # , verify=False)
    response.raise_for_status()
    services = response.json().get("services", [])
    
    for service in services:
        service_name = service.get("name")
        service_type = service.get("type")
        get_rest_service_json(service_name, service_type, token)

if __name__ == '__main__':
    # log beginning of script
    log_message("Starting script")
    
    rest_url = get_user_input("Enter the ArcGIS REST API URL", "https://maps.rrgnbs.com/arcgisserver/rest/services/")
    portal_url = get_user_input("Enter the portal URL", "https://maps.rrgnbs.com/arcgisportal")
    portal_username = get_user_input("ArcGIS Portal Username (not SSO)", default_value='rrgadmin')
    portal_password = getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    if portal_username == "" or portal_password == "":
        log_message("Username and password are required.", 'error')
        exit(1)
    gis = GIS(portal_url, portal_username, portal_password)
    log_message(f"Connected to portal: {portal_url}")
    
    get_services_info()
    # get_rest_services_info(gis._con.token)
    
    log_message("Script completed")
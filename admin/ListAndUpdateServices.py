# ListAndUpdateServices.py
# By: Julie Tripp
# Date: 05/09/2025
# This script is functional and works correctly as of Enterprise 11.1.0
#
# Adapted from:
#   https://github.com/pheede/ArcGIS-Enterprise-Stuff/blob/master/sharedinstances.py
#   https://github.com/WUSTL-GIS-Programming-spring-2014/classinfo/blob/master/Classes/Class8/ChangeInstances.py
#
import sys
import argparse
import urllib
import logging
import os
from datetime import datetime
import json
import requests

servicesNeedingChange = ['ServieName1', 'ServiceName2', 'ServiceName3']

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filebasename = f'sharedinstances_{timestamp}'
output_directory = os.path.dirname(os.path.abspath(__file__))
output_directory = os.path.join(output_directory, 'Output')
if not os.path.exists(output_directory):
    os.makedirs(output_directory)
log_file_path = os.path.join(output_directory, f'{filebasename}.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(log_file_path, mode='w')
])


def parseInputParameters():
    parser = argparse.ArgumentParser(description='List and optionally update map services in an ArcGIS Server site.')
    parser.add_argument('--server', help='The URL of the ArcGIS Server site to work against. Only built-in authentication is supported.', default='https://gis.example.com/arcgisserver')
    parser.add_argument('--user', help='Username of the administrative account', default='gisadmin')
    parser.add_argument('--password', help='Password of the specified user account.') #, required=True)
    parser.add_argument('--update', action='store_true', help='Specify this parameter to change all Pro-based services from dedicated to shared instances.')
    args = parser.parse_args()
    if not args.password:
        from getpass import getpass
        args.password = getpass(f"**  Enter password for {args.user}: ")
    '''
    if not args.update:
        # ask the user if they want to update the services
        update = input("Do you want to update all the services to shared? (y/n): ")
        if update.lower() == 'y':
            args.update = True
        else:
            args.update = False
    '''
    return args

# A function that checks that the input JSON object is not an error object.    
def assertJsonSuccess(data):
    try:
        obj = json.loads(data)
        if 'status' in obj:
            if obj['status'] == "error":
                logging.error("Error: " + str(obj))
                return False
            elif obj['status'] == "success":
                return True
    except Exception as e:
        print("JSON object is not valid. " + str(e))
    try:
        # check if the word error is in the data as a string
        data_str = str(data)
        if 'error' in data_str:
            logging.error("Error: " + data_str)
            return False
        elif 'success' in data_str:
            return True
    except Exception as e:
        print('Not a valid string. ' + str(e))
    
    # check if data has no content
    if data is None or len(data) == 0:
        logging.error("Error: Object is empty.")
        return False
    
    # logging.error("Error: Unable to determine if success or error.")
    return True

def outputToFile(filename, data):
    try:
        try:
            data_to_output = json.dumps(data, indent=4)
            filename += '.json'
        except Exception as e:
            data_to_output = str(data)
            filename += '.txt'
        with open(os.path.join(output_directory, filename), 'w') as f:
            f.write(data_to_output)
    except Exception as e:
        logging.error("Error writing to file: " + str(e))

def listServices(server):
    arcMapSvcs = []
    dedicatedInstanceSvcs = []
    sharedInstanceSvcs = []
    svcsNeedPropertyUpdate = []
        
    for folder in server.services.folders:
        # skip the system folders
        if folder in ['Hosted', 'DataStoreCatalogs', 'System', 'Utilities']: continue
        
        for service in server.services.list(folder=folder):
            if service.properties['serviceName'] in servicesNeedingChange:
                outputToFile(f"{service.properties['serviceName']}_service_properties", service.properties)
                
            # bug reports suggest that some services don't have a type.. this is odd, but we skip them to avoid a crash
            if 'type' not in service.properties: continue
            
            # # skip everything that's not a map service; we don't support anything else in the shared pool at 10.7.x - 10.9.x
            # if service.properties['type'] != 'MapServer': continue
            if service.properties['type'] not in ['MapServer', 'FeatureServer', 'ImageServer']: continue
            # if service.properties['type'] not in ['ImageServer']: continue
            
            if 'properties' in service.properties:
                if 'path' in service.properties['properties']:
                    if service.properties['properties']['path'] == 'undefined':
                        logging.warning('Path is undefined. ServiceName: ' + service.properties['serviceName'])
            
            # the provider value is case-sensitive!
            if service.properties['provider'] == 'ArcObjects': # provider='ArcObjects' means the service is running under the ArcMap runtime i.e. published from ArcMap
                arcMapSvcs.append(service)
            elif service.properties['provider'] == 'ArcObjects11': # provider='ArcObjects11' means the service is running under the ArcGIS Pro runtime i.e. published from ArcGIS Pro
                dedicatedInstanceSvcs.append(service)
            elif service.properties['provider'] == 'DMaps': # provider='DMaps' means the service is running in the shared instance pool (and thus running under the ArcGIS Pro provider runtime)
                sharedInstanceSvcs.append(service)
            elif service.properties['provider'] == 'ArcObjectsRasterRendering': # provider='ArcObjectsRasterRendering' means the image service is running in the shared instance pool
                sharedInstanceSvcs.append(service)
            else: pass # whoa nelly! unknown type of provider.. must be a fancy new server released after this script was written
    
    logging.info('*** ArcMap services ***')
    if len(arcMapSvcs) == 0:
        logging.info('There are no services published from ArcMap. Impressive!')
    else:
        logging.info('Services from ArcMap not eligible to run in the shared instance pool:')
        for service in arcMapSvcs:
            logging.info(f"- ServiceName: {service.properties['serviceName']}")
            try:
                output_text = f"Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
                logging.info(e)
            
            # imagine what uncommenting this would do..
            #if args.update:
            #   data = urllib.parse.urlencode({ 'token' : service._con.token, 'provider' : 'ArcObjects11', 'f' : 'json' }).encode('ascii')
            #   with urllib.request.urlopen(service.url + '/changeProvider', data) as f:
            #       print(f.read().decode('utf-8'))

    logging.info('*** ArcGIS Pro Shared instance services ***')
    if len(sharedInstanceSvcs) == 0:
        logging.info('There are no services published from ArcGIS Pro that are running in the shared instance pool.')
    else:
        logging.info('Services from ArcGIS Pro already running in the shared instance pool:')
        for service in sharedInstanceSvcs:
            try:
                output_text = f"- ServiceName: '{service.properties['serviceName']}'; Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
                # logging.info('Service instances per node min, max: ' + str(service.properties['minInstancesPerNode']) + ', ' + str(service.properties['maxInstancesPerNode']))
                if service.properties['minInstancesPerNode'] != 0 or service.properties['maxInstancesPerNode'] != 0:
                    # logging.info('Service instances min, max: ' + str(service.properties['properties'].get('minInstances')) + ', ' + str(service.properties['properties'].get('maxInstances')))
                    # logging.info(service.properties['properties'])
                    logging.warning('Shared service has more than 0 min/max instances. Needs to be updated.')
                    if service.properties['serviceName'] in servicesNeedingChange:
                        if args.update:
                            svcsNeedPropertyUpdate.append(service)
                        else:
                            logging.info('Service not updated because script is not in update mode.')
                    else:
                        logging.info('Service not updated because it is not in the list of services needing change.')
                else:
                    logging.info('Service path: ' + service.properties['properties'].get('path'))
                    if service.properties['properties'].get('path') == 'undefined':
                        logging.warning("Path equals 'undefined' for ServiceName: '" + service.properties['serviceName'])
                        if service.properties['serviceName'] in servicesNeedingChange:
                            if args.update:
                                svcsNeedPropertyUpdate.append(service)
                            else:
                                logging.info('Service not updated because script is not in update mode.')
                        else:
                            logging.info('Service not updated because it is not in the list of services needing change.')
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
                logging.info(e)
            
    logging.info('*** ArcGIS Pro Dedicated instance services ***')
    if len(dedicatedInstanceSvcs) == 0:
        logging.info('There are no services published from ArcGIS Pro that are running with dedicated instances.')
    else:
        logging.info('Services from ArcGIS Pro that may be eligible to run in the shared instance pool:')
        for service in dedicatedInstanceSvcs:
            serviceName = service.properties['serviceName']
            logging.info(f"- ServiceName: {serviceName}")
            
            try:
                output_text = f"Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
            
            try:
                # switch Pro-based service to shared instance pool
                if serviceName in servicesNeedingChange:
                    if args.update:
                        # updating the provider can only be done via the dedicated changeProvider operation, it can't be  done by 
                        # simply editing the service properties directly (backwards compatibility concession to avoid older 
                        # ArcGIS Desktop clients from modifying this property incorrectly)
                        # if service is ImageServer, then provider='ArcObjectsRasterRendering' else, if not ImageServer, then provider='DMaps'
                        if service.properties['type'] == 'ImageServer':
                            provider_type = 'ArcObjectsRasterRendering'
                        else:
                            provider_type = 'DMaps'
                        data = urllib.parse.urlencode({ 'token' : service._con.token, 'provider' : provider_type, 'f' : 'json' }).encode('ascii')
                        logging.info(f"Changing provider for '{serviceName}' to '{provider_type}'")
                        with urllib.request.urlopen(service.url + '/changeProvider', data) as f:
                            results = f.read().decode('utf-8')
                            logging.info(results)
                            if assertJsonSuccess(results):
                                logging.info(f"Service '{serviceName}' changed to '{provider_type}' successfully.")
                                svcsNeedPropertyUpdate.append(service)
                            else:
                                logging.error(f"Service '{serviceName}' failed to change to {provider_type}.")
                    else:
                        logging.info('Service not updated because script is not in update mode.')
                else:
                    logging.info('Service not updated because it is not in the list of services needing change.')
            except Exception as e:
                logging.error(f'Error changing provider for {service.properties["serviceName"]}')
                logging.error(e)

    return svcsNeedPropertyUpdate


def changeProperties(services, minInstances=0, maxInstances=0):
    if not args.update:
        logging.info("Script is not in update mode. No properties will be changed.")
        return
    
    if len(services) == 0:
        logging.info("No services need property updates.")
        return
    
    logging.info("Change the properties for a service.")
    
    try:
        # get token from the first record of the services service._con.token
        token = services[0]._con.token
        if token == "":
            logging.error("Could not generate a token.")
            return
    except Exception as e:
        logging.error("Error getting token from the service.")
        logging.error(str(e))
        return
    
    try:
        # This request only needs the token and the response formatting parameter 
        # params = urllib.parse.urlencode({'token': token, 'f': 'json'})
        params = {'token': token, 'f': 'json'}
        headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
                
        for service in services:
            # Get the service name
            serviceName = service.properties['serviceName']
            logging.info("Checking instances for service: '" + serviceName + "'")
            try:
                serviceMinInstancesPerNode = service.properties['minInstancesPerNode']
                serviceMaxInstancesPerNode = service.properties['maxInstancesPerNode']
                logging.info('Service instances per node min, max:' + str(serviceMinInstancesPerNode) + ', ' + str(serviceMaxInstancesPerNode))
                
                serviceMinInstance = service.properties['properties'].get('minInstances')
                serviceMaxInstance = service.properties['properties'].get('maxInstances')
                logging.info('Service instances min, max:' + str(serviceMinInstance) + ', ' + str(serviceMaxInstance))
                
                servicePath = service.properties['properties'].get('path')
                logging.info('Service path: ' + str(servicePath))
                
                if (serviceMinInstancesPerNode != minInstances or serviceMaxInstancesPerNode != maxInstances or servicePath == 'undefined'):
                    serviceURL = service.url
                    
                    # Connect to service to get its current JSON definition 
                    logging.info("Reading service information...")
                    response = requests.post(serviceURL, data=params, headers=headers, verify=False)
                    if (response.status_code != 200):
                        logging.error("Could not read service information.")
                        logging.error(str(response))
                        continue
                        
                    data = response.text
                    
                    # Check that data returned is not an error object
                    if not assertJsonSuccess(data):          
                        logging.error("Error when reading service information. " + str(data))
                        continue
                    else:
                        logging.info("Service information read successfully. Now changing properties...")

                    # Deserialize response into Python object
                    dataObj = json.loads(data)
                    # logging.info("Service information: ")
                    # logging.info(dataObj)
                    outputToFile(f"{service.properties['serviceName']}_rest_service_information", dataObj)
                    
                    if (serviceMinInstancesPerNode != minInstances or serviceMaxInstancesPerNode != maxInstances):
                        logging.info("Changing service instances...")
                        # Edit desired properties of the service
                        dataObj["minInstancesPerNode"] = minInstances
                        dataObj["maxInstancesPerNode"] = maxInstances
                        
                        dataObj["properties"]["minInstances"] = minInstances
                        dataObj["properties"]["maxInstances"] = maxInstances
                    
                    if servicePath == 'undefined':
                        # remove path property from the service
                        logging.info("Removing undefined path property from the service...")
                        if 'path' in dataObj['properties']:
                            del dataObj['properties']['path']

                    # Serialize back into JSON
                    updatedSvcJson = json.dumps(dataObj)

                    # Call the edit operation on the service. Pass in modified JSON.
                    editSvcURL = serviceURL + "/edit"
                    params_edit = {'token': token, 'f': 'json', 'service': updatedSvcJson}
                    editResponse = requests.post(editSvcURL, data=params_edit, headers=headers, verify=False)
                    if (editResponse.status_code != 200):
                        logging.error("Error while executing edit.")
                        logging.error(str(editResponse))
                        continue
                    
                    # Check that data returned is not an error object
                    editData = editResponse.text
                    if not assertJsonSuccess(editData):
                        logging.error("Error returned while editing service: " + str(editData))
                        continue
                    logging.info(f'Response from edit: {editData}')
                    logging.info("Service edited successfully.")
                else:
                    logging.info("Service already has the desired properties.")
            except Exception as e:
                logging.error("Error while changing properties for service: " + serviceName)
                logging.error(str(e))
            
    except Exception as e:
        logging.error('Error while changing properties for service: ' + serviceName)
        logging.error(str(e))

    return


# Main script execution
logging.info('Starting script to list and optionally update map services in an ArcGIS Server site.')

args = parseInputParameters()

logging.info('Connecting to %s...' % args.server)
import arcgis.gis.server

connected = False
try:
    server = arcgis.gis.server.Server(args.server, username=args.user, password=args.password)
    connected = True
except Exception as e:
    logging.error('Error connecting to server: %s' % e)
    sys.exit(1)

logging.info("Connected, enumerating services...")
svcsNeedPropertyUpdate = listServices(server)

if args.update:
    changeProperties(svcsNeedPropertyUpdate, minInstances=0, maxInstances=0)

print('See log file for details: %s' % log_file_path)
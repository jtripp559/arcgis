from getpass import getpass
import os
from arcgis.gis import GIS
import json
# Connect to your ArcGIS Enterprise
username = input("Enter admin username: ")
password = getpass("Enter admin password: ")
gis = GIS("https://gis.example.com/arcgisportal", username, password)
# Get the servers
servers = gis.admin.servers.list()
# Define the file path
export_dir = r"C:\Temp\JSON"
file_path = r"C:\Temp\JSON\service_properties.json"
with open(file_path, "a") as file:
    # Loop through each server
    for server in servers:
        # Get the services
        services = server.services.list()
        # Loop through each service
        for service in services:
            # Get the service properties
            service_properties = service.properties
            # Export service properties to a file
            file.write(str(service_properties) + "\n")
file_path_server_properties = r"C:\Temp\JSON\server_properties.json"
with open(file_path_server_properties, "a") as file_server_properties:
    # Loop through each server
    for server in servers:
        server_properties = server.properties
        # Export server properties to a file
        file_server_properties.write(str(server_properties) + "\n")
        # Loop through each resource in the 'resources' list
        for resource in server.properties['resources']:
            # Define the file path
            file_path = os.path.join(export_dir, f"{resource}_properties.json")
            if hasattr(server, resource):
                # Get the resource properties
                resource_properties = getattr(server, resource)
                # Convert the resource properties to a serializable format
                if hasattr(resource_properties, 'to_dict'):
                    resource_properties = resource_properties.to_dict()
                elif hasattr(resource_properties, 'to_json'):
                    resource_properties = json.loads(resource_properties.to_json())
                # Export resource properties to a file
                with open(file_path, "w") as file:
                    try:
                        json.dump(resource_properties, file)
                    except TypeError:
                        file.write(str(resource_properties))
            else:
                print(f"'Server' object has no attribute '{resource}'")
print('Done!')
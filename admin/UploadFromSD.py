import arcpy
import getpass
from arcgis.gis import GIS
import traceback

def connect_to_portal():
    global portal_url, gis, portal_username
    connected = False
    
    portal_url = "https://maps.rrgnbs.com/arcgisportal"
    portal_username = "rrgadmin"
    portal_password = getpass.getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    if portal_username == "" or portal_password == "":
        print("Missing portal username or password.")
    else:
        try:
            arcpy.SignInToPortal(portal_url, portal_username, portal_password)
            connected = True
            print(f"Connected to {portal_url} as {portal_username}")
        except Exception as e:
            print(f"Failed to connect to {portal_url}: {e}")
            print(traceback.format_exc())
        try:
            gis = GIS(portal_url, portal_username, portal_password)
        except Exception as e:
            print(f"Failed to connect to arcgis: {e}")
            print(traceback.format_exc())
    return connected

connected = connect_to_portal()
if connected:
    sd_output_filepath = r"T:\ArcGISDataset\Water Balance Tool\ArcGIS Pro\WaterBalanceTool\Staging\Population_Density_BasinATLAS_Level9_sqkm_yr2020.sd"
    federated_server_url = "https://maps.rrgnbs.com/arcgisserver"
    try:
        print("Start Publishing")
        arcpy.UploadServiceDefinition_server(sd_output_filepath, federated_server_url)
        print(f"Finished Publishing")
    except Exception as e:
        print(f"Failed to upload service: {e}")
        print(traceback.format_exc())
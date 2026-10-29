import arcpy
import traceback
import getpass

# Define the path to your AOI feature class and output geodatabase
workspace_full_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_WaterBalance_sde.sde"
aoi_feature_class = f"{workspace_full_path}/SDE.RRG_L0BASINATLAS_V10_LEV09"
portal_url="https://maps.rrgnbs.com/arcgisportal"

# Define the input parameters
# input_raster = "https://worldpop.arcgis.com/arcgis/rest/services/WorldPop_Total_Population_100m/ImageServer"
input_raster = r"T:\ArcGISDataset\Rasters\WorldPop\1km\ppp_2020_1km_Aggregated.tif"
# point_feature_class = f"{workspace_full_path}/sde.WorldPopTotPop100m2000_2020"
point_feature_class = f"{workspace_full_path}/sde.WorldPopTotPop1km2020Pts"
raster_field = "Value"

spatial_join_output = None
summary_table = None

try:
    # Set the workspace to your enterprise geodatabase connection
    arcpy.env.workspace = workspace_full_path
    print(f"Workspace set to {workspace_full_path}")
except Exception as e:
    print(f"Failed to set the workspace to {workspace_full_path}: {e}", 'error')
    env_set = False

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
    
def connect_to_portal():
     #global portal_url, portal_username, gis
    connected = False
    
    # Get portal URL from the user or default to 'https://maps.rrgnbs.com/arcgisportal'
     #portal_url = get_user_input("ArcGIS portal URL", default_value='https://maps.rrgnbs.com/arcgisportal', value_to_check=portal_url)
    
    # Get portal_username and password from the user
    # portal_username = get_user_input("ArcGIS Portal Username (not SSO)", default_value='rrgadmin', value_to_check=portal_username)
    portal_username = 'rrgadmin'
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
        '''
        try:
            gis = GIS(portal_url, portal_username, portal_password)
        except Exception as e:
            print(f"Failed to connect to arcgis: {e}")
        '''
    return connected

def copy_raster_to_workspace(image_server_url, output_raster_name=None):
    workspace_raster_path = None
    
    if output_raster_name == "" or output_raster_name is None:
        # get output_raster_name from image_server_url
        # it's the words between the last '/' and the 2nd to last '/'
        output_raster_name = image_server_url.split('/')[-2]
        output_raster_name = 'sde.' + output_raster_name
        
    # Define the output raster path in the geodatabase
    workspace_raster_path = f"{workspace_full_path}/{output_raster_name}"
    
    # check if workspace_raster_path exists
    if arcpy.Exists(workspace_raster_path):
        print(f"Raster {output_raster_name} already exists in the geodatabase.")
        return workspace_raster_path
    
    try:
        # Create a raster object from the image server URL
        print(f"Creating raster object from {image_server_url}...")
        raster = arcpy.Raster(image_server_url)
        
        # Save the raster to the geodatabase
        print(f"Saving raster to {workspace_raster_path}...")
        raster.save(workspace_raster_path)
        
        print("Raster downloaded and saved successfully.")
        return workspace_raster_path
    except arcpy.ExecuteError:
        tb = traceback.format_exc()
        error_message = f"Geoprocessing error: {arcpy.GetMessages(2)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return None
    except Exception as ex:
        tb = traceback.format_exc()
        error_message = f"An error occurred: {str(ex)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return None


def RasterToPoint(in_raster_path):
    try:
        # Convert Raster to Points
        print("Converting raster to points...")
        arcpy.conversion.RasterToPoint(
            in_raster=in_raster_path,
            out_point_features=point_feature_class,
            raster_field=raster_field
        )
        print("Raster converted to points successfully.")
        return "Raster converted to points successfully.", 0
    except arcpy.ExecuteError:
        tb = traceback.format_exc()
        error_message = f"Geoprocessing error: {arcpy.GetMessages(2)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1
    except Exception as ex:
        tb = traceback.format_exc()
        error_message = f"An error occurred: {str(ex)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1

def SpatialJoin():
    global spatial_join_output
    try:
        # Perform Spatial Join
        spatial_join_output = f"{workspace_full_path}/SDE.Basin_WorldPop_SpatialJoin"
        print("Performing spatial join...")
        arcpy.analysis.SpatialJoin(
            target_features=aoi_feature_class,
            join_features=point_feature_class,
            out_feature_class=spatial_join_output,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="INTERSECT"
        )
        print("Spatial Join completed successfully.")
        return "Spatial Join completed successfully.", 0
    except arcpy.ExecuteError:
        tb = traceback.format_exc()
        error_message = f"Geoprocessing error: {arcpy.GetMessages(2)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1
    except Exception as ex:
        tb = traceback.format_exc()
        error_message = f"An error occurred: {str(ex)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1

def SummaryStatistics():
    global summary_table
    try:
        # Summary Statistics
        summary_table = f"{workspace_full_path}/SDE.Basin_WorldPop_SummaryStats"
        print("Calculating summary statistics...")
        arcpy.analysis.Statistics(
            in_table=spatial_join_output,
            out_table=summary_table,
            statistics_fields=[[raster_field, "SUM"]],
            case_field="OBJECTID"  # Replace with the unique identifier field of your AOI polygons
        )
        print("Summary Statistics completed successfully.")
        return "Summary Statistics completed successfully.", 0
    except arcpy.ExecuteError:
        tb = traceback.format_exc()
        error_message = f"Geoprocessing error: {arcpy.GetMessages(2)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1
    except Exception as ex:
        tb = traceback.format_exc()
        error_message = f"An error occurred: {str(ex)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1

def JoinField():
    try:
        # Join the Summary Statistics Table Back to AOIs
        print("Joining summary statistics back to AOIs...")
        arcpy.management.JoinField(
            in_data=aoi_feature_class,
            in_field="OBJECTID",  # Replace with the unique identifier field of your AOI polygons
            join_table=summary_table,
            join_field="OBJECTID",  # Replace with the unique identifier field of your AOI polygons
            fields=["SUM_Value"]
        )
        print("Join Summary Statistics completed successfully.")
        return "Join Summary Statistics completed successfully.", 0
    except arcpy.ExecuteError:
        tb = traceback.format_exc()
        error_message = f"Geoprocessing error: {arcpy.GetMessages(2)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1
    except Exception as ex:
        tb = traceback.format_exc()
        error_message = f"An error occurred: {str(ex)}\nTraceback: {tb}"
        arcpy.AddError(error_message)
        return error_message, 1
		
def calculate_population_within_aoi():
    workspace_raster_path = copy_raster_to_workspace(input_raster, "sde.WorldPopTotPop1km2020")
    print(workspace_raster_path)
    if workspace_raster_path is None:
        exit()
    
    result_msg, err_cnt = RasterToPoint(workspace_raster_path)
    # result_msg, err_cnt = RasterToPoint(input_raster)
    print(result_msg)
    
    if err_cnt == 0:
        result_msg, err_cnt = SpatialJoin()
        print(result_msg)
        
    if err_cnt == 0:
        result_msg, err_cnt = SummaryStatistics()
        print(result_msg)
        
    '''
    if err_cnt == 0:
        result_msg, err_cnt = JoinField()
        print(result_msg)
    '''
        
    if err_cnt == 0:
        print("Population calculation completed successfully.")
        
    return "Population calculation completed successfully."
	
connected_to_portal = connect_to_portal()
if not connected_to_portal:
    exit()

result = calculate_population_within_aoi()
print(result)
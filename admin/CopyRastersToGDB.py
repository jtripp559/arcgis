# -*- coding: utf-8 -*-

import arcpy, os
import logging
from datetime import datetime
from getpass import getpass

# workspace_full_path = r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde"
workspace_full_path = ''
workspace_paths = {
    'W': r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde",
    'M': r"D:\GenericArcGISConnectionsDir\ORG_DB2_sde.sde",
    'B': r"D:\GenericArcGISConnectionsDir\ORG_Generic_sde.sde",
    'G': r"D:\GenericArcGISConnectionsDir\ORG_DB4_sde.sde",
    'C': r"D:\GenericArcGISConnectionsDir\ORG_DB1_sde.sde"
}
connected_to_arcgis = False


# init logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = os.path.dirname(os.path.realpath(__file__))
log_dir = os.path.join(log_dir, "output")
if not os.path.exists(log_dir):
    os.mkdir(log_dir)
log_file = os.path.join(log_dir, f"CopyRastersToGDB_{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.DEBUG, format='%(message)s')

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

def init_arcpy():
    global workspace_full_path
    try:
        arcpy.env.mask = r"D:\GenericArcGISDataDir\GIS\General GIS Data\Worldwide\World.shp"
        arcpy.env.cellSize = "MINOF"
        arcpy.env.overwriteOutput = True
        
        # ask the user which sde to use (ORG or DB2)
        sde_path = get_user_input("Which DB will you be importing into? (OPTIONS - W: ORG_WS, M: ORG_DB2, C: ORG_DB1, G: ORG_Gen_Ref, B: ORG_Generic)")
        sde_path = sde_path.upper().strip()[0]
        workspace_full_path = workspace_paths.get(sde_path, workspace_full_path)
        if workspace_full_path == '' or workspace_full_path is None:
            # ask user to enter the full path
            workspace_full_path = get_user_input("Enter the full path to the workspace")
        if workspace_full_path == '' or workspace_full_path is None or (not os.path.exists(workspace_full_path)):
            log_message(f"Workspace {workspace_full_path} does not exist.", 'error')
            return False
        
        arcpy.env.workspace = workspace_full_path
    except Exception as e:
        log_message(f"Error initializing arcpy: {e}", 'error')
        return False

def list_raster_files(directory):
    raster_files_list = []
    for root, dirs, files in os.walk(directory):
        for file in files: 
            extension = ''
            if file.endswith('.tif'):
                extension = '.tif'
            elif file.endswith('.tiff'):
                extension = '.tiff'
            elif file.endswith('.crf'):
                extension = '.crf'
            if extension != '':
                file_path = os.path.join(root, file)
                db_name = os.path.basename(file).replace(extension, '')
                raster_files_list.append((file_path, db_name))
    return raster_files_list
        
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
    global connected_to_arcgis
    if connected_to_arcgis:
        return True
    
    # global arcgis_url, base_url, selected_portal, filename_base, gis, arcgis_username, arcgis_password
    connected = False

    # ArcGIS Online
    arcgis_url_agol = 'https://myorg.maps.arcgis.com'
    base_url_agol = 'https://services.arcgis.com/cb1XtHtD3d6ZWNAQ/arcgis/rest/services'
    # Old ArcGIS Enterprise
    arcgis_url_ent = 'https://gis2.example.com/portal'
    base_url_ent = 'https://gis2.example.com/server/rest/services'
    # New ArcGIS Enterprise
    arcgis_url_org = 'https://gis.example.com/arcgisportal'
    base_url_org = 'https://gis.example.com/arcgisserver/rest/services/'
    
    which_portal = get_user_input("Which ArcGIS portal (AGOL, ENT, ORG)", default_value='ORG')
    which_portal = which_portal.upper()
    if which_portal.startswith('A'):
        arcgis_url = arcgis_url_agol
        # base_url = base_url_agol
        # selected_portal = 'AGOL'
    elif which_portal.startswith('R'):
        arcgis_url = arcgis_url_ent
        # base_url = base_url_ent
        # selected_portal = 'ENT'
    else:
        arcgis_url = arcgis_url_org
        # base_url = base_url_org
        # selected_portal = 'ORG'
    
    # # Get ArcGIS URL from the user or default to 'https://gis.example.com/arcgisportal'
    # arcgis_url = get_user_input("ArcGIS URL", default_value=arcgis_url)
    
    # Get arcgis_username and password from the user
    arcgis_username = get_user_input("ArcGIS Username (not SSO)", default_value='gisadmin')
    arcgis_password = getpass(f"**  ArcGIS Password for {arcgis_username}: ")
    if arcgis_username == "" or arcgis_password == "":
        print("Missing username or password.")
    else:
        try:
            arcpy.SignInToPortal(arcgis_url, arcgis_username, arcgis_password)
            connected = True
            print(f"Connected to {arcgis_url} as {arcgis_username}")
        except Exception as e:
            print(f"Failed to connect to {arcgis_url} using arcpy: {e}")
        '''
        try:
            gis = GIS(arcgis_url, arcgis_username, arcgis_password)
            connected = True
            print(f"Connected to {arcgis_url} using GIS")
        except Exception as e:
            print(f"Failed to connect to {arcgis_url} using GIS: {e}")
        '''
    connected_to_arcgis = connected
    return connected
    
# List tifs to compress
log_message("Getting raster files...")
rasterList = [
    (r"D:\GenericArcGISDataDir\OutputDir1\GFW\GFW_gain.tif", "GFW_gain"),
    (r"D:\GenericArcGISDataDir\OutputDir1\GFW\GFW_lossyear.tif", "GFW_lossyear")
]
'''
rasterList = [
    ("https://utility.arcgis.com/usrsvcs/servers/e118b42854084a12ac94ec87907e460a/rest/services/Runoff_december_tif/ImageServer", "Runoff_december_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/d3d7e87cbd614b47a3d30b8734929491/rest/services/Runoff_february_tif/ImageServer", "Runoff_february_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/121d06f8709446cab2ddbb008f0cf910/rest/services/Runoff_january_tif/ImageServer", "Runoff_january_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/5cd92009366246f2a6db03e7ba05b4a7/rest/services/Runoff_july_tif/ImageServer", "Runoff_july_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/739a5ab5ed1d4ac8abf441cf9633c4ab/rest/services/Runoff_june_tif/ImageServer", "Runoff_june_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/d84c9965f634400c9053d53d39be84f4/rest/services/Runoff_march_tif/ImageServer", "Runoff_march_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/86ce9e2796e84c2783f07cea10ffec7d/rest/services/Runoff_may_tif/ImageServer", "Runoff_may_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/17111bfa0d434bf4907278194165cf3d/rest/services/Runoff_november_tif/ImageServer", "Runoff_november_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/8256f15c07944d2d9e192fb5fe7b1882/rest/services/Runoff_october_tif/ImageServer", "Runoff_october_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/6295225ac8fa43fb8d0d4f75e252aae0/rest/services/Runoff_september_tif/ImageServer", "Runoff_september_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/20447dd5ed63453f89a289fc4776c218/rest/services/Runoff_total_tif/ImageServer", "Runoff_total_tif"),
    ("https://utility.arcgis.com/usrsvcs/servers/a19e1e2eef154330bc1e43c811d2e53d/rest/services/Cumulative_change_in_SM/ImageServer", "SHBAAM_sm_Change"),
    ("https://utility.arcgis.com/usrsvcs/servers/3bc6a393b8a44ccba120248b8788fb4c/rest/services/Tree_cover_gain_GFW/ImageServer", "GFW_gain")
]
'''

'''
rasterList = list_raster_files(r'D:\GenericArcGISDataDir\OutputDir1\CHELSA\1WorldWide\V2\Tas\Scaled\CF\Monthly\2041-2070')
rasterList.extend(list_raster_files(r'D:\GenericArcGISDataDir\OutputDir1\CHELSA\1WorldWide\V2\Tasmin\Scaled\CF\Monthly\2041-2070'))
rasterList.extend(list_raster_files(r'D:\GenericArcGISDataDir\OutputDir1\CHELSA\1WorldWide\V2\Tasmax\Scaled\CF\Monthly\2041-2070'))
rasterList.extend(list_raster_files(r'D:\GenericArcGISDataDir\OutputDir1\CHELSA\1WorldWide\V2\Pr\Scaled\CF\Monthly\2011-2040'))
rasterList.extend(list_raster_files(r'D:\GenericArcGISDataDir\OutputDir1\CHELSA\1WorldWide\V2\Pr\Scaled\CF\Monthly\2041-2070'))
'''

init_arcpy()

log_message(f"Processing {len(rasterList)} raster files")
for raster, db_name in rasterList:
    # if raster has http, then connect to ArcGIS
    if raster.startswith('http'):
        if not connect_to_arcgis():
            log_message("Failed to connect to ArcGIS", 'error')
            exit()
    
    # outName = os.path.basename(raster).replace('.tif','').replace('-','_')
    db_name = db_name.replace('-','_')
    log_message(f"Processing {db_name}")
    # outRaster = r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde\SDE.{}".format(db_name)
    db_name = f"SDE.{db_name}"
    outRaster = os.path.join(workspace_full_path, db_name)
    if arcpy.Exists(outRaster):
        log_message(f"{db_name} already exists.")
        outRasterExists = True
    else:
        try:
            arcpy.management.CopyRaster(
                in_raster=raster,
                out_rasterdataset=outRaster,
                config_keyword="",
                background_value=None,
                nodata_value="",
                onebit_to_eightbit="NONE",
                colormap_to_RGB="NONE",
                pixel_type="32_BIT_FLOAT",
                scale_pixel_value="NONE",
                RGB_to_Colormap="NONE",
                format="GRID",
                transform="NONE",
                process_as_multidimensional="CURRENT_SLICE",
                build_multidimensional_transpose="NO_TRANSPOSE"
            )
            outRasterExists = True
            log_message(f"Raster {db_name} copied")
        except Exception as e:
            log_message(f"Failed to CopyRaster: {e}", 'error')
            outRasterExists = False
    if outRasterExists:
        try:
            log_message(f"Building pyramids for {db_name}")
            arcpy.management.BuildPyramids(in_raster_dataset=outRaster,
                                            pyramid_level="-1",
                                            SKIP_FIRST="NONE",
                                            resample_technique="BILINEAR",
                                            compression_type="DEFAULT",
                                            compression_quality=75,
                                            skip_existing="SKIP_EXISTING")
            log_message("Pyramids built")
        except arcpy.ExecuteError:
            log_message(f"Error building pyramids: {arcpy.GetMessages(2)}", 'error')
        except Exception as e:
            log_message(f"Failed to build pyramids: {e}", 'error')

        try:
            log_message(f"Calculating statistics for {db_name}")
            arcpy.management.CalculateStatistics(outRaster)
            log_message("Statistics calculated")
        except arcpy.ExecuteError:
            log_message(f"Error calculating statistics: {arcpy.GetMessages(2)}", 'error')
        except Exception as e:
            log_message(f"Failed to calculate statistics: {e}", 'error')

        log_message(f"Changing privileges for {db_name}")
        try:
            arcpy.management.ChangePrivileges(
                in_dataset=outRaster,
                user="data editor",
                View="GRANT",
                Edit="GRANT"
            )
        except Exception as e:
            log_message(f"Failed to change privileges for data editor: {e}", 'error')
        try:
            arcpy.management.ChangePrivileges(
                in_dataset=outRaster,
                user="data creator",
                View="GRANT",
                Edit="GRANT"
            )
        except Exception as e:
            log_message(f"Failed to change privileges for data creator: {e}", 'error')
        try:
            arcpy.management.ChangePrivileges(
                in_dataset=outRaster,
                user="data viewer",
                View="GRANT",
                Edit="AS_IS"
            )
        except Exception as e:
            log_message(f"Failed to change privileges for data viewer: {e}", 'error')

log_message("Rasters copy completed")

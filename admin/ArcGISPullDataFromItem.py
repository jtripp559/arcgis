'''
Name: ArcGISPullDataFromItem.py
Developed by: Julie Tripp
Date: 10/09/2024

Purpose: This script is used to pull data from ArcGIS items and export it to a JSON file.

NOTES:
Upload ShapeFile to DB Example:
arcpy.conversion.FeatureClassToGeodatabase(
    Input_Features=r"T:/GenericArcGISDataDir/Rasters/OutputDir1/CHELSA/ChangePrecipitationTemperature.shp;T:/GenericArcGISDataDir/Rasters/OutputDir1/Berghuijs/Global_Recharge_Fraction_mm_y_Berghuijs_2022_Filled.shp",
    Output_Geodatabase=r"T:/GenericArcGISDataDir/Enterprise/Connections/ORG_DB5_sde.sde"
)

'''

import json
import getpass
import os
from arcgis.gis import GIS
from arcgis.features import FeatureLayer
from arcgis.raster import ImageryLayer
import traceback
import arcpy
import pandas as pd
from datetime import datetime
import logging

arcpy.env.mask = r"D:\GenericArcGISDataDir\GIS\General GIS Data\Worldwide\World.shp"
arcpy.env.cellSize = "MINOF"
arcpy.env.overwriteOutput = True

raster_upload_db = r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde"

item_list = ['2622d0346e264f469d02d3b59212845e']

# test image service
# item_list = ['d661328987b146b68334767f7d4ebe66']

# test feature service
# item_list=['ab2738976fb94550a04422966094b6dc']

# item_list = ["2609b456ec6c4d8c805f7c17624b67f6","d10558978be24d40bdf28a8f15521219","648a4e2db14941c9b428245b37baa9e3","648a4e2db14941c9b428245b37baa9e3","5574f5e8217a46f98767ac4760e9e9fa","cad78e963fe94d9f8bc2ffd34db8260d","8578f8863c914e6fb57f10bdd4490768","c00584f61aae416ca57caab9b9ce2a03","c00584f61aae416ca57caab9b9ce2a03","ab2738976fb94550a04422966094b6dc","ddeb8e4d87d24080b23197844020dbf7","1606a57a44fc4470bc93148438c4542c","2622d0346e264f469d02d3b59212845e","2622d0346e264f469d02d3b59212845e","1c1285a724bf4073b2722d7050c22859","1c1285a724bf4073b2722d7050c22859","1c1285a724bf4073b2722d7050c22859","abe5ad25d4c74ec391b8e79c4aef4af3","4370fb97053a42f5bf53ef007300f525","482c4900b41b4e558f0223eb6f28b6c3","10fb584e6ff64f868cfc6f2862c1ff81","10fb584e6ff64f868cfc6f2862c1ff81","7b2f176ba2994e7d8a05c4ce8a8ce06c","7b2f176ba2994e7d8a05c4ce8a8ce06c","01c42f64dba94a108758991136a7b320","fab2272bb1b042d68326e6729360404e","7d957709dbea4c1bace1c00b585280bd","7d957709dbea4c1bace1c00b585280bd","800fee5a8d014438a1e1ef87566e7587","c615ea4a462b4164a29228f6c442e85b","d066021654134017aafee5814bf02dc6","27e5aa16a4544db0a69c3a2d941ec93b","365734726d6c4ec0989203919ed4b568","a1f77cfd20834f349ad0a18ae5c610fb","6e770b7c78b2430b93b1c97738005967","10b99891bef74ed692ab45ddaf737668","da9433008ea24353924e13fc41fea690","583f85dfdd7547cf9a5479abb6f61ba2","e118b42854084a12ac94ec87907e460a","d3d7e87cbd614b47a3d30b8734929491","121d06f8709446cab2ddbb008f0cf910","5cd92009366246f2a6db03e7ba05b4a7","739a5ab5ed1d4ac8abf441cf9633c4ab","d84c9965f634400c9053d53d39be84f4","86ce9e2796e84c2783f07cea10ffec7d","17111bfa0d434bf4907278194165cf3d","8256f15c07944d2d9e192fb5fe7b1882","6295225ac8fa43fb8d0d4f75e252aae0","20447dd5ed63453f89a289fc4776c218","d661328987b146b68334767f7d4ebe66","0103291b98d14045b43820248b6c1105","3bc6a393b8a44ccba120248b8788fb4c","6ce3dcaf52ae4e248ac9cb60367467c8","a2106cf00dca410eb36457b900428800","b6461445e52c4605b069c6e199d40699","a19e1e2eef154330bc1e43c811d2e53d","5bd3ec4005224070984861c721184cb7","5cf177cdacae4de0bf2affbfeda91d34","355cfc8857794188bbcd95659a77b0f4","858bee49015a4e57824f51a7127ba65d","db2212b8669d4726adc9aca383f49968","46fa7d7b25834bd48357ce4e472446e7","46fa7d7b25834bd48357ce4e472446e7","46fa7d7b25834bd48357ce4e472446e7"]

arcgis_url = ''
base_url = ''
has_logging = False

filename_base = 'ArcGIS_Items'

timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

selected_portal = None

gis = None
token = None
arcgis_username = None
arcgis_password = None
max_arcgis_items = 10000

# will store the results exported file paths by item id
results_dict = {}

def log(message, level='info', print_message=True):
    log_message = message
    if level == 'warning':
        log_message = f"WARNING: {message}"
    elif level == 'error':
        log_message = f"ERROR: {message}"
    if print_message:
        print(log_message)
    if has_logging:
        if level == 'info':
            logging.info(log_message)
        elif level == 'warning':
            logging.warning(log_message)
        elif level == 'error':
            logging.error(log_message)

def init_logging():
    global has_logging
    try:
        current_dir = os.path.dirname(__file__)
    except:
        current_dir = os.getcwd()
    output_dir = current_dir
    # if os.path.exists(os.path.join(current_dir, 'Output')):
    output_dir = os.path.join(current_dir, 'Output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    # change output_dir to selected_portal directory within Output
    output_dir = os.path.join(output_dir, selected_portal)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # ask the user if they'd like to use the default output directory or specify a different one
    output_dir = get_user_input("Output directory", default_value=output_dir)
    
    log_file_path = os.path.join(output_dir, f"{filename_base}_{timestamp}.log")
    logging.basicConfig(filename=log_file_path, level=logging.INFO)
    
    has_logging = True
    
    log("Output directory: " + output_dir)
    return output_dir

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
    log(f"{prompt}: {user_input}")
    return user_input

def connect_to_arcgis():
    global arcgis_url, base_url, selected_portal, filename_base, gis, arcgis_username, arcgis_password
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
        base_url = base_url_agol
        selected_portal = 'AGOL'
    elif which_portal.startswith('R'):
        arcgis_url = arcgis_url_ent
        base_url = base_url_ent
        selected_portal = 'ENT'
    else:
        arcgis_url = arcgis_url_org
        base_url = base_url_org
        selected_portal = 'ORG'
    filename_base = f'{filename_base}_{selected_portal}'
    
    # Get arcgis_username and password from the user
    arcgis_username = get_user_input("ArcGIS Username (not SSO)", default_value='gisadmin')
    arcgis_password = getpass.getpass(f"**  ArcGIS Password for {arcgis_username}: ")
    if arcgis_username == "" or arcgis_password == "":
        log("Missing username or password.", level='error')
    else:
        try:
            arcpy.SignInToPortal(arcgis_url, arcgis_username, arcgis_password)
            connected = True
            log(f"Connected to {arcgis_url} as {arcgis_username}")
        except Exception as e:
            log(f"Failed to connect to {arcgis_url} using arcpy: {e}", level='error')
        try:
            gis = GIS(arcgis_url, arcgis_username, arcgis_password, verify_cert=False)
            connected = True
            log(f"Connected to {arcgis_url} using GIS")
        except Exception as e:
            log(f"Failed to connect to {arcgis_url} using GIS: {e}", level='error')
            log(traceback.format_exc())
    return connected

def export_json_to_file(json_data, output_dir, filename):
    if json_data is not None:
        try:
            if (not isinstance(json_data, dict)) and (not isinstance(json_data, list)):
                if hasattr(json_data, 'to_dict'):
                    json_data = json_data.to_dict()
        except Exception as e:
            json_data = json_data
            
        try:
            if isinstance(json_data, dict) or isinstance(json_data, list):
                filename = filename + '.json'
                filepath = os.path.join(output_dir, filename)
                with open(filepath, 'w') as f:
                    json.dump(json_data, f, indent=4)
            else:
                filename = filename + '.txt'
                filepath = os.path.join(output_dir, filename)
                with open(filepath, 'w') as f:
                    if isinstance(json_data, str):
                        # If it's a string, write it as-is
                        f.write(json_data)
                    else:
                        # For other data types, convert to string before writing
                        f.write(str(json_data))
            log('Exported to ' + filepath)
        except Exception as e:
            log(f"Failed to export JSON to file '{filename}': {e}", level='error')
            log(traceback.format_exc())

def export_feature_by_layers(item, output_dir):
    global results_dict
    try:
        log(f"Exporting feature layer(s) to shapefiles '{item.url}'")
        # get layers from item
        layers = item.layers
        item_url = item.url
        feature_title = item_url.split('/')[-2]
        
        # get a list of layer urls to use in FeatureClassToShapefile
        layer_urls = [f"{item_url}/{layer.properties.id}" for layer in layers]
        
        # Convert the list of URLs to a semicolon-separated string
        input_features = ";".join(layer_urls)
        log(f"Input features: {input_features}")
        
        # Use arcpy.conversion.FeatureClassToShapefile to export the feature layers to shapefiles
        output_path = os.path.join(output_dir, f"{feature_title}")
        # mkdir
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        arcpy.conversion.FeatureClassToShapefile(Input_Features=input_features, Output_Folder=output_path)
        
        log(f"Exported feature layer(s) to {output_path}")
        results_dict[item.id]['export_path'] = output_path
    except Exception as e:
        log(f"Failed to export feature layer(s) to shapefiles '{item_url}': {e}", level='error')
        log(traceback.format_exc())

def export_feature_layer(item, output_dir, downloadFormat='Shapefile'):
    global results_dict
    if item is None:
        return
    if item.type != 'Feature Service':
        return
    feature_title = item.url.split('/')[-2]
    log(f"Exporting feature layer '{feature_title}' to {downloadFormat}")
    try:
        # Note: this downloads as a ZIP file
        result = item.export('sample {}'.format(item.type), downloadFormat)
        output_path = os.path.join(output_dir, f'{feature_title}.shp')
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        result.download(output_path)
        result.delete()
        log(f"Exported feature layer to {output_path}")
        results_dict[item.id]['export_path'] = output_path
    except Exception as e:
        # log(f"Failed to export feature layer '{feature_title}': {e}", level='error')
        # log(traceback.format_exc())
        
        export_feature_by_layers(item, output_dir)

def export_image_layer(imagery_layer):
    global results_dict
    image_url = imagery_layer.url
    # image_title = imagery_layer.title
    # get image title from image_url from the 2nd to last part split by '/'
    image_service_title = image_url.split('/')[-2]
    log(f"Exporting imagery '{image_service_title}'")
    db_path = os.path.join(raster_upload_db, f"SDE.{image_service_title}")
    if arcpy.Exists(db_path):
        log(f"{image_service_title} already exists.", level='warning')
    else:
        try:
            # raster = arcpy.Raster(image_url)
            arcpy.management.CopyRaster(
                in_raster=image_url,
                out_rasterdataset=db_path,
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
            log(f"Exported image from {image_url} to {db_path}")
            results_dict[item.id]['export_path'] = db_path
            
            '''
            # Note: Selection feature from D:\GenericArcGISDataDir\GIS\General GIS Data\Worldwide\World.shp
            arcpy.management.DownloadRasters(
                in_image_service=image_url,
                out_folder=output_dir,
                where_clause="1=1",
                selection_feature='-179.999988541 -58.4986090379999 179.999988541 83.6236001620001 GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
                clipping="CLIPPING",
                convert_rasters="ALWAYS_CONVERT",
                format="TIFF",
                compression_method="NONE",
                compression_quality=None,
                MAINTAIN_FOLDER="MAINTAIN_FOLDER"
            )
            '''
            '''
            tiff_path = os.path.join(output_dir, filename + '.tif')
            export_params = {
                'bbox': None,
                'image_sr': None,
                'bbox_sr': None,
                'size': None,
                'dpi': None,
                'image_format': 'tiff',
                'pixel_type': None,
                'no_data': None,
                'no_data_interpretation': None,
                'interpolation': None,
                'compression': None,
                'adjust_aspect_ratio': None,
                'lerc_version': None,
                'rendering_rule': None,
                'mosaic_rule': None,
                'time': None,
                'out_path': tiff_path
            }
            imagery_layer.export_image(**export_params)
            # log(f'Exported imagery to {output_dir}')
            '''
        except Exception as e:
            log(f"Failed to export imagery to TIFF '{image_url}': {e}", level='error')
            log(traceback.format_exc())
        
def get_data(item_id):
    global gis, results_dict
    item = None
    if gis is None:
        return None
    try:
        item = gis.content.get(item_id)
        
        # Initialize the dictionary for the item_id if it doesn't exist
        if item_id not in results_dict:
            results_dict[item_id] = {}
        
        export_json_to_file(item, output_dir, f"{filename_base}_{item_id}_get")  
        # add output_dir, f"{filename_base}_{item_id}_get" to results_dict as get_export_path
        results_dict[item_id]['get_export_path'] = os.path.join(output_dir, f"{filename_base}_{item_id}_get.json")
        
        item_get_data = item.get_data()
        export_json_to_file(item_get_data, output_dir, f"{filename_base}_{item_id}_getdata")
        
        # add output_dir, f"{filename_base}_{item_id}_getdata" to results_dict as getdata_export_path
        results_dict[item_id]['getdata_export_path'] = os.path.join(output_dir, f"{filename_base}_{item_id}_getdata.json")
        
        '''
        zip_file_path = os.path.join(output_dir, f"{filename_base}_{item_id}.zip")
        item.download(save_path=zip_file_path)
        if os.path.exists(zip_file_path):
            log(f"Downloaded data to {zip_file_path}")
        '''
        item_type = item.get('type')
        item_url = item.get('url')
        log(f"Item type: {item_type}")
        log(f"Item URL: {item_url}")
        
        if item_type == 'Feature Service':
            # feature_layer = FeatureLayer(item_url)
            # export_feature_layer_to_shapefile(feature_layer, output_dir, f"{filename_base}_{item_id}_feature")
            # export_feature_layer(item, output_dir, f"{filename_base}_{item_id}_feature")
            export_feature_layer(item, output_dir)
        elif item_type == 'Image Service':
            # export_image_layer(ImageryLayer(item_url), output_dir, f"{filename_base}_{item_id}_imagery")
            # export_image_layer(item, output_dir, f"{filename_base}_{item_id}_imagery")
            export_image_layer(item)
        
    except Exception as e:
        log(f"Failed to get data for item {item_id}: {e}", level='error')
        log(traceback.format_exc())
    return item

connected_to_arcgis = connect_to_arcgis()
if not connected_to_arcgis:
    log("Failed to connect to ArcGIS", level='error')
    exit()

output_dir = init_logging()

log(f"Processing {len(item_list)} items")
for item in item_list:
    log(f"Getting data for item {item}")
    get_data(item)
    log(f"Completed getting data for item {item}")

# log(results_dict)
# save results_dict to file flattened to csv
results_file_path = os.path.join(output_dir, f"{filename_base}_{timestamp}")
export_json_to_file(results_dict, output_dir, f"{filename_base}")
results_df = pd.json_normalize(results_dict, sep='.')
results_df.to_csv(f"{results_file_path}.csv", index=False)

log(f"Exported results to {results_file_path}")

if has_logging:
    logging.shutdown()
    print('See log file for details')

print('Finished processing items')

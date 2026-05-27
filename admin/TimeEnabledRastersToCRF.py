'''
TimeEnabledRastersToCRF.py

Developed by: Julie Tripp
Date:  11/19/2024

Description:
This script creates a CRF file from a Mosaic Dataset in a folder.

User Variables:
1) datasets: List of dictionaries containing the following:
    - mosaicdataset_name: Name to be used for the Mosaic Dataset in the workspace
    - variable_field_value: Value to be used for the Variable Field in the Mosaic Dataset
    - variable_field_description: Description to be used for the Variable Field in the Mosaic Dataset
    - variable_field_units: Units to be used for the Variable Field in the Mosaic Dataset
    - raster_input_path: Could be a folder or a list of specific rasters
        * Folder: All rasters in the folder will be added to the Mosaic Dataset
            - raster_input_sub_folder_action: options: "NO_SUBFOLDERS", "SUBFOLDERS"
        * List: Only the specified rasters will be added to the Mosaic Dataset
2) arcpy.env.workspace: Workspace where the Mosaic Dataset will be created
3) crf_output_dir: Directory where the CRF files will be saved
4) raster_input_sub_folder_action: options: "NO_SUBFOLDERS", "SUBFOLDERS"
5) raster_input_duplicate_items_action: options: "ALLOW_DUPLICATES", "EXCLUDE_DUPLICATES", "OVERWRITE_DUPLICATES"
6) add_missing_rasters: Boolean to add missing rasters to the Mosaic Dataset
    - If True, the script will attempt to add raster to the Mosaic Dataset even if the Mosaic Dataset already exists
    - If False, the script will skip adding the rasters to the Mosaic Dataset if it already exists


Workflow:
1) Set the workspace
2) Loop through the specified datasets
    a) Create Mosaic Dataset in the workspace, if it does not already exist
    b) Add Rasters to Mosaic Dataset, if add_missing_rasters is True or the Mosaic Dataset did not exist
    c) Add Fields to Mosaic Dataset
        - Fields:
            * Variable (Text) = variable_field_value
            * StdTime (Date) = calculated from the Name field in the Mosaic Dataset
    d) Build Multidimensional Info
    e) Copy Raster to CRF

Raster naming convention:
    StdTime is parsed from the raster Name field by splitting on underscores.
    Supported patterns:
        *_YYYY        -> January 1 of YYYY         (e.g. ETAW_mm_2002)
        *_YYYY_MM     -> First of month YYYY-MM    (e.g. Pe_mm_2002_06)
    Rasters that do not match one of these patterns will fail StdTime
    calculation and the multidimensional info will be incomplete.

'''
import arcpy
import os
import logging
import datetime
import traceback

# Variables

# NOTE: if the workspace is not set, a new File Geodatabase will be created in the Output directory
arcpy.env.workspace = r"D:\GenericArcGISConnectionsDir\ORG_DB5_sde.sde"
# NOTE: if crf_output_dir is not set, the CRF files will be saved in the Output directory
crf_output_dir = r"D:\GenericTool1Dir\CRFS"

# NOTE: raster_input_path below, could be list of specific rasters not just an entire folder
# e.g. raster_input_path = r"D:\GenericTool1Dir\ETAW\Annual\ETAW_mm_2002.tif;D:\GenericTool1Dir\ETAW\Annual\ETAW_mm_2003.tif"
datasets = [
    {
        "mosaicdataset_name": "DeepPerc_AW_SW_Annual",
        "variable_field_value": "'Deep Percolation of AW SW'",
        "variable_field_description": "'Deep Percolation of AW SW'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\Deep_AW_SW\Annual"
    },
    {
        "mosaicdataset_name": "Pe_Annual",
        "variable_field_value": "'Effective Precipitation (Pe)'",
        "variable_field_description": "'Effective Precipitation (Pe)'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\Pe\Annual"
    },
    {
        "mosaicdataset_name": "ETAW_Annual",
        "variable_field_value": "'ET of Applied Water'",
        "variable_field_description": "'Evapotranspiration of Actual Water'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\ETAW\Annual"
    },
    {
        "mosaicdataset_name": "Pe_Monthly",
        "variable_field_value": "'Effective Precipitation (Pe)'",
        "variable_field_description": "'Effective Precipitation (Pe)'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\Pe\Monthly"
    },
    {
        "mosaicdataset_name": "DeepPerc_AW_SW_Monthly",
        "variable_field_value": "'Deep Percolation of AW SW'",
        "variable_field_description": "'Deep Percolation of AW SW'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\Deep_AW_SW\Monthly"
    },
    {
        "mosaicdataset_name": "ETAW_Monthly",
        "variable_field_value": "'ET of Applied Water'",
        "variable_field_description": "'Evapotranspiration of Actual Water'",
        "variable_field_units": "'mm'",
        "raster_input_path": r"D:\GenericTool1Dir\ETAW\Monthly"
    }
]

# These variables probably won't change
raster_input_sub_folder_action = "SUBFOLDERS" # options: "NO_SUBFOLDERS", "SUBFOLDERS"
raster_input_duplicate_items_action = "EXCLUDE_DUPLICATES" # options: "ALLOW_DUPLICATES", "EXCLUDE_DUPLICATES", "OVERWRITE_DUPLICATES"

add_missing_rasters = False

pixel_types = {"U1": "1_BIT",
               "U2": "2_BIT",
               "U4": "4_BIT",
               "S8": "8_BIT_SIGNED",
               "U8": "8_BIT_UNSIGNED",
               "S16": "16_BIT_SIGNED",
               "U16": "16_BIT_UNSIGNED",
               "S32": "32_BIT_SIGNED",
               "U32": "32_BIT_UNSIGNED",
               "F32": "32_BIT_FLOAT",
               "F64": "64_BIT"}


        
date_code_block = """from datetime import datetime
def calculate_date(name):
    year_month = name.split('_')[-1]
    if len(year_month) == 4:
        date_string = year_month + '/01/01'
    else:
        year, month = name.split('_')[-2], name.split('_')[-1]
        date_string = year + '/' + month + '/01'
    return datetime.strptime(date_string, '%Y/%m/%d')"""

timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# These variables will be set in the loop
mosaicdataset_name = ""
variable_field_value = ""
variable_field_description = ""
variable_field_units = ""
raster_input_path = ""

# initialize logging
# set the output_dir to the Output directory within the script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(current_dir, 'Output')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
log_file_path = os.path.join(output_dir, f'TimeEnabledData_{timestamp}.log')
logging.basicConfig(filename=log_file_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def log_message(message, level='info'):
    print(message)
    if level == 'info':
        logging.info(message)
    elif level == 'warning':
        logging.warning(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'critical':
        logging.critical(message)
    elif level == 'debug':
        logging.debug(message)

# Functions
def prepend_text(prepend_text, name):
    """Return name with prepend_text at the front if not already present."""
    if name.find(prepend_text) == -1:
        name = prepend_text + name
    return name

def find_mosaic_dataset(dataset_name):
    """Return True if a Mosaic Dataset matching dataset_name exists in the workspace.

    dataset_name is automatically prefixed with 'SDE.' to match enterprise
    geodatabase naming.
    """
    log_message("Search if the Mosaic Dataset already exists")
    dataset_name = prepend_text("SDE.", dataset_name)
    mosaicdatasets = arcpy.ListDatasets("*", "MosaicDataset")
    for mosaicdataset in mosaicdatasets:
        if mosaicdataset == dataset_name:
            log_message("Mosaic Dataset already exists")
            return True
    log_message("Mosaic Dataset does not exist")
    return False

def create_moasic_dataset(dataset_name):
    """Create a Mosaic Dataset if it does not already exist.

    Returns:
         1 = newly created
         0 = already existed, no action taken
        -1 = CreateMosaicDataset call succeeded but dataset still not found
        -2 = CreateMosaicDataset raised an exception
    """
    return_value = 0
    if not find_mosaic_dataset(dataset_name):
        log_message("Create Mosaic Dataset")
        try:
            arcpy.management.CreateMosaicDataset(
                in_workspace=arcpy.env.workspace,
                in_mosaicdataset_name=dataset_name,
                coordinate_system='GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
                num_bands=None,
                pixel_type="",
                product_definition="NONE",
                product_band_definitions=None
            )
            if not find_mosaic_dataset(dataset_name):
                log_message("Failed to create Mosaic Dataset")
                return -1
            return_value = 1
            log_message("Mosaic Dataset created")
        except Exception as e:
            log_message(f"Failed to create Mosaic Dataset: {dataset_name}", 'error')
            log_message(e, 'error')
            return -2
    return return_value

def add_rasters_to_moasic_dataset(dataset_name):
    """Add rasters from raster_input_path (module global) to the Mosaic Dataset.

    Uses the sub-folder and duplicate-items actions configured at the top of
    the script. Returns True on success, False if AddRastersToMosaicDataset
    raises.
    """
    try:
        # Construct the cache location path dynamically
        # Get the current user's home directory
        user_dir = os.path.expanduser("~")
        # e.g. "C:\Users\JulieTripp\AppData\Local\ESRI\rasterproxies\SDE.ETAW_Annual"
        cache_location = os.path.join(user_dir, "AppData", "Local", "ESRI", "rasterproxies", dataset_name)

        log_message("Add Rasters to Mosaic Dataset")
        arcpy.management.AddRastersToMosaicDataset(
            in_mosaic_dataset=dataset_name,
            raster_type="Raster Dataset",
            input_path=raster_input_path,
            update_cellsize_ranges="UPDATE_CELL_SIZES",
            update_boundary="UPDATE_BOUNDARY",
            update_overviews="NO_OVERVIEWS",
            maximum_pyramid_levels=None,
            maximum_cell_size=0,
            minimum_dimension=1500,
            spatial_reference=None,
            filter="",
            sub_folder=raster_input_sub_folder_action,
            duplicate_items_action=raster_input_duplicate_items_action,
            build_pyramids="BUILD_PYRAMIDS",
            calculate_statistics="CALCULATE_STATISTICS",
            build_thumbnails="BUILD_THUMBNAILS",
            operation_description="",
            force_spatial_reference="NO_FORCE_SPATIAL_REFERENCE",
            estimate_statistics="ESTIMATE_STATISTICS",
            aux_inputs=None,
            enable_pixel_cache="NO_PIXEL_CACHE",
            cache_location=cache_location
        )
        log_message("Rasters added to Mosaic Dataset")
        return True
    except Exception as e:
        log_message(f"Failed to add Rasters to Mosaic Dataset: {raster_input_path}", 'error')
        log_message(e, 'error')
        return False


def add_fields_to_mosaic_dataset(dataset_name):
    """Populate the Variable and StdTime fields on the Mosaic Dataset Footprint.

    Variable is set from variable_field_value (module global). StdTime is
    calculated from the Name field using date_code_block. Returns True on
    success, False if a CalculateField call raises.
    """
    # add two new Text fields to the Footprint of the Mosaic Dataset: Variable and Date
    try:
        log_message("Add Fields to Mosaic Dataset")
        
        mosaic_layer = "temp_" + dataset_name + "_" + timestamp
        arcpy.management.MakeMosaicLayer(dataset_name, mosaic_layer)
        
        mosaic_footprint = mosaic_layer + "\\Footprint"
        
        field_names_to_add = {"Variable": "TEXT", "StdTime": "DATE"}
        
        # field_names_to_add = ["Variable", "StdTime"]
        # for field_name in field_names_to_add:
        for field_name, field_type in field_names_to_add.items():
            if field_name == "Variable":
                log_message("Calculate Field: " + field_name)
                arcpy.management.CalculateField(
                    in_table=mosaic_footprint,
                    field=field_name,
                    expression=variable_field_value,
                    expression_type="PYTHON3",
                    code_block="",
                    field_type="TEXT",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )
            elif field_name == "StdTime":
                log_message("Calculate Field: " + field_name)
                arcpy.management.CalculateField(
                    in_table=mosaic_footprint,
                    field=field_name,
                    expression="calculate_date(!Name!)",
                    expression_type="PYTHON3",
                    code_block=date_code_block,
                    field_type="DATE",
                    enforce_domains="NO_ENFORCE_DOMAINS"
                )
            else:
                log_message("Field already exists: " + field_name)
    except Exception as e:
        log_message(f"Failed to add Fields to Mosaic Dataset: {dataset_name}", 'error')
        log_message(e, 'error')
        return False
    
    try:
        # close or release the Mosaic Layer
        arcpy.management.Delete(mosaic_layer)
    except Exception as e:
        log_message(f"Failed to delete Mosaic Layer: {mosaic_layer}", 'error')
        
    log_message("Fields added to Mosaic Dataset")
    return True

# Main

if len(datasets) == 0:
    log_message("Nothing to process")
    exit()

log_message("Process started")
run_start = datetime.datetime.now()

# Outcome counters for end-of-run summary
total_datasets = len(datasets)
created_count = 0
skipped_existing_crf = 0
failed_count = 0

if arcpy.env.workspace is None or arcpy.env.workspace == "":
    log_message("Creating a new File Geodatabase")
    gdb_path = os.path.join(output_dir, 'Output', f'TimeEnabledRasters_{timestamp}.gdb')
    arcpy.management.CreateFileGDB(os.path.dirname(gdb_path), os.path.basename(gdb_path))
    log_message(f"File Geodatabase created at: {gdb_path}")
    arcpy.env.workspace = gdb_path

for idx, dataset in enumerate(datasets, start=1):
    dataset_start = datetime.datetime.now()
    mosaicdataset_name = dataset.get("mosaicdataset_name")
    variable_field_value = dataset.get("variable_field_value")
    variable_field_description = dataset.get("variable_field_description")
    variable_field_units = dataset.get("variable_field_units")
    raster_input_path = dataset.get("raster_input_path")
    
    log_message("*" * 50)
    log_message(f"[{idx}/{total_datasets}] Processing Mosaic Dataset: {mosaicdataset_name}")
    
    # if variable fields do not have apostrophes, add them
    if not variable_field_value.startswith("'"):
        variable_field_value = "'" + variable_field_value + "'"
    if not variable_field_description.startswith("'"):
        variable_field_description = "'" + variable_field_description + "'"
    if not variable_field_units.startswith("'"):
        variable_field_units = "'" + variable_field_units + "'"
    
    if crf_output_dir is None or crf_output_dir == "":
        crf_output_dir = output_dir
    out_crf_path = os.path.join(crf_output_dir, mosaicdataset_name + ".crf")
    
    if os.path.exists(out_crf_path):
        log_message(f"CRF file already exists: {out_crf_path}")
        skipped_existing_crf += 1
        continue

    moasic_dataset_created = create_moasic_dataset(mosaicdataset_name)
    if moasic_dataset_created < 0:
        failed_count += 1
        continue
    sde_mosaicdataset = prepend_text("SDE.", mosaicdataset_name)

    if moasic_dataset_created == 1 or add_missing_rasters:
        success = add_rasters_to_moasic_dataset(sde_mosaicdataset)
        if not success:
            failed_count += 1
            continue

    success = add_fields_to_mosaic_dataset(sde_mosaicdataset)
    if not success:
        failed_count += 1
        continue

    variable_desc_units = variable_field_value + ' ' + variable_field_description + ' ' + variable_field_units
    try:
        log_message("Build Multidimensional Info")
        arcpy.md.BuildMultidimensionalInfo(
            in_mosaic_dataset=sde_mosaicdataset,
            variable_field="Variable",
            dimension_fields="StdTime Date Years",
            variable_desc_units=variable_desc_units,
            delete_multidimensional_info="NO_DELETE_MULTIDIMENSIONAL_INFO"
        )
        log_message("Multidimensional Info built")
    except Exception as e:
        log_message(f"Failed to build Multidimensional Info for Mosaic Dataset: {sde_mosaicdataset}", 'error')
        log_message(e, 'error')
        failed_count += 1
        continue

    try:
        log_message("Get Pixel Type of Mosaic Dataset")
        inRaster = arcpy.Raster(sde_mosaicdataset)
        rasterInfo = inRaster.getRasterInfo()
        pixel_type = rasterInfo.getPixelType()
        log_message(f"Pixel Type: {pixel_type}")
        pixel_type_description = pixel_types.get(pixel_type, "32_BIT_FLOAT")
    except Exception as e:
        log_message(f"Failed to get Pixel Type of Mosaic Dataset: {sde_mosaicdataset} — defaulting to 32_BIT_FLOAT", 'error')
        log_message(e, 'error')
        pixel_type_description = "32_BIT_FLOAT"

    try:
        log_message("Copy Raster to CRF")
        arcpy.management.CopyRaster(
            in_raster=sde_mosaicdataset,
            out_rasterdataset=out_crf_path,
            config_keyword="",
            background_value=None,
            nodata_value="",
            onebit_to_eightbit="NONE",
            colormap_to_RGB="NONE",
            pixel_type=pixel_type_description,
            scale_pixel_value="NONE",
            RGB_to_Colormap="NONE",
            format="CRF",
            transform="NONE",
            process_as_multidimensional="ALL_SLICES",
            build_multidimensional_transpose="NO_TRANSPOSE"
        )
        log_message(f"Raster copied to CRF: {out_crf_path}")
        created_count += 1
    except Exception as e:
        log_message(f"Failed to copy Raster to CRF {out_crf_path}", 'error')
        log_message(e, 'error')
        failed_count += 1
        continue

    # CRF is already valid at this point — pyramid/stats failures are logged
    # as warnings but don't flip the dataset to "failed" in the summary.
    try:
        log_message(f"Building pyramids for {mosaicdataset_name}")
        arcpy.management.BuildPyramids(
            in_raster_dataset=out_crf_path,
            pyramid_level="-1",
            SKIP_FIRST="NONE",
            resample_technique="BILINEAR",
            compression_type="DEFAULT",
            compression_quality=75,
            skip_existing="SKIP_EXISTING"
        )
        log_message("Pyramids built")
    except arcpy.ExecuteError:
        log_message(f"Error building pyramids: {arcpy.GetMessages(2)}", 'warning')
        log_message(f"Traceback: {traceback.format_exc()}", 'warning')
    except Exception as e:
        log_message(f"Failed to build pyramids: {e}", 'warning')
        log_message(f"Traceback: {traceback.format_exc()}", 'warning')

    try:
        log_message(f"Calculating statistics for {mosaicdataset_name}")
        arcpy.management.CalculateStatistics(out_crf_path)
        log_message("Statistics calculated")
    except arcpy.ExecuteError:
        log_message(f"Error calculating statistics: {arcpy.GetMessages(2)}", 'warning')
        log_message(f"Traceback: {traceback.format_exc()}", 'warning')
    except Exception as e:
        log_message(f"Failed to calculate statistics: {e}", 'warning')
        log_message(f"Traceback: {traceback.format_exc()}", 'warning')

    dataset_elapsed = datetime.datetime.now() - dataset_start
    log_message(f"[{idx}/{total_datasets}] {mosaicdataset_name} done in {dataset_elapsed}")

# End-of-run summary
run_elapsed = datetime.datetime.now() - run_start
log_message("=" * 50)
log_message("Process completed")
log_message(f"Total datasets:          {total_datasets}")
log_message(f"  CRFs created:          {created_count}")
log_message(f"  Skipped (CRF exists):  {skipped_existing_crf}")
log_message(f"  Failed:                {failed_count}")
log_message(f"Total elapsed time:      {run_elapsed}")
log_message(f"Log file:                {log_file_path}")

if created_count > 0:
    log_message("-" * 50)
    log_message("Next step: Share the newly created CRF file(s) to the ArcGIS Portal")
    log_message("using the Share as Web Layer tool with the following settings:")
    log_message("  - Configuration > Layers > Imagery > Image Service Properties >")
    log_message("       1) Check 'Pixels'")
    log_message("       2) Add 0s to Max Image Size")
    log_message("       3) Check 'Has Live Data'")
    log_message("       4) Layer Drawing must be 'Dynamically from data'")
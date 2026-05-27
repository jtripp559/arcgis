'''
feature_to_rasters.py

Description:
Converts feature layer tables (with geometry, year, and value columns) to
per-year GeoTIFF rasters on the T: drive, in the naming convention expected
by TimeEnabledRastersToCRF.py.

Output naming: {prefix}_{year}.tif  (e.g., GW_OverUnder_Berghuijs_2002.tif)
The trailing _YYYY is required for the CRF script's date parser.

Required source feature class fields:
    year   - integer/numeric; used for yearly grouping and output filename
    value  - numeric; rasterized as the cell value (FeatureToRaster `field`)
    SHAPE  - polygon geometry in WGS 84 (EPSG:4326)

After running this script, add the output folders as dataset entries in
TimeEnabledRastersToCRF.py to create CRFs for ArcGIS Enterprise.
'''

import arcpy
import os
import logging
import datetime

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
sde_conn = r"D:\GenericArcGISConnectionsDir\ORG_Generic_sde.sde"

# Cell size in degrees (WGS 84). Matches existing rasters (e.g., ETAW_mm)
# 0.00833333 deg ~ 1 km (30 arc-seconds) at equator.
cell_size = 0.00833333376793981

datasets = [
    {
        "feature_class": "sde.GROUNDWATER_OVER_UNDER_BASINATLAS_BERGHUIJS",
        "output_dir": r"D:\GenericArcGISDataDir\OutputDir1\Generic\GW_OverUnder_Berghuijs\Annual",
        "output_prefix": "GW_OverUnder_Berghuijs",
    },
    {
        "feature_class": "sde.GROUNDWATER_OVER_UNDER_BASINATLAS_PCR_GLOBWB2",
        "output_dir": r"D:\GenericArcGISDataDir\OutputDir1\Generic\GW_OverUnder_PCR_GLOBWB2\Annual",
        "output_prefix": "GW_OverUnder_PCR_GLOBWB2",
    },
]

# -----------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
current_dir = os.path.dirname(os.path.abspath(__file__))
log_output_dir = os.path.join(current_dir, 'Output')
if not os.path.exists(log_output_dir):
    os.makedirs(log_output_dir)
log_file_path = os.path.join(log_output_dir, f'feature_to_rasters_{timestamp}.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_message(message, level='info'):
    print(message)
    getattr(logging, level, logging.info)(message)


def log_separator(char='=', width=60):
    # Write a blank line + separator to both console and log (no literal \n in file)
    print('')
    print(char * width)
    logging.info('')
    logging.info(char * width)


REQUIRED_FIELDS = ("year", "value")


def validate_fields(fc_path):
    # Return list of missing required fields (case-insensitive); empty list = all present
    existing = {f.name.lower() for f in arcpy.ListFields(fc_path)}
    return [f for f in REQUIRED_FIELDS if f.lower() not in existing]

# -----------------------------------------------------------------------
# ArcPy environment setup
# -----------------------------------------------------------------------
# Ensure output rasters use WGS 84 (matches source feature class SRID 4326)
arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(4326)

# Set a consistent global extent so all yearly rasters align
# (matches the bounding box from the source feature class spatial index)
arcpy.env.extent = arcpy.Extent(-180, -55.9875000004, 180.0006429038, 83.6256427763)

# Use T: drive for scratch to avoid filling C: drive
arcpy.env.scratchWorkspace = r"D:\GenericArcGISDataDir\Scratch"

# Prevent arcpy from cancelling long-running geoprocessing over SDE
arcpy.env.autoCancelling = False

# Overwrite disabled — we use skip logic for existing files instead
arcpy.env.overwriteOutput = False

# -----------------------------------------------------------------------
# Processing
# -----------------------------------------------------------------------
start_time = datetime.datetime.now()
log_message(f"Started: {start_time}")
log_message(f"Log file: {log_file_path}")
log_message(f"SDE connection: {sde_conn}")
log_message(f"Cell size: {cell_size} degrees")
log_message(f"Output CRS: WGS 84 (EPSG:4326)")
log_message(f"Scratch workspace: {arcpy.env.scratchWorkspace}")

# Create scratch workspace if it doesn't exist
if not os.path.exists(arcpy.env.scratchWorkspace):
    os.makedirs(arcpy.env.scratchWorkspace)

totals = {"created": 0, "skipped": 0, "failed": 0}

for ds_idx, dataset in enumerate(datasets, start=1):
    fc_path = os.path.join(sde_conn, dataset["feature_class"])
    ds_output_dir = dataset["output_dir"]
    prefix = dataset["output_prefix"]
    ds_start = datetime.datetime.now()
    
    log_separator()
    log_message(f"Dataset {ds_idx}/{len(datasets)}: {dataset['feature_class']}")
    log_message(f"Output dir: {ds_output_dir}")
    
    # Create output directory if it doesn't exist
    if not os.path.exists(ds_output_dir):
        os.makedirs(ds_output_dir)
        log_message(f"  Created directory: {ds_output_dir}")

    # Validate required fields up front so we fail fast with a clear message
    try:
        missing = validate_fields(fc_path)
    except Exception as e:
        log_message(f"  FAILED to inspect fields on {fc_path}: {e}", 'error')
        continue
    if missing:
        log_message(
            f"  FAILED: missing required field(s) {missing} on {dataset['feature_class']}. "
            f"Expected: {list(REQUIRED_FIELDS)}", 'error'
        )
        continue

    # Get distinct years using SQL for performance (avoids scanning all rows)
    try:
        log_message("  Querying distinct years...")
        years = set()
        with arcpy.da.SearchCursor(fc_path, ["year"], sql_clause=(None, "GROUP BY year")) as cursor:
            for row in cursor:
                if row[0] is not None:
                    years.add(row[0])
        years = sorted(years)
        log_message(f"  Found {len(years)} years: {years[0]} - {years[-1]}")
    except Exception as e:
        # Fallback: GROUP BY may not be supported on all SDE connections
        log_message(f"  GROUP BY query failed ({e}), falling back to full scan...", 'warning')
        try:
            years = set()
            with arcpy.da.SearchCursor(fc_path, ["year"]) as cursor:
                for row in cursor:
                    if row[0] is not None:
                        years.add(row[0])
            years = sorted(years)
            log_message(f"  Found {len(years)} years: {years[0]} - {years[-1]}")
        except Exception as e2:
            log_message(f"  FAILED to query years: {e2}", 'error')
            continue
        
    success_count = 0
    skip_count = 0
    fail_count = 0
    total_years = len(years)

    for idx, year in enumerate(years, start=1):
        out_tif = os.path.join(ds_output_dir, f"{prefix}_{year}.tif")
        progress = f"[{idx}/{total_years}]"

        if os.path.exists(out_tif):
            log_message(f"  {progress} Skipping {year} - already exists")
            skip_count += 1
            continue

        log_message(f"  {progress} Converting year {year}...")
        step_start = datetime.datetime.now()
        layer_name = f"temp_{prefix}_{year}"
        
        try:
            # Create a temporary feature layer with only this year's data
            arcpy.management.MakeFeatureLayer(
                fc_path,
                layer_name,
                where_clause=f"year = {year}"
            )
            
            # Get feature count for this year
            feat_count = int(arcpy.management.GetCount(layer_name)[0])
            log_message(f"    Features: {feat_count}")
            
            if feat_count == 0:
                log_message(f"    WARNING: No features for year {year}, skipping", 'warning')
                skip_count += 1
                continue
            
            # Convert features to raster
            arcpy.conversion.FeatureToRaster(
                in_features=layer_name,
                field="value",
                out_raster=out_tif,
                cell_size=cell_size
            )
            
        except Exception as e:
            log_message(f"    FAILED: {e}", 'error')
            fail_count += 1
            # Clean up partial output so skip logic doesn't ignore it on re-run
            if os.path.exists(out_tif):
                try:
                    arcpy.management.Delete(out_tif)
                    log_message(f"    Cleaned up partial output: {out_tif}")
                except Exception:
                    log_message(f"    WARNING: Could not remove partial file: {out_tif}", 'warning')
                    
        finally:
            # Clean up temp layer and in-memory data
            if arcpy.Exists(layer_name):
                arcpy.management.Delete(layer_name)
            arcpy.management.Delete("in_memory")
            
        try:
            # Verify output
            if os.path.exists(out_tif):
                # Build pyramids and statistics for performance
                arcpy.management.BuildPyramids(out_tif)
                arcpy.management.CalculateStatistics(out_tif)
                
                file_size_mb = os.path.getsize(out_tif) / (1024 * 1024)
                elapsed = (datetime.datetime.now() - step_start).total_seconds()
                log_message(f"    Done: {file_size_mb:.1f} MB, {elapsed:.1f}s")
                success_count += 1
            else:
                log_message(f"    WARNING: Output file not found after conversion", 'warning')
                fail_count += 1
                
        except Exception as e:
            log_message(f"    FAILED: {e}", 'error')
            fail_count += 1
            
    ds_elapsed = (datetime.datetime.now() - ds_start).total_seconds()
    log_message(
        f"  Summary for {prefix}: {success_count} created, {skip_count} skipped, "
        f"{fail_count} failed (elapsed {ds_elapsed:.1f}s)"
    )
    totals["created"] += success_count
    totals["skipped"] += skip_count
    totals["failed"] += fail_count

log_separator()
total_elapsed = (datetime.datetime.now() - start_time).total_seconds()
log_message(
    f"Overall totals across {len(datasets)} dataset(s): "
    f"{totals['created']} created, {totals['skipped']} skipped, {totals['failed']} failed"
)
log_message(f"Completed in {total_elapsed:.1f}s")
log_message(f"Log saved to: {log_file_path}")

# -----------------------------------------------------------------------
# Next step: Add these entries to TimeEnabledRastersToCRF.py datasets:
#
#   {
#       "mosaicdataset_name": "GW_OverUnder_Berghuijs_Annual",
#       "variable_field_value": "'Total Unexploited / Overdrafted Groundwater (Berghuijs)'",
#       "variable_field_description": "'Total Unexploited / Overdrafted Groundwater (Berghuijs)'",
#       "variable_field_units": "'mm'",
#       "raster_input_path": r"D:\GenericArcGISDataDir\OutputDir1\Generic\GW_OverUnder_Berghuijs\Annual"
#   },
#   {
#       "mosaicdataset_name": "GW_OverUnder_PCR_GLOBWB2_Annual",
#       "variable_field_value": "'Total Unexploited / Overdrafted Groundwater (PCR-GLOBWB2)'",
#       "variable_field_description": "'Total Unexploited / Overdrafted Groundwater (PCR-GLOBWB2)'",
#       "variable_field_units": "'mm'",
#       "raster_input_path": r"D:\GenericArcGISDataDir\OutputDir1\Generic\GW_OverUnder_PCR_GLOBWB2\Annual"
#   },
# -----------------------------------------------------------------------

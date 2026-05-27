import arcpy
import logging

# Set up logging
logging.basicConfig(
    filename='projectAllGDBFeatures.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Path to the workspace (SDE connection file)
workspace = r"D:\GenericArcGISConnectionsDir\ORG_DB4_sde.sde"

# Define the WGS_1984 spatial reference
wgs84_spatial_ref = arcpy.SpatialReference(4326)  # EPSG code for WGS_1984

logging.info(f"Starting the projection of datasets in the workspace.")

# List all datasets in the workspace
arcpy.env.workspace = workspace
datasets = arcpy.ListFeatureClasses()  # List feature classes in the workspace

# Iterate through each dataset
for dataset in datasets:
    # Get the full path of the dataset
    dataset_path = f"{workspace}\\{dataset}"

    # Describe the dataset to get its spatial reference
    spatial_ref = arcpy.Describe(dataset_path).spatialReference

    # Check if the spatial reference is not WGS_1984
    if spatial_ref.name != "GCS_WGS_1984":
        # Define the output dataset with "_WGS84" appended
        out_dataset = f"{dataset_path}_WGS84"
        
        # check if out_dataset already exists
        if arcpy.Exists(out_dataset):
            logging.warning(f"Output dataset {out_dataset} already exists. Skipping projection.")
            continue
        
        logging.info(f"Reprojecting {dataset} to {out_dataset}")
        try:
            arcpy.management.Project(
                in_dataset=dataset_path,
                out_dataset=out_dataset,
                out_coor_system=wgs84_spatial_ref
            )
        except Exception as e:
            logging.error(f"Error projecting {dataset}: {e}")

logging.info(f"Projection completed for all datasets in the workspace.")
import arcpy
import os
import arcpy.server
from getpass import getpass
import logging

toolbox_path = r"D:\GenericArcGISDataDir\Data Science Scripts\Geoprocessing tools\Unpublished_Tools.atbx"
web_tool_name = "TDriveTest"

sddraft_dir = r"D:\GenericArcGISDataDir\Data Science Scripts\Drafts"
federated_server_url = 'https://gis.example.com/arcgisserver'
enterprise_version = "11.2"

# initialize variables
sddraft_path = os.path.join(sddraft_dir, f"{web_tool_name}.sddraft")

def init_logging():
    log_file_path = os.path.join(os.path.dirname(__file__), 'Output')
    if not os.path.exists(log_file_path):
        os.makedirs(log_file_path)
    log_file_path = os.path.join(log_file_path, 'PublishGPTool.log')

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Stream (console) handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_formatter = logging.Formatter('%(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

def connect_to_portal():
    connected = False
    portal_url = "https://gis.example.com/arcgisportal"
    portal_username = "gisadmin"

    portal_password = getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    try:
        # Sign in to portal
        arcpy.SignInToPortal(portal_url, portal_username, portal_password)
        logging.info(f"Signed in to {portal_url} as {portal_username}")
        connected = True
    except Exception as e:
        logging.error(f"Error signing in to portal: {e}")
    return connected

def run_gp_tool():
    success = False
    try:
        logging.info("Running the GP tool...")
        # 1. Run your script tool so you get a Result object
        toolboxModule = arcpy.ImportToolbox(input_file=toolbox_path, module_name='UnpublishedTools')
        # NOTE: example of using parameters with the toolboxModule
        # parameters = toolboxModule.TDriveTest_UnpublishedTools.getParameterInfo()
        # parameters[0].value = "TDriveTest"
        # parameters[1].value = "https://gis.example.com/arcgisserver"
        # tool_result = arcpy.TDriveTest_UnpublishedTools(parameters)
        tool_result = arcpy.TDriveTest_UnpublishedTools()
        success = True
        logging.info("Tool executed successfully")
        logging.info(tool_result)
        logging.info(f'Messages: {arcpy.GetMessages(0)}')
    except arcpy.ExecuteError:
        logging.error('Error running the tool')
        logging.error(arcpy.GetMessages(2))         # message type 2 = errors
        logging.error(arcpy.GetMessages(1))         # message type 1 = warnings
    except Exception as e:
        logging.error('Error running the tool')
        logging.error(e)
        logging.error(arcpy.GetMessages(2))         # message type 2 = errors
        logging.error(arcpy.GetMessages(1))         # message type 1 = warnings
    finally:
        return success, tool_result

def create_sddraft(tool_result):
    success = False
    try:
        logging.info("Creating SDDraft...")
        # 2. Build the sharing draft
        # https://pro.arcgis.com/en/pro-app/latest/arcpy/sharing/geoprocessingsharingdraft-class.htm
        sddraft = arcpy.sharing.CreateSharingDraft(
                    server_type="FEDERATED_SERVER",   # or "STANDALONE_SERVER"
                    service_type="WEB_TOOL",
                    service_name= web_tool_name,
                    draft_value=[tool_result])
        sddraft.overwriteExistingService = True
        sddraft.targetServer = federated_server_url
        sddraft.summary     = web_tool_name
        sddraft.description = sddraft.summary
        sddraft.tags        = "test"
        sddraft.serverFolder = ""
        sddraft.portalFolder = ""
        sddraft.convertFeatureLayerURL = False
        sddraft.copyDataToServer = False
        sddraft.executionType = "Asynchronous"
        sddraft.capabilities = "Uploads"
        
        # remove the sddraft_path if it exists
        if os.path.exists(sddraft_path):
            os.remove(sddraft_path)
            logging.info(f"Removed existing SDDraft")

        # 3. Export to SDDraft
        logging.info("Exporting SDDraft...")
        sddraft.exportToSDDraft(sddraft_path)
        success = True
        
        logging.info(f"SDDraft created at '{sddraft_path}'")
    except arcpy.ExecuteError:
        logging.error('Error creating the SDDraft')
        logging.error(arcpy.GetMessages(2))         # message type 2 = errors
        logging.error(arcpy.GetMessages(1))
    except Exception as e:
        logging.error('Error creating the SDDraft')
        logging.error(e)
        logging.error(arcpy.GetMessages(2))
        logging.error(arcpy.GetMessages(1))
    finally:
        return success

def get_staging_version(enterprise_version):
    # Mapping of ArcGIS Enterprise version to staging_version
    version_map = {
        "11.4": 340,
        "11.3": 330,
        "11.2": 320,
        "11.1": 310,
        "11.0": 300,
        "10.9.1": 209,
        "10.9": 208,
        "10.8.1": 206,
        "10.8": 205,
        "10.7.1": 204,
        "10.7": 203,
        "10.6.1": 202,
        "10.6": 201
    }
    return version_map.get(enterprise_version, 102)

def stage_and_publish_service(uploadService=False):
    success = False
    # 4. **Analyze + Stage**  (StageService runs the same analyzer the UI uses)
    sd_path = os.path.join(sddraft_dir, f'{web_tool_name}.sd')
    try:
        # remove the sd_path if it exists
        if os.path.exists(sd_path):
            os.remove(sd_path)
            logging.info(f"Removed existing SD")
            
        logging.info("Staging the service...")
        arcpy.server.StageService(in_service_definition_draft=sddraft_path, 
                                out_service_definition=sd_path, 
                                staging_version=get_staging_version(enterprise_version))
        warnings = arcpy.GetMessages(1)
        logging.info(f'messages: {arcpy.GetMessages(0)}')
        logging.info(f'errors: {arcpy.GetMessages(2)}')
        logging.info(f'warnings: {arcpy.GetMessages(1)}')
        
        if warnings:
            logging.warning("Analyzer Warnings:")
            logging.warning(warnings)
        else:
            logging.info("No warnings from analyzer")
            if uploadService:
                # 5. Upload
                logging.info("Uploading the service...")
                arcpy.server.UploadServiceDefinition(sd_path, federated_server_url) # sddraft.targetServer)
                logging.info("Upload complete")
                success = True
            else:
                success = True
                logging.info("Uploading the service skipped")
    except arcpy.ExecuteError:
        logging.error("Errors in stage_and_publish_service:")
        logging.error(arcpy.GetMessages(2))         # message type 2 = errors
        logging.error(arcpy.GetMessages(1))
    except Exception as e:
        logging.error("Errors in stage_and_publish_service:")
        logging.error(e)
        logging.error(arcpy.GetMessages(1))
        logging.error(arcpy.GetMessages(2))
    finally:
        return success

# main
if __name__ == "__main__":
    init_logging()
    logging.info("Starting the script...")
    # Connect to portal
    if connect_to_portal():
        # Run the GP tool
        success, tool_result = run_gp_tool()
        if success:
            # Create SDDraft
            if create_sddraft(tool_result):
                # Stage and publish the service
                stage_and_publish_service(uploadService=False)
    logging.info("Script completed.")
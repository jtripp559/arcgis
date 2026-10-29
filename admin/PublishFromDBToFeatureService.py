# NEED TO WORK ON UPDATING DOM
# THE REST SEEMS TO WORK

# PublishFromDBToFeatureService.py
#
# Developed by: Julie Tripp
#               julie.tripp@rrgnbs.com
# Date:  10/29/2024
#
# NOTE: sddraft files created from sharing in ArcGIS Pro can be found here:
#       C:\Users\userName\AppData\Local\ESRI\ArcGISPro\Staging\SharingProcesses
#
# Description: This script publishes feature datasets as map services with feature access to an ArcGIS Enterprise portal.
#
# Env File:
#   The script can be run with an optional .env file in the same directory as the script with the following variables:
#   Note: Any missing variables or empty values will be prompted for during script execution.
#    REPOSITORY_ID=
#    CSV_IMPORT_FILE_PATH=
#    WORKSPACE_TYPE_FILEGDB_OR_SDE=
#    WORKSPACE_FULL_PATH=
#    ARCGIS_SERVER_MANAGER_DB_NAME=
#    DATABASE_NAME=
#    DATABASE_OWNER_NAME=
#    ARCGIS_PORTAL_FOLDER_NAME=
#    ARCGIS_SERVER_FOLDER_NAME=
#    INSTANCE_TYPE_SHARED_OR_DEDICATED=
#    DEFAULT_TAGS=
#    RECYCLE_START_HOUR=
#    RECYCLE_START_MIN=
#    SPECIFIC_FEATURES_TO_IMPORT=
#    FEDERATED_SERVER_URL=
#    PORTAL_URL=
#    PORTAL_USERNAME=
#    REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING=
#
# Script execution options:
# 1. Run the script from the command line with the following command:
#    python PublishFromDBToFeatureService.py
# 2. Run the script from the command line with the following command, providing the csv import file as an argument:
#    python PublishFromDBToFeatureService.py "C:\path\to\import.csv"
#
# User Prompts (if empty/missing from .env file or command line argument):
# 1. Repository ID: 
#   - Find the RepositoryID in the manifest.xml of a service manually published to Portal from Pro for the same connection. See \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput.
# 2. ArcPy Environment Prompts:
#   - Workspace type (Options: FileGDB or SDE) - Default to SDE
#   - Full path to the workspace (e.g. T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde)
#   - Name for the database in Server Manager (e.g. sde.DEFAULT (NBS-APP1), Beisa_Datastore.gdb, dbo.DEFAULT (NBS-APP1)
#       - TIP: This is the name that will be displayed when you click on the "service" icon.
#               If you're not sure what this should be, but you know of another service that you published from Pro directly, 
#               then you can find it in the SVCManifest > Databases > SVCDatabase > Name tag of the manifest.xml file in the
#               extracted directory of the \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput directory for that service.
#           E.g. \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput\AnnualDepthToGroundwater_BasinATLAS_lev09.MapServer\extracted\
# 3. Portal Connection Prompts:
#   - Federated Server URL - Default to 'https://maps.rrgnbs.com/arcgisserver'
#   - Portal URL - Default to 'https://maps.rrgnbs.com/arcgisportal'
#   - Portal Username - Cannot be SSO enabled
#   - Portal Password
# 4. feature Dataset Prompts:
#   - Import from CSV file (Y/N)
#     - If "Y", path to the import file
#     - If "N", name of the feature dataset(s) separated by commas (e.g. ActualEvapotranspiration2021_SSEBop, NDVI2021_SSEBop)
#        - If no feature names entered, confirm to use all feature datasets in the workspace
# 5. Database and Database Owner Name Prompts (conditional, if not a FileGDB workspace )
#   - "Database Name (e.g. NBS-APP1):"
#   - "Database Owner Name (e.g. dbo):"
#   - Prepended to the feature dataset name to create the full dataset name (e.g. NBS-APP1.dbo.ActualEvapotranspiration2021_SSEBop)
# 6. Shared Instance - Default to Y
# 7. Portal and Server Folder Prompts (optional)
# 8. Default Tags for all features (optional)
# 9. Missing Data Prompts (Conditional, if missing data in feature dataset)
#   - Title
#   - Summary
#   - Description
#   - Tags
#
# Overview:
# 1. Gather rasters to publish (either from a CSV file or from the database)
# 2. Create a local service definition draft (sddraft) file using arcpy.CreateImageSDDraft
# 3. Build pyramids and calculate statistics for the raster dataset, if needed
# 4. Manually update the service definition draft DOM with additional raster details
# 5. Stage the local service definition draft to a local service definition (sd) file using arcpy.StageService_server
# 6. Upload the local service definition to the server using arcpy.UploadServiceDefinition_server
# 7. Validate and correct the Title of the published service in the portal
#
import arcpy
import os
import argparse
import datetime
import getpass
import json
from xml.dom import minidom as DOM
import logging
import shutil
from pprint import pprint
import pandas as pd
from arcgis.gis import GIS
import sys
import chardet
import traceback

# # from arcgis.layers import Service
# import xml.sax.saxutils as saxutils
try:
    # conda install python-dotenv
    from dotenv import find_dotenv, load_dotenv
    dotenv_available = True
except ImportError:
    dotenv_available = False

# ******
# testing variables only
remove_sddraft_files = True    # set to True to remove the sddraft files after successful upload; False is useful for troubleshooting; set using REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING in the .env file
backup_sddraft_files = False    # set to True to backup the sddraft file before each update to the DOM
remove_sd_files = True          # set to True to remove the sd file, if created
stageService = True             # set to True to stage the service, i.e. create a local service definition (sd) file
uploadToServer = True           # set to True to upload the service definition (sd file) to the server
limit_to_first_n_datasets = 0   # limit the number of datasets to process to the first n datasets retreived from workspace
# ******
if stageService == False:
     uploadToServer = False
if uploadToServer == False:
    remove_sd_files = False
    remove_sddraft_files = False
else:
    stageService = True

# set the output_path to the Output directory within the script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Migration status ledger (shared helper lives in ArcGIS Admin\Migrate). The module owns the canonical
# path + all writes (ledger_mod.set_state); we only pass a --ledger-path override (ledger_mod.set_ledger_path)
# and call set_state. Best-effort: if it is not importable, publishing continues unaffected. Override the
# path with env MIGRATION_LEDGER_PATH or the --ledger-path CLI arg.
sys.path.insert(0, os.path.join(current_dir, "Migrate"))
sys.path.insert(0, os.path.join(current_dir, "docs", "plan", "completed"))
try:
    import migration_status_ledger as ledger_mod
except Exception as _ledger_imp_err:
    ledger_mod = None
# Folder map (shared helper in ArcGIS Admin\Migrate): maps each source AGOL owner-folder to its
# Portal_Server_Folder (used here at publish for the server REST folder) and Portal_Owner_User_Folder
# (used at the Phase 8 reassign). Best-effort -- if unavailable, the per-row/run-level folder values are
# used as-is. Loaded once at startup. See Migrate\Input\Folder_Map.csv.
try:
    import folder_map as folder_map_mod
    _folder_map = folder_map_mod.load_folder_map()
except Exception as _fmap_imp_err:
    folder_map_mod = None
    _folder_map = {}
# Master Phase-1 migration manifest (Migrate\Input\ItemsToMigratePhase1.csv): single source of truth for
# each item's destination database / schema / SDE connection, keyed by AGOL Item ID. Best-effort -- when a
# publish row carries an item_id, its workspace/db/schema are taken from here (CSV columns still override).
try:
    import items_manifest as items_manifest_mod
    _items_manifest = items_manifest_mod.load_manifest()
except Exception as _man_imp_err:
    items_manifest_mod = None
    _items_manifest = {}
# Workflow credentials from the Windows Credential Manager (key 'portal' -> nbs_arcgis_admin), with an
# interactive prompt fallback. Best-effort -- if not importable, connect_to_portal() prompts as before.
try:
    import credential_store
except Exception as _cred_imp_err:
    credential_store = None
# Post-publish symbology (Step 6): apply the source AGOL item's renderer + pop-ups + visibility range +
# default view to the new Enterprise item (and sync its Map Image Layer) in the SAME run. Best-effort --
# if it is not importable, publishing continues unaffected.
try:
    from migration_poc_step6_apply_symbology import apply_symbology
except Exception as _sym_imp_err:
    apply_symbology = None
output_path = os.path.join(current_dir, 'Output')
if not os.path.exists(output_path):
    os.makedirs(output_path)
# Directory the .sddraft / .sd / temp .aprx are written to. Defaults to output_path; override with
# --sd-output-dir (e.g. a Staging folder on T:). Set here at module level so apply_cli_overrides can read it.
sd_output_dir = output_path
input_path = os.path.join(current_dir, 'Input')
if not os.path.exists(input_path):
    os.makedirs(input_path)
project_template_path = os.path.join(input_path, "BlankTemplateProject", "BlankTemplateProject.aprx")
if not os.path.exists(project_template_path):
    print(f"BlankTemplateProject.aprx not found in the BlankTemplateProject directory within : {input_path}")
    sys.exit()
# The migration ledger path is owned by migration_status_ledger (canonical: ArcGIS Admin\Migrate\Output,
# env MIGRATION_LEDGER_PATH overrides). A --ledger-path CLI arg is forwarded to ledger_mod.set_ledger_path()
# in apply_cli_overrides(); this script no longer hardcodes a default path of its own.

# Timestamp for unique naming
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# initialize the all_json_data dictionary
all_json_data = {}

# initialize the logging general_logger and error_logger to empty
general_logger = None
error_logger = None
general_log_file_path = os.path.join(output_path, f"PublishFeatureService_{timestamp}.log")
error_log_file_path = os.path.join(output_path, f"PublishFeatureService_Errors_{timestamp}.log")

# initialize the log_hist_data variable to an empty list
log_hist_data = []
error_count = 0

# Global variable to store the df built from the data in the import csv file
feature_import_df = pd.DataFrame()

# Global dictionary to store portal group names and ids
portal_group_dict = {}

# All of the following variables can be set in the .env file
recycleStartHour = 20   # must be between 0 and 23
recycleStartMin = 0 # must be a multiple of 15, up to 45
federated_server_url = '' # "https://maps.rrgnbs.com/arcgisserver"
portal_url = '' # 'https://maps.rrgnbs.com/arcgisportal'
# server_connection_file_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_arcgisserver_server_connection.ags"
portal_username = ''
workspace_type = ""
workspace_factory = ""
server_manager_db_name = ""
workspace_full_path = ""
repository_id = ''
instance_type = ''
arcgisPortalFolderName = ''
arcgisServerFolderName = ''
database_name = ''
database_owner_name = ''
csv_import_file_path = ''
specific_features_to_import = ''
default_tags = ''

# Existing-service guard flags (set from the CLI via apply_cli_overrides). When a service of the same name
# already exists on the federated server (BEFORE we create/publish a new one):
#   override_existing      (--OverrideExisting)     -> overwrite/republish over the existing service.
#   use_existing           (--UseExisting)          -> assume the existing same-name service is the intended
#                                                      feature and use it (do NOT republish) when the same SDE
#                                                      reference can't be auto-confirmed.
#   create_new_if_existing (--CreateNewIfExisting)  -> leave the existing service alone and publish a NEW
#                                                      service under the next free, suffix-incremented name
#                                                      (e.g. <name>_2), still referencing OUR SDE feature
#                                                      class. Use when the existing same-name service is a
#                                                      DIFFERENT dataset and you want both to coexist.
# An existing service that is auto-detected to reference the SAME SDE feature class by reference is ALWAYS
# used as-is (not republished) regardless of these flags. If none of the flags is set and the same reference
# can't be confirmed, the item is recorded as an error in the ledger and skipped.
# Precedence when more than one is set: override_existing > use_existing > create_new_if_existing.
override_existing = False
use_existing = False
create_new_if_existing = False

# initilaize gis variable
gis = None

# The feature_name currently being published. Set at the top of each main-loop iteration so log_message()
# can attribute any 'error'-level log to the right migration-ledger row (join on dest_feature_class). Blank
# during setup/connect (before the loop) so those non-per-item errors are NOT recorded against any item.
current_feature_name = ''
# Reentrancy guard + per-run de-dupe so the auto-record-on-error in log_message neither loops nor appends
# the same (feature, message) to a row's error column more than once.
_recording_ledger_error = False
_recorded_ledger_errors = set()

def _record_error_to_ledger(message):
    """Best-effort: when an 'error' is logged WHILE a specific feature is being published, append it to that
    item's migration-status-ledger row (joined dest_feature_class == current_feature_name, resolved back to
    the SOURCE item_id). This CENTRALIZES the 'on publish error, record against the source row' pattern so
    individual error sites don't each need their own ledger_source_for_feature/record_error block. A row
    that carries an error is then EXCLUDED from future publish CSVs (BuildPublishCSV skips errored rows) and
    is not treated as publishable downstream -- so the failed item stops being retried every sweep. Skipped
    when no feature is in flight (setup errors) or the ledger helper is unavailable; de-duped per run and
    reentrancy-guarded; never raises (logging must not depend on the ledger)."""
    global _recording_ledger_error
    if ledger_mod is None or not current_feature_name or _recording_ledger_error:
        return
    key = (current_feature_name.lower(), str(message)[:300])
    if key in _recorded_ledger_errors:
        return
    _recording_ledger_error = True
    try:
        src = ledger_source_for_feature(current_feature_name)
        if src:
            ledger_mod.record_error(src, str(message)[:300], phase="publish")
            _recorded_ledger_errors.add(key)
    except Exception:
        pass   # never let ledger recording break logging
    finally:
        _recording_ledger_error = False

def init_logging():
    global general_logger, error_logger
    
    # Create a general logger
    general_logger = logging.getLogger('general')
    general_logger.setLevel(logging.INFO)

    # Create a file handler for the general logger
    general_handler = logging.FileHandler(general_log_file_path, mode='a', encoding='utf-8')
    general_handler.setLevel(logging.INFO)

    # Add the handler to the general logger
    general_logger.addHandler(general_handler)

    # Create an error logger
    error_logger = logging.getLogger('error')
    error_logger.setLevel(logging.ERROR)

    # Create a file handler for the error logger
    error_handler = logging.FileHandler(error_log_file_path, mode='a', encoding='utf-8')
    error_handler.setLevel(logging.ERROR)

    # Add the handler to the error logger
    error_logger.addHandler(error_handler)

def log_by_type(message, log_level='info', tab_count=1):
    try:
        if message:
            msg_tabs = '\t' * tab_count
            if isinstance(message, dict):
                for key, value in message.items():
                    # print(msg)
                    msg = msg_tabs + f'key: {key}'
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
                    new_tab_count = tab_count + 1
                    log_by_type(value, log_level, new_tab_count)
            elif isinstance(message, list):
                for detail in message:
                    # print(detail)
                    msg = msg_tabs + detail
                    general_logger.info(msg)
                    if log_level == 'error':
                        error_logger.error(msg)
            else:
                # print('\t' + message)
                msg = msg_tabs + str(message)
                general_logger.info(msg)
                if log_level == 'error':
                    error_logger.error(msg)
    except Exception as e:
        try:
            log_message(f"Failed to log message by type: {e}", 'info')
        except Exception as inner_e:
            print(f"Failed to log message by type: {inner_e}")

def log_message(message, log_level='', message_details=None, reset_log_hist=False):
    if message == '':
        return
    global general_logger, error_logger, log_hist_data, error_count
    if log_level == 'error':
        error_count += 1
        # cycle through log_hist_data and print each message to error_logger
        for msg in log_hist_data:
            error_logger.error(msg)
    # record message to a global variable storing all the messages since reset_log_hist was set to True
    if reset_log_hist or log_level == 'error':
        # restart the log_hist_data list
        log_hist_data = []
    if log_level != 'error':
        log_hist_data.append(message)
    if log_level == '' or log_level == 'error':
        print(message)
    if log_level == '':
        log_level = 'info'
    general_logger.info(message)
    if log_level == 'error':
        error_logger.error(message)
        # Centralized ledger capture: record this error against the feature currently being published
        # (best-effort, de-duped, reentrancy-guarded -- see _record_error_to_ledger).
        _record_error_to_ledger(message)
    log_by_type(message_details, log_level)

def init_global_variables():
    global federated_server_url, portal_url, portal_username, database_name, database_owner_name, recycleStartHour, recycleStartMin, workspace_type, server_manager_db_name, workspace_full_path
    global csv_import_file_path, specific_features_to_import, repository_id, instance_type, arcgisPortalFolderName, arcgisServerFolderName, default_tags, remove_sddraft_files
    has_env_file = False
    if dotenv_available:
        try:
            env_file = find_dotenv()
            if env_file:
                # Load variables from the .env file, if any
                # This .env file must be in the same directory as this script
                load_dotenv()
                has_env_file = True
                federated_server_url = os.getenv('FEDERATED_SERVER_URL','')
                portal_url = os.getenv('PORTAL_URL','')
                portal_username = os.getenv('PORTAL_USERNAME','')
                
                workspace_type = os.getenv('WORKSPACE_TYPE_FILEGDB_OR_SDE','')
                # validate workspace_type is either FILEGDB or SDE and set to upper
                workspace_type = workspace_type.upper()
                if workspace_type not in ['FILEGDB', 'SDE']:
                    workspace_type = ''
                    
                server_manager_db_name = os.getenv('ARCGIS_SERVER_MANAGER_DB_NAME','')
                workspace_full_path = os.getenv('WORKSPACE_FULL_PATH','')
                database_name = os.getenv('DATABASE_NAME','')
                database_owner_name = os.getenv('DATABASE_OWNER_NAME','')
                csv_import_file_path = os.getenv('CSV_IMPORT_FILE_PATH','')
                specific_features_to_import = os.getenv('SPECIFIC_FEATURES_TO_IMPORT','')
                default_tags = os.getenv('DEFAULT_TAGS','')
                repository_id = os.getenv('REPOSITORY_ID','')
                instance_type = os.getenv('INSTANCE_TYPE_SHARED_OR_DEDICATED','')
                # validate instance type is either SHARED or DEDICATED and set to lower
                instance_type = instance_type.lower()
                if instance_type not in ['shared', 'dedicated']:
                    instance_type = ''
                    
                arcgisPortalFolderName = os.getenv('ARCGIS_PORTAL_FOLDER_NAME','')
                arcgisServerFolderName = os.getenv('ARCGIS_SERVER_FOLDER_NAME','')
                    
                recycleStartHour = int(os.getenv('RECYCLE_START_HOUR', '20'))
                # validate the recycleStartHour
                if recycleStartHour < 0 or recycleStartHour > 23:
                    recycleStartHour = 20
                    
                recycleStartMin = int(os.getenv('RECYCLE_START_MIN', '0'))
                # validate the recycleStartMin
                if recycleStartMin % 15 != 0:
                    recycleStartMin = 0
                
                remove_sddraft_files_str = os.getenv('REMOVE_LOCAL_SD_FILES_AFTER_PUBLISHING', str(remove_sddraft_files))
                if remove_sddraft_files_str.lower() == 'true':
                    remove_sddraft_files = True
                else:
                    remove_sddraft_files = False
                
                # print all the values from the .env file
                log_message(f"Values from the .env file:", 'info')
                log_message(f"\tFederated Server URL: {federated_server_url}", 'info')
                log_message(f"\tPortal URL: {portal_url}", 'info')
                log_message(f"\tPortal Username: {portal_username}", 'info')
                log_message(f"\tWorkspace Type: {workspace_type}", 'info')
                log_message(f"\tServer Manager DB Name: {server_manager_db_name}", 'info')
                log_message(f"\tWorkspace Full Path: {workspace_full_path}", 'info')
                log_message(f"\tDatabase Name: {database_name}", 'info')
                log_message(f"\tDatabase Owner Name: {database_owner_name}", 'info')
                log_message(f"\tCSV Import File Path: {csv_import_file_path}", 'info')
                log_message(f"\tSpecific features to Import: {specific_features_to_import}", 'info')
                log_message(f"\tDefault Tags: {default_tags}", 'info')
                log_message(f"\tRepository ID: {repository_id}", 'info')
                log_message(f"\tInstance Type: {instance_type}", 'info')
                log_message(f"\tArcGIS Portal Folder Name: {arcgisPortalFolderName}", 'info')
                log_message(f"\tArcGIS Server Folder Name: {arcgisServerFolderName}", 'info')
                log_message(f"\tRecycle Start Hour: {recycleStartHour}", 'info')
                log_message(f"\tRecycle Start Minute: {recycleStartMin}", 'info')
        except Exception as e:
            log_message(f"Failed to load environment variables from the .env file: {e}", 'info')
    else:
        log_message("dotenv module not available, skipping .env file loading", 'info')
    return has_env_file

def parse_cli_args():
    # Optional command-line overrides. Precedence: CLI arg > .env value > interactive prompt.
    # This lets the script publish from a specific schema/workspace WITHOUT editing the shared .env
    # (e.g. the per-schema migration runs: RRGOrg_ws.sde/owner 'ws', then RRGOrg_crop.sde/owner 'crop').
    # Any option omitted here falls back to the .env value, then to the interactive prompt as before.
    parser = argparse.ArgumentParser(
        description=("Publish referenced feature services from a database to ArcGIS Enterprise. "
                     "Any option provided here OVERRIDES the matching .env value; anything omitted "
                     "falls back to .env and then to an interactive prompt."))
    parser.add_argument("csv", nargs="?", default=None,
                        help="Path to the import CSV (columns: feature_name,title,summary,description,"
                             "tags,credits[,instance,portal_groups,categories]). Overrides CSV_IMPORT_FILE_PATH.")
    parser.add_argument("--workspace-full-path", "--workspace", dest="workspace_full_path", default=None,
                        help="Full path to the SDE/FileGDB workspace. Overrides WORKSPACE_FULL_PATH.")
    parser.add_argument("--workspace-type", dest="workspace_type", default=None,
                        help="FILEGDB or SDE. Overrides WORKSPACE_TYPE_FILEGDB_OR_SDE.")
    parser.add_argument("--database-name", dest="database_name", default=None,
                        help="Database name (e.g. RRGOrg). Overrides DATABASE_NAME.")
    parser.add_argument("--database-owner", "--owner", dest="database_owner_name", default=None,
                        help="Database owner/schema (e.g. ws, crop). Overrides DATABASE_OWNER_NAME.")
    parser.add_argument("--server-manager-db", dest="server_manager_db_name", default=None,
                        help='Server Manager DB name (e.g. "sde.DEFAULT (NBS-APP1)"). '
                             "Overrides ARCGIS_SERVER_MANAGER_DB_NAME.")
    parser.add_argument("--repository-id", dest="repository_id", default=None,
                        help="RepositoryID. Overrides REPOSITORY_ID.")
    parser.add_argument("--portal-folder", dest="portal_folder", default=None,
                        help="Portal item folder. Overrides ARCGIS_PORTAL_FOLDER_NAME.")
    parser.add_argument("--server-folder", dest="server_folder", default=None,
                        help="Server REST folder. Overrides ARCGIS_SERVER_FOLDER_NAME.")
    parser.add_argument("--instance", dest="instance_type", default=None,
                        help="shared or dedicated. Overrides INSTANCE_TYPE_SHARED_OR_DEDICATED.")
    parser.add_argument("--default-tags", dest="default_tags", default=None,
                        help="Tags appended to all datasets. Overrides DEFAULT_TAGS.")
    parser.add_argument("--federated-server-url", dest="federated_server_url", default=None,
                        help="Federated server URL. Overrides FEDERATED_SERVER_URL.")
    parser.add_argument("--portal-url", dest="portal_url", default=None,
                        help="Portal URL. Overrides PORTAL_URL.")
    parser.add_argument("--portal-username", dest="portal_username", default=None,
                        help="Portal username (not SSO). Overrides PORTAL_USERNAME.")
    parser.add_argument("--ledger-path", dest="ledger_path", default=None,
                        help="Migration status ledger CSV path. Overrides MIGRATION_LEDGER_PATH.")
    parser.add_argument("--sd-output-dir", dest="sd_output_dir", default=None,
                        help="Service definition (SD) output directory. Overrides SD_OUTPUT_DIR.")
    # Existing-service handling (a service of the same name already on the federated server). Accept both
    # the PascalCase spellings requested and lowercase-hyphen aliases.
    parser.add_argument("--OverrideExisting", "--override-existing", dest="override_existing",
                        action="store_true",
                        help="If a service of the same name already exists, overwrite (republish over) it.")
    parser.add_argument("--UseExisting", "--use-existing", dest="use_existing",
                        action="store_true",
                        help="If a service of the same name already exists and the SAME SDE reference cannot "
                             "be auto-confirmed, assume the existing service is the intended feature and use "
                             "it (do NOT republish). An existing service that DOES reference the same SDE "
                             "feature class is always used as-is regardless of this flag.")
    parser.add_argument("--CreateNewIfExisting", "--create-new-if-existing", "--create_new_if_existing",
                        dest="create_new_if_existing", action="store_true",
                        help="If a service of the same name already exists and the SAME SDE reference cannot "
                             "be auto-confirmed, leave the existing service alone and publish a NEW service "
                             "under the next free suffix-incremented name (e.g. <name>_2), still referencing "
                             "OUR SDE feature class. Use when the existing same-name service is a DIFFERENT "
                             "dataset and both should coexist. Lower precedence than --OverrideExisting and "
                             "--UseExisting.")
    # parse_known_args so stray/unexpected args never crash the publish run
    args, unknown = parser.parse_known_args()
    if unknown:
        log_message(f"Ignoring unrecognized command-line arguments: {unknown}", 'info')
    return args

def apply_cli_overrides(args):
    global csv_import_file_path, workspace_full_path, workspace_type, database_name, database_owner_name
    global server_manager_db_name, repository_id, arcgisPortalFolderName, arcgisServerFolderName
    global instance_type, default_tags, federated_server_url, portal_url, portal_username
    global sd_output_dir, override_existing, use_existing, create_new_if_existing
    if args is None:
        return
    def ov(new_value, current_value, label, transform=None):
        if new_value is not None and str(new_value) != '':
            if transform:
                new_value = transform(new_value)
            log_message(f"CLI override: {label} = {new_value}", 'info')
            return new_value
        return current_value
    csv_import_file_path = ov(args.csv, csv_import_file_path, 'CSV_IMPORT_FILE_PATH')
    workspace_full_path = ov(args.workspace_full_path, workspace_full_path, 'WORKSPACE_FULL_PATH')
    workspace_type = ov(args.workspace_type, workspace_type, 'WORKSPACE_TYPE_FILEGDB_OR_SDE',
                        transform=lambda v: v.upper())
    database_name = ov(args.database_name, database_name, 'DATABASE_NAME')
    database_owner_name = ov(args.database_owner_name, database_owner_name, 'DATABASE_OWNER_NAME')
    server_manager_db_name = ov(args.server_manager_db_name, server_manager_db_name, 'ARCGIS_SERVER_MANAGER_DB_NAME')
    repository_id = ov(args.repository_id, repository_id, 'REPOSITORY_ID')
    arcgisPortalFolderName = ov(args.portal_folder, arcgisPortalFolderName, 'ARCGIS_PORTAL_FOLDER_NAME')
    arcgisServerFolderName = ov(args.server_folder, arcgisServerFolderName, 'ARCGIS_SERVER_FOLDER_NAME')
    instance_type = ov(args.instance_type, instance_type, 'INSTANCE_TYPE_SHARED_OR_DEDICATED',
                       transform=lambda v: v.lower())
    default_tags = ov(args.default_tags, default_tags, 'DEFAULT_TAGS')
    federated_server_url = ov(args.federated_server_url, federated_server_url, 'FEDERATED_SERVER_URL')
    portal_url = ov(args.portal_url, portal_url, 'PORTAL_URL')
    portal_username = ov(args.portal_username, portal_username, 'PORTAL_USERNAME')
    # Forward a --ledger-path override to the ledger module (it owns the canonical path otherwise).
    if args.ledger_path and str(args.ledger_path) != '' and ledger_mod is not None:
        log_message(f"CLI override: MIGRATION_LEDGER_PATH = {args.ledger_path}", 'info')
        ledger_mod.set_ledger_path(args.ledger_path)
    sd_output_dir = ov(args.sd_output_dir, sd_output_dir, 'SD_OUTPUT_DIR')
    if not sd_output_dir:
        sd_output_dir = output_path
    if getattr(args, 'override_existing', False):
        override_existing = True
        log_message("CLI override: OverrideExisting = True (existing services will be overwritten)", 'info')
    if getattr(args, 'use_existing', False):
        use_existing = True
        log_message("CLI override: UseExisting = True (an existing same-name service is assumed to be the "
                    "intended feature)", 'info')
    if getattr(args, 'create_new_if_existing', False):
        create_new_if_existing = True
        log_message("CLI override: CreateNewIfExisting = True (on a same-name clash, publish a new "
                    "suffix-incremented service referencing our SDE feature class)", 'info')


'''
# Function to check if the workspace is registered with the server  # Not needed
def is_workspace_registered_with_server(workspace, server_connection_file):
    server = arcpy.mapping.ListWorkspaces(server_connection_file, "FROM_CONNECTION_FILE")[0]
    registered_workspaces = [item.path for item in arcpy.ListDataStoreItems(server, "DATABASE")]
    return workspace in registered_workspaces
'''

def remove_file(file_path):
    success = False
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            log_message(f"Removed file: '{file_path}'", 'info')
        success = True
    except Exception as e:
        log_message(f"Failed to remove file '{file_path}': {e}", 'info')
    return success

def get_file_encoding(file_path):
    encoding = 'ISO-8859-1'
    try:
        with open(file_path, 'rb') as f:
            rawdata = f.read()
        result = chardet.detect(rawdata)
        encoding = result['encoding']
        log_message(f"Detected file encoding for '{file_path}': {encoding}", 'info')
    except Exception as e:
        log_message(f"Failed to get file encoding for '{file_path}': {e}", 'info')
    return encoding

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
    log_message(f"{prompt}: {user_input}", 'info')
    return user_input

def get_all_json_data():
    global all_json_data, all_json_data_file_path
    if all_json_data == {}:
        if os.path.exists(all_json_data_file_path):
            # load all_json_data from the pre-processed json file
            with open(all_json_data_file_path, 'r') as f:
                all_json_data = json.load(f)
        else:
            # piece together all_json_data from the json files in the input directory
            query_results = {}
            json_query_results_file_path = os.path.join(input_path, 'RRGImageLayers_all.json')
            with open(json_query_results_file_path, 'r') as f:
                query_results_json = json.load(f)
            for query_results_record in query_results_json['results']:
                if 'url' in query_results_record:
                    url = query_results_record.get('url', '')
                    if url != '':
                        # store record in global dictionary with url as key
                        key = url.lower()
                        query_results[key] = query_results_record
                
            json_file_path = os.path.join(input_path, 'RRGEnterprise_all_services_data.json')
            with open(json_file_path, 'r') as f:
                data = json.load(f)
            for record in data['services']:
                key = None
                url = ''
                if 'url' in record:
                    url = record['url'].lower()
                    # remove ?f=pjson from the end of the url
                    if url.endswith('?f=pjson'):
                        url = url[:-8]
                if 'metadata.itemName' in record:
                    # store record in global dictionary with metadata.itemName as key
                    key = record['metadata.itemName'].lower()
                else:
                    # store record in global dictionary with url as key
                    key = url
                if key and key != '':
                    record['nbs_results'] = query_results.get(url, {})
                    
                    # pull out relevant information from the record
                    # tags, summary, title, description
                    if record['nbs_results'] != {}:
                        tags = record['nbs_results'].get('tags', [])
                        record['nbs_summary'] = record['nbs_results'].get('snippet', '')
                        record['nbs_title'] = record['nbs_results'].get('title', '')
                        record['nbs_description'] = record['nbs_results'].get('description', '')
                    else:
                        if 'metadata' in record:
                            if 'dataIdInfo' in record['metadata']:
                                if 'searchKeys' in record['metadata']['dataIdInfo']:
                                    tags = record['metadata']['dataIdInfo']['searchKeys'].get('keyword', [])
                                    record['nbs_summary'] = record['metadata']['dataIdInfo'].get('idPurp', '')
                                    if 'idCitation' in record['metadata']['dataIdInfo']:
                                        if 'resTitle' in record['metadata']['dataIdInfo']['idCitation']:
                                            if '#text' in record['metadata']['dataIdInfo']['idCitation']['resTitle']:
                                                record['nbs_title'] = record['metadata']['dataIdInfo']['idCitation']['resTitle']['#text']
                                            else:
                                                record['nbs_title'] = record['metadata']['dataIdInfo']['idCitation']['resTitle']
                        record['nbs_description'] = ''
                    if record.get('nbs_title', '') == '':
                        record['nbs_title'] = key
                    if record.get('nbs_summary', '') == '':
                        record['nbs_summary'] = record['nbs_title']
                    record['nbs_tags'] = ','.join(tags)
                    record['nbs_dataLocation'] = record.get('metadata.linkage', '')
                    record['nbs_dataFormat'] = record.get('metadata.distFormat', '')
                    record['nbs_spatialReference'] = record.get('metadata.geogcsn', '')
                    all_json_data[key] = record
            # export all_json_data to a json file
            with open(all_json_data_file_path, 'w') as f:
                json.dump(all_json_data, f, indent=4)
            log_message(f'Exported all_json_data to {all_json_data_file_path}')
    return all_json_data

def find_json_data(dataset):
    return_json = None
    json_data = get_all_json_data()
    if json_data != None:
        lower_dataset = dataset.lower()
        # get the name from the dataset
        lower_name = lower_dataset.split('.')[-1]
        if json_data.get(lower_dataset):
            return_json = json_data[lower_dataset]
        else:
            # look for the name.lower() in the key of the json_data dictionary
            for key in json_data.keys():
                if lower_name in key:
                    return_json = json_data[key]
                    break
    if return_json == None:
        log_message(f"No json data found for {dataset}", 'info')
    return return_json

def get_recycle_time():
    global recycleStartHour, recycleStartMin
    recycleStartMin += 15
    if recycleStartMin > 59:
        recycleStartMin = 0
        recycleStartHour += 1
    if recycleStartHour > 23:
        recycleStartHour = 0
    return str(recycleStartHour).zfill(2) + ":" + str(recycleStartMin).zfill(2)

def get_parent_element(doc, parentPath):
    parent_element = None
    if parentPath == []:
        return None
    for tag in parentPath:
        if parent_element is None:
            elements = doc.getElementsByTagName(tag)
        else:
            elements = parent_element.getElementsByTagName(tag)
        if elements:
            parent_element = elements[0]
        else:
            return None
    return parent_element

def add_element_under_nested_parent(doc, elementTagName, value='', nestedParentPath=[], attribute={}):
    if elementTagName == '':
        return
    parent_element = None
    search_elements = []
    if nestedParentPath == []:
        search_elements = doc.getElementsByTagName(elementTagName)
    else:
        parent_element = get_parent_element(doc, nestedParentPath)
        if parent_element:
            search_elements = parent_element.getElementsByTagName(elementTagName)
    element = None
    if search_elements:
        # setup to update the existing element
        element = search_elements[0]
    else:
        # create a new element
        element = doc.createElement(elementTagName)
    if element:
        if value != '':
            if element.firstChild:
                element.firstChild.nodeValue = value
            else:
                element_text = doc.createTextNode(value)
                element.appendChild(element_text)
        # set attributes if any
        for attr_name, attr_value in attribute.items():
            element.setAttribute(attr_name, attr_value)
    if parent_element:
        parent_element.appendChild(element)
    log_message(f"Set value of element '{elementTagName}' to '{value}' under parent path '{' > '.join(nestedParentPath)}'", 'info')

def add_key_value_element_under_nested_parent(doc, elementTagName, key, value, nestedParentPath=[], elementAttributes={}, keyAttributes={}):
    if elementTagName == '' or key == '' or value == '' or nestedParentPath == []:
        return
    parent_element = get_parent_element(doc, nestedParentPath)
    if parent_element:
        new_element = doc.createElement(elementTagName)
        for attr_name, attr_value in elementAttributes.items():
            new_element.setAttribute(attr_name, attr_value)
        new_key = doc.createElement('Key')
        new_key_text = doc.createTextNode(key)
        new_key.appendChild(new_key_text)
        new_element.appendChild(new_key)
        new_value = doc.createElement('Value')
        for attr_name, attr_value in keyAttributes.items():
            new_value.setAttribute(attr_name, attr_value)
        new_value_text = doc.createTextNode(value)
        new_value.appendChild(new_value_text)
        new_element.appendChild(new_value)
        parent_element.appendChild(new_element)
        log_message(f"Added key-value element '{elementTagName}' with key '{key}' and value '{value}' under parent path '{' > '.join(nestedParentPath)}'", 'info')
        
def add_databases_to_sddraft_dom(doc, connectionString, datasetOnPremisePath):
    dataset_name = datasetOnPremisePath.split('.')[-1]
    
    # prompt for DB Name for Server Manger e.g. sde.DEFAULT (NBS-APP1),  dbo.DEFAULT (NBS-APP1), Beisa_Datastore.gdb
    
    databases_xml = f'''
    <Databases xsi:type='typens:ArrayOfSVCDatabase' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xs='http://www.w3.org/2001/XMLSchema' xmlns:typens='http://www.esri.com/schemas/ArcGIS/3.2.0'>
        <SVCDatabase xsi:type='typens:SVCDatabase'>
            <ID/>
            <Name>{server_manager_db_name}</Name>
            <OnPremisePath/>
            <ServerPath/>
            <InPackagePath/>
            <OnPremiseWorkspaceFactoryProgID>{workspace_factory}</OnPremiseWorkspaceFactoryProgID>
            <OnPremiseConnectionString>{connectionString}</OnPremiseConnectionString>
            <InPackageWorkspaceFactoryProgID/>
            <Datasets xsi:type='typens:ArrayOfSVCDataset'>
                <SVCDataset xsi:type='typens:SVCDataset'>
                    <ID/>
                    <Name>{dataset_name}</Name>
                    <OnPremisePath>{datasetOnPremisePath}</OnPremisePath>
                    <ServerPath/>
                    <InPackagePath/>
                    <OnServerName>{dataset_name}</OnServerName>
                    <DatasetType>esriDTRasterDataset</DatasetType>
                </SVCDataset>
            </Datasets>
            <Replicas xsi:type='typens:ArrayOfSVCReplica'/>
            <SwizzledOnClient>false</SwizzledOnClient>
            <ByReference>true</ByReference>
            <OnServerWorkspaceFactoryProgID>{workspace_factory}</OnServerWorkspaceFactoryProgID>
            <OnServerConnectionString>{connectionString}</OnServerConnectionString>
            <OnServerName>{server_manager_db_name}</OnServerName>
        </SVCDatabase>
    </Databases>
    '''
    log_message(f'server_manager_db_name: {server_manager_db_name}', 'info')
    log_message(f'workspace_factory: {workspace_factory}', 'info')
    log_message(f'dataset_name: {dataset_name}', 'info')
    log_message(f'datasetOnPremisePath: {datasetOnPremisePath}', 'info')
    log_message(f'connectionString: {connectionString}', 'info')
    log_message(f"databases_xml: {databases_xml}", 'info')
    
    databases_node = DOM.parseString(databases_xml).documentElement
    # Remove temporary namespace declarations after parsing
    databases_node.removeAttribute('xmlns:xsi')
    databases_node.removeAttribute('xmlns:xs')
    databases_node.removeAttribute('xmlns:typens')
    
    # replace <Databases xsi:type='typens:ArrayOfSVCDatabase'/> with databases_xml
    databases_elements = doc.getElementsByTagName('Databases')
    if databases_elements:
        databases_element = databases_elements[0]
        parent_node = databases_element.parentNode
        parent_node.replaceChild(databases_node, databases_element)
    else:
        # add new Databases element
        doc.documentElement.appendChild(databases_node)
        
def remove_non_ascii(text):
    if pd.isnull(text):
        text = ''
    else:
        text = str(text)
    if text is None or text == '':
        return ''
    # replace non-ascii characters with a space 
    # except for the dash-like characters which are replaced with a hyphen
    return_text = ''.join(i if ord(i) < 128 else '-' if ord(i) in {8211, 8212, 8722, 8209, 8210} else ' ' for i in text)
    # return_text = saxutils.escape(return_text)
    if return_text != text:
        log_message(f"Replaced non-ascii characters in '{text}' with '{return_text}'", 'info')
    return return_text

def update_sddraft_dom(sd_file_path, feature_name, title, description, credits='', is_shared_instance=True, repository_id='0'):
    # Specifics of ESRI sddraft files:
    #   - StagingSettings.PropertyArray.PropertySetProperty.Key = 'PortalFolderName'    => Value = # Name of the folder in the portal where the service will be published
    #   - Configurations.SVCConfiguration.ServiceFolder = # Name of the folder in the server where the service will be published
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'recycleInterval'   => Value = # Time in minutes between recycling the service
    #   FOR SHARED INSTANCES
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MinInstances'       => Value = 0
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MaxInstances'       => Value = 0
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'provider'           => Value = 'DMaps'  (map/feature shared pool; NOT the raster 'ArcObjectsRasterRendering')
    #   FOR DEDICATED INSTANCES
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MinInstances'       => Value = # Minimum number of instances of the service
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'MaxInstances'       => Value = # Maximum number of instances of the service
    #   - Configurations.Definition.Props.PropertySetProperty.Key = 'provider'           => Value = 'ArcObjects11'
    # See https://developers.arcgis.com/rest/enterprise-administration/enterprise/deployment-default-properties/
    
    log_message(f"Updating sddraft DOM at '{sd_file_path}'", 'info')
    
    try:
        # Read the contents of the draft into an xml parser
        doc = DOM.parse(sd_file_path)
        # print(doc.toprettyxml())
        
        # Replace unsupported character with a space in title and description
        title = remove_non_ascii(title)
        description = remove_non_ascii(description)
        credits = remove_non_ascii(credits)
            
        # Update the feature specific information
        add_element_under_nested_parent(doc, 'Name', feature_name, ['ItemInfo'])
        add_element_under_nested_parent(doc, 'Title', title, ['ItemInfo'])
        add_element_under_nested_parent(doc, 'Description', description, ['ItemInfo'])
        add_element_under_nested_parent(doc, 'Credits', credits, ['ItemInfo'])

        # Locate the ItemInfo element
        item_info_elements = doc.getElementsByTagName('ItemInfo')
        if item_info_elements:
            item_info = item_info_elements[0]
            # print(item_info.toprettyxml())
            
            # Replace underscore with space in all String elements within the Tags element
            elements = item_info.getElementsByTagName('Tags')
            if elements:
                for element in elements:
                    string_elements = element.getElementsByTagName('String')
                    for string_element in string_elements:
                        if string_element.firstChild:
                            if string_element.firstChild.nodeValue != 'RRG_Enterprise':
                                string_element.firstChild.nodeValue = string_element.firstChild.nodeValue.replace("_", " ")
                    
        recycleInterval = '264'
        
        found_IncludeDataInSDFile = False
        found_PortalFolderName = False
        found_AllowCopy = False
        found_Provider = False
        found_ServiceTitle = False
        connectionString = ''

        if is_shared_instance:
            # Shared instance pool: provider must be 'DMaps' for a map/feature service.
            # ('ArcObjectsRasterRendering' was a leftover from this script's image-service origin and is
            # WRONG for feature services -- it was the reason the POC had to fall back to dedicated.)
            # Esri: shared-pool services report provider=DMaps; min/max instances are 0 (the pool manages them).
            provider_value = 'DMaps'
            min_instances = '0'
            max_instances = '0'
        else:
            provider_value = 'ArcObjects11'
            min_instances = '1'
            max_instances = '2'
        
        # Locate the PropertySetProperty elements
        property_set_properties = doc.getElementsByTagName('PropertySetProperty')
        for property_set_property in property_set_properties:
            key_elements = property_set_property.getElementsByTagName('Key')
            if key_elements and key_elements[0].firstChild:
                key = key_elements[0].firstChild.nodeValue
                if key in ['MaxImageWidth', 'MaxImageHeight']:
                    # Update the value
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements and value_elements[0].firstChild:
                        current_value = int(value_elements[0].firstChild.nodeValue)
                        new_value = current_value * 10  # Add one extra 0
                        # print(f'Updating {key} from {current_value} to {new_value}')
                        value_elements[0].firstChild.nodeValue = str(new_value)
                elif key == 'recycleInterval':
                    # set the recycleInterval property
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = recycleInterval
                        else:
                            text_node = doc.createTextNode(recycleInterval)
                            value_elements[0].appendChild(text_node)
                elif key == 'recycleStartTime':
                    # get recycleStartTime as 15 minutes after the current recycleStartTime
                    recycleStartTime = get_recycle_time()
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = recycleStartTime
                        else:
                            text_node = doc.createTextNode(recycleStartTime)
                            value_elements[0].appendChild(text_node)
                elif key == 'CallingContext':
                    # set the property value to 0
                    value = '0'
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
                elif key == 'minInstances':
                    value = min_instances
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
                elif key == 'maxInstances':
                    value = max_instances
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
                elif key == 'ServerConnectionString':
                    # Update ServerConnectionString to
                    #   - remove /services and 
                    #   - replace esriAGSConnectionModeConsumer with esriAGSConnectionModePublisher
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            current_value = value_elements[0].firstChild.nodeValue
                            # replace esriAGSConnectionModeConsumer with esriAGSConnectionModePublisher in current_value to get value
                            value = current_value.replace('esriAGSConnectionModeConsumer', 'esriAGSConnectionModePublisher')
                            value = value.replace('/services', '')
                            value_elements[0].firstChild.nodeValue = value
                elif key == 'IncludeDataInSDFile':
                    found_IncludeDataInSDFile = True
                elif key == 'PortalFolderName':
                    found_PortalFolderName = True
                elif key == 'AllowCopy':
                    found_AllowCopy = True
                    # set the property value to false
                    value = 'false'
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
                elif key == 'Provider':
                    found_Provider = True
                    value = provider_value
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
                elif key == 'ConnectionString':
                    # get the value and store it in connectionString variable
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            connectionString = value_elements[0].firstChild.nodeValue
                elif key == 'ServiceTitle':
                    found_ServiceTitle = True
                    value = title
                    value_elements = property_set_property.getElementsByTagName('Value')
                    if value_elements:
                        if value_elements[0].firstChild:
                            value_elements[0].firstChild.nodeValue = value
                        else:
                            text_node = doc.createTextNode(value)
                            value_elements[0].appendChild(text_node)
        if (not found_IncludeDataInSDFile):
            add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'IncludeDataInSDFile', 'false', ['ConfigurationProperties', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:boolean'})
        if (not found_PortalFolderName) and arcgisPortalFolderName != '':
            add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'PortalFolderName', arcgisPortalFolderName, ['StagingSettings', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
        if (not found_AllowCopy):
            add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'AllowCopy', 'false', ['ConfigurationProperties', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:boolean'})
        if (not found_Provider):
            add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'Provider', provider_value, ['Props', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
        if (not found_ServiceTitle):
            add_key_value_element_under_nested_parent(doc, 'PropertySetProperty', 'ServiceTitle', title, ['StagingSettings', 'PropertyArray'], {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
        
        # Update the RecyclingInterval
        add_element_under_nested_parent(doc, 'RecyclingInterval', recycleInterval, ['Configurations', 'SVCConfiguration', 'Definition'])
        
        if arcgisServerFolderName != '':
            # Update ServiceFolder to user specified arcgisServerFolderName.
            add_element_under_nested_parent(doc, 'ServiceFolder', arcgisServerFolderName, ['Configurations', 'SVCConfiguration'])
            # if arcgisServerFolderName does not exist in the server, add it to the server via REST Admin API
            # determine if the arcgisServerFolderName already exists on the server by checking
            arcgisServerFolderName_exists = False
            try:
                server = gis.admin.servers.list()[0]
                folder_list = server.services.folders
                if arcgisServerFolderName in folder_list:
                    arcgisServerFolderName_exists = True
                    log_message(f"Folder '{arcgisServerFolderName}' already exists on the server.", 'info')
                else:
                    # create the folder on the server
                    status = server.services.create_folder(arcgisServerFolderName)
                    if status:
                        log_message(f"Folder '{arcgisServerFolderName}' created on the server.", 'info')
                    else:
                        log_message(f"Failed to create folder '{arcgisServerFolderName}' on the server.", 'error')
                        # traceback.print_exc()
                        log_message(traceback.format_exc(), 'error')
            except Exception as e:
                log_message(f"Failed to check if folder '{arcgisServerFolderName}' exists on the server: {e}", 'info')
                log_message(traceback.format_exc(), 'info')
            
        add_element_under_nested_parent(doc, 'RepositoryID', repository_id, ['Resources','SVCResource'])
        
        if workspace_type == 'FILEGDB':
            connectionString = 'DATABASE=' + arcpy.env.workspace

        if connectionString != '':
            resources_elements = doc.getElementsByTagName('Resources')
            if resources_elements:
                resources_onPremisePath_elements = resources_elements[0].getElementsByTagName('OnPremisePath')
                if resources_onPremisePath_elements:
                    if resources_onPremisePath_elements[0].firstChild:
                        resources_onPremisePath = resources_onPremisePath_elements[0].firstChild.nodeValue
                        add_databases_to_sddraft_dom(doc, connectionString, resources_onPremisePath)
        
        if backup_sddraft_files:
            # save current sd_file_path to a backup file
            backup_sd_file_path = sd_file_path.replace('.sddraft', '_backup.sddraft')
            try:
                shutil.copyfile(sd_file_path, backup_sd_file_path)
                log_message(f"Backup saved to {backup_sd_file_path}")
            except Exception as e:
                log_message(f"Failed to backup {sd_file_path} to {backup_sd_file_path}: {e}", 'info')
        
        # Write the changes back to the sddraft
        with open(sd_file_path, 'w') as f:
            doc.writexml(f)
        
        # analysis = arcpy.mapping.AnalyzeForSD(sd_file_path)
        # if analysis['errors'] != {}:
        #    log_message('AnalyzeForSD Errors', 'error', analysis['errors'])
        #    return False
        return True
    except Exception as e:
        log_message(f"Failed to update sddraft DOM at '{sd_file_path}': {e}", 'error')
        return False

def finalize_sddraft(sd_file_path, is_shared_instance=True):
    """Post-export edits for the FEDERATED_SERVER / MAP_IMAGE referenced publish:
      1) enable the FeatureServer extension (Feature Access) so the publish yields a FeatureServer
         alongside the MapServer (the referenced Feature Layer the migration shares back to AGOL);
      2) set the instance provider -- shared = 'DMaps' (min/max 0), dedicated = 'ArcObjects11' (min/max 1/2).
    Deliberately does NOT touch the Databases / RepositoryID / connection-string blocks: arcpy already
    wrote a correct BY-REFERENCE SD (copyDataToServer=False), so those must be left intact (this replaces
    the old update_sddraft_dom() offline workaround). Returns True on success."""
    log_message(f"Finalizing sddraft '{sd_file_path}' (enable Feature Access; set instance provider)", 'info')
    try:
        doc = DOM.parse(sd_file_path)

        # 1) enable the FeatureServer extension (Feature Access)
        enabled = False
        for ext in doc.getElementsByTagName('SVCExtension'):
            tns = ext.getElementsByTagName('TypeName')
            if tns and tns[0].firstChild and tns[0].firstChild.data == 'FeatureServer':
                for en in ext.getElementsByTagName('Enabled'):
                    if en.firstChild:
                        en.firstChild.data = 'true'
                        enabled = True
        log_message(f"\tFeatureServer extension enabled: {enabled}", 'info')

        # 2) instance provider (best-effort -- a failure here must NOT block the publish)
        try:
            if is_shared_instance:
                provider_value, min_i, max_i = 'DMaps', '0', '0'
            else:
                provider_value, min_i, max_i = 'ArcObjects11', '1', '2'
            found_provider = False
            for psp in doc.getElementsByTagName('PropertySetProperty'):
                keys = psp.getElementsByTagName('Key')
                if not (keys and keys[0].firstChild):
                    continue
                k = keys[0].firstChild.nodeValue
                vals = psp.getElementsByTagName('Value')
                new_val = None
                if k in ('provider', 'Provider'):
                    found_provider = True
                    new_val = provider_value
                elif k == 'minInstances':
                    new_val = min_i
                elif k == 'maxInstances':
                    new_val = max_i
                if new_val is not None and vals:
                    if vals[0].firstChild:
                        vals[0].firstChild.nodeValue = new_val
                    else:
                        vals[0].appendChild(doc.createTextNode(new_val))
            if not found_provider:
                add_key_value_element_under_nested_parent(
                    doc, 'PropertySetProperty', 'provider', provider_value,
                    ['Definition', 'Props', 'PropertyArray'],
                    {'xsi:type': 'typens:PropertySetProperty'}, {'xsi:type': 'xs:string'})
            log_message(f"\tInstance provider set to '{provider_value}' (shared={is_shared_instance})", 'info')
        except Exception as e:
            log_message(f"\t(could not set instance provider; service keeps its default: {e})", 'info')

        with open(sd_file_path, 'w') as f:
            doc.writexml(f)
        return True
    except Exception as e:
        log_message(f"Failed to finalize sddraft at '{sd_file_path}': {e}", 'error')
        return False

def set_arcpy_environment():
    global workspace_type, workspace_factory, server_manager_db_name, workspace_full_path
    env_set = True
    
    # prompt for DB Name for Server Manger e.g. sde.DEFAULT (NBS-APP1),  dbo.DEFAULT (NBS-APP1), Beisa_Datastore.gdb
    
    # Ask the user if they are utlizing a FileGDB or SDE
    workspace_type = get_user_input("Workspace type (FileGDB or SDE)", default_value='SDE', value_to_check=workspace_type)
    workspace_type = workspace_type.upper()
    if workspace_type not in ['FILEGDB', 'SDE']:
        log_message(f"Invalid workspace type {workspace_type}. Exiting...", 'error')
        env_set = False
    else:
        if workspace_type == 'FILEGDB':
            example_workspace_path = r"\\nbs-app2\t$\ArcGISDataset\GIS\RRG - NBS\Elite Ag\Beisa\Beisa_Datastore.gdb"
            workspace_factory = 'esriDataSourcesGDB.FileGDBWorkspaceFactory'
            # prompt for DB Name for Server Manger e.g. sde.DEFAULT (NBS-APP1),  dbo.DEFAULT (NBS-APP1), Beisa_Datastore.gdb
            example_server_manager_db_name = 'Beisa_Datastore.gdb'
        else:
            example_workspace_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_WS_sde.sde"
            workspace_factory = 'esriDataSourcesGDB.SdeWorkspaceFactory'
            example_server_manager_db_name = 'sde.DEFAULT (NBS-APP1)'
        
        # Run-level workspace is OPTIONAL: leave blank to provide a per-row 'workspace_full_path' column
        # in the CSV (lets ONE run publish across multiple databases/schemas). A non-blank value here is
        # the default/fallback for rows that do not override it. Example: {example_workspace_path}
        workspace_full_path = get_user_input(
            f"Full path to the workspace (blank = set per-row in the CSV; e.g. {example_workspace_path})",
            default_value='', value_to_check=workspace_full_path)
        if workspace_full_path == "":
            log_message("No run-level workspace; expecting a per-row 'workspace_full_path' column in the CSV.", 'info')
        elif not os.path.exists(workspace_full_path):
            log_message(f"Database connection file {workspace_full_path} does not exist. Exiting...", 'error')
            env_set = False

        if server_manager_db_name == '':
            print('NOTE: The name for the database in Server Manager displays on the Reference tab in the service.')
            print('NOTE: Leave blank to provide a per-row "server_manager_db" column in the CSV.')
            server_manager_db_name = get_user_input(
                f"Name for the database in ArcGIS Server Manager (blank = per-row; e.g. {example_server_manager_db_name})",
                default_value='', value_to_check=server_manager_db_name)

    if env_set and workspace_full_path != "":
        try:
            # Set the workspace to your enterprise geodatabase connection
            arcpy.env.workspace = workspace_full_path
            log_message(f"Workspace set to {workspace_full_path}")
        except Exception as e:
            log_message(f"Failed to set the workspace to {workspace_full_path}: {e}", 'error')
            env_set = False

    return env_set

def connect_to_portal():
    global portal_url, gis, portal_username
    connected = False
    
    # Get portal URL from the user or default to 'https://maps.rrgnbs.com/arcgisportal'
    portal_url = get_user_input("ArcGIS portal URL", default_value='https://maps.rrgnbs.com/arcgisportal', value_to_check=portal_url)
    
    # Portal login: try the Windows Credential Manager FIRST (key 'portal' -> nbs_arcgis_admin), falling
    # back to an interactive prompt. The .env / --portal-username value is used as the default/prompt
    # username; a stored credential's own username takes precedence when present.
    if credential_store is not None:
        # Shared helper: CREDENTIALS FIRST (key 'portal'), Pro/prompt fallback, and sign_in_arcpy=True so
        # arcpy (used for publishing below) shares the same login -- FATAL if that arcpy sign-in fails.
        # verify_cert is left at the GIS default; pass it through here if this site needs it.
        try:
            gis = credential_store.connect(portal_url, key="portal",
                                           default_username=(portal_username or 'rrgadmin'),
                                           sign_in_arcpy=True, log=lambda m: log_message(m, 'info'))
            portal_username = gis.properties.user.username
            connected = True
            log_message(f"Connected to {portal_url} as {portal_username}")
        except Exception as e:
            log_message(f"Failed to connect to {portal_url}: {e}", 'error')
    else:
        portal_username = get_user_input("ArcGIS Portal Username (not SSO)", default_value='rrgadmin', value_to_check=portal_username)
        portal_password = getpass.getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
        if portal_username == "" or portal_password == "":
            log_message("Missing portal username or password.", 'error')
        else:
            try:
                arcpy.SignInToPortal(portal_url, portal_username, portal_password)
                connected = True
                log_message(f"Connected to {portal_url} as {portal_username}")
            except Exception as e:
                log_message(f"Failed to connect to {portal_url}: {e}", 'error')
            try:
                gis = GIS(portal_url, portal_username, portal_password)
            except Exception as e:
                log_message(f"Failed to connect to arcgis: {e}", 'error')
    return connected

def format_feature_name(feature_name):
    if workspace_type == 'FILEGDB':
        return feature_name
    
    global database_name, database_owner_name
    feature_dataset = ''
    period_count = feature_name.count('.')
    if period_count >= 2:
        # assume the feature name is fully qualified
        feature_dataset = feature_name
    else:
        if database_name == '':
            # get the database name from the user
            database_name = get_user_input("Name of the database", default_value='NBS_WS', value_to_check=database_name)
            if database_name == "":
                log_message("Missing database name.", 'error')
                return feature_dataset
        if period_count == 1:
            # assume schema name is included in the feature name
            feature_dataset = f"{database_name}.{feature_name}"
        else:
            if database_owner_name == "":
                # get the schema name from the user
                database_owner_name = get_user_input("Name of the database user", default_value='sde', value_to_check=database_owner_name)
                if database_owner_name == "":
                    log_message("Missing schema name.", 'error')
                    return feature_dataset
            feature_dataset = f"{database_name}.{database_owner_name}.{feature_name}"
    return feature_dataset

def factory_for_workspace(path, ws_type=''):
    """Workspace factory progID from an explicit type, else inferred from the path extension
    (.gdb -> FileGDB, otherwise SDE)."""
    wt = (ws_type or '').upper()
    if wt == 'FILEGDB':
        return 'esriDataSourcesGDB.FileGDBWorkspaceFactory'
    if wt == 'SDE':
        return 'esriDataSourcesGDB.SdeWorkspaceFactory'
    return ('esriDataSourcesGDB.FileGDBWorkspaceFactory'
            if os.path.splitext(path)[1].lower() == '.gdb'
            else 'esriDataSourcesGDB.SdeWorkspaceFactory')

def get_row_value(row_df, *names):
    """First non-empty value among the given column names in a single-row DataFrame, else ''."""
    for n in names:
        if n in row_df.columns:
            val = row_df[n].values[0]
            if pd.notnull(val) and str(val).strip() != '':
                return str(val).strip()
    return ''

def apply_row_env_overrides(row_df, base):
    """Apply OPTIONAL per-row workspace/database/schema overrides from the publish CSV, so a single CSV
    can target multiple databases and schemas in one run. Precedence: per-row CSV value > run-level base
    (CLI arg / .env / prompt). Resets to the base first so an override never bleeds into the next row.
    Sets arcpy.env.workspace for this row. Returns True if a usable workspace was set, else False (the
    caller should skip the row). Recognized columns (all optional):
        workspace_full_path (or workspace), workspace_type, database_name (or database),
        database_owner (or database_owner_name / schema), server_manager_db (or server_manager_db_name),
        portal_folder (or arcgis_portal_folder_name), server_folder (or arcgis_server_folder_name),
        agol_owner_folder (or owner_folder) -> mapped to the server folder via Folder_Map.csv when
        server_folder is not given explicitly,
        item_id (or agol_item_id) -> looked up in ItemsToMigratePhase1.csv for the SDE connection /
        database / schema (the source of truth; explicit workspace/database/owner columns override it)."""
    global workspace_type, workspace_factory, database_name, database_owner_name, server_manager_db_name
    global arcgisPortalFolderName, arcgisServerFolderName
    # reset the mutable env back to the run-level base before applying this row's overrides
    workspace_type = base['workspace_type']
    database_name = base['database_name']
    database_owner_name = base['database_owner_name']
    server_manager_db_name = base['server_manager_db_name']
    arcgisPortalFolderName = base['arcgisPortalFolderName']
    arcgisServerFolderName = base['arcgisServerFolderName']

    row_ws = get_row_value(row_df, 'workspace_full_path', 'workspace')
    row_wstype = get_row_value(row_df, 'workspace_type')
    row_db = get_row_value(row_df, 'database_name', 'database')
    row_owner = get_row_value(row_df, 'database_owner', 'database_owner_name', 'schema')
    row_smdb = get_row_value(row_df, 'server_manager_db', 'server_manager_db_name')
    row_portal_folder = get_row_value(row_df, 'portal_folder', 'arcgis_portal_folder_name')
    row_server_folder = get_row_value(row_df, 'server_folder', 'arcgis_server_folder_name')
    row_agol_folder = get_row_value(row_df, 'agol_owner_folder', 'owner_folder')
    row_item_id = get_row_value(row_df, 'item_id', 'agol_item_id')

    # Master manifest (ItemsToMigratePhase1.csv) by AGOL Item ID is the source of truth for the SDE
    # connection / database / schema; explicit per-row CSV columns still override it.
    man_ws = man_db = man_owner = ''
    if row_item_id and items_manifest_mod is not None:
        rec = items_manifest_mod.get(row_item_id, _items_manifest)
        if rec:
            man_ws = rec.get('connection_filepath', '')
            man_db = rec.get('target_database', '')
            man_owner = rec.get('target_schema', '')
            log_message(f"\tManifest: item {row_item_id} -> sde='{man_ws}', database='{man_db}', "
                        f"schema='{man_owner}'", 'info')
        else:
            log_message(f"\titem {row_item_id} not in ItemsToMigratePhase1.csv; using CSV/base values", 'info')

    if row_wstype:
        workspace_type = row_wstype.upper()
    # precedence for database / owner / workspace: explicit CSV column > master manifest > run-level base
    if row_db:
        database_name = row_db
    elif man_db:
        database_name = man_db
    if row_owner:
        database_owner_name = row_owner
    elif man_owner:
        database_owner_name = man_owner
    if row_smdb:
        server_manager_db_name = row_smdb
    # Portal item folder: leave at the base/blank for migration publishes (item is created in the
    # publishing user's ROOT; the per-item Portal_Owner_User_Folder is applied at the Phase 8 reassign).
    if row_portal_folder:
        arcgisPortalFolderName = '' if row_portal_folder.strip().upper() == 'ROOT' else row_portal_folder
    # Server REST folder: an explicit server_folder wins ('ROOT' = root); otherwise resolve the mapped
    # Portal_Server_Folder from the source AGOL owner-folder via Folder_Map.csv ('MAXENT'/'MaxEnt' -> 'MaxEnt').
    if row_server_folder:
        arcgisServerFolderName = '' if row_server_folder.strip().upper() == 'ROOT' else row_server_folder
    elif row_agol_folder and folder_map_mod is not None:
        mapped_server = folder_map_mod.server_folder(row_agol_folder, _folder_map)
        arcgisServerFolderName = mapped_server
        log_message(f"\tFolder map: AGOL owner-folder '{row_agol_folder}' -> server folder "
                    f"'{mapped_server or '(root)'}'", 'info')

    workspace = row_ws or man_ws or base['workspace_full_path']
    if workspace == '':
        log_message("\tNo workspace for this row (no per-row 'workspace_full_path', no manifest match, and "
                    "no run-level workspace). Skipping.", 'error')
        return False
    if not os.path.exists(workspace):
        log_message(f"\tWorkspace not found for this row: {workspace}. Skipping.", 'error')
        return False
    workspace_factory = factory_for_workspace(workspace, workspace_type)
    try:
        arcpy.env.workspace = workspace
        log_message(f"Row workspace: {workspace}  ->  {database_name}.{database_owner_name}.* "
                    f"(server_manager_db='{server_manager_db_name}')")
    except Exception as e:
        log_message(f"\tFailed to set workspace {workspace}: {e}", 'error')
        return False
    if arcgisPortalFolderName or arcgisServerFolderName:
        log_message(f"\tRow folders: portal='{arcgisPortalFolderName}'; server='{arcgisServerFolderName}'", 'info')
    return True

def _folder_display_name(f):
    """Folder title/name across arcgis API versions. The older API yields plain dicts (key 'title'); arcgis
    >= 2.3 (here 2.4.1.1) yields `Folder` OBJECTS with `.name` (no `.get`, no `.title`). Handle both so the
    folder-existence check doesn't crash with "'Folder' object has no attribute 'get'"."""
    if isinstance(f, dict):
        return f.get('title') or f.get('name') or ''
    return getattr(f, 'title', None) or getattr(f, 'name', None) or ''


def ensure_portal_folder(folder_name):
    """Ensure the Portal content folder exists under the connected (publishing) user, creating it if
    missing, so the published item lands in it (PortalFolderName in the SD draft). Best-effort: logs and
    continues on any failure (the publish may still create it, else the item lands in the user's root).
    Never raises. The authoritative per-item folder under the FINAL owner is (re)applied at the Phase-8
    reassign; this only makes the publishing user's folder exist so PortalFolderName resolves now."""
    global gis
    if not folder_name or gis is None:
        return
    try:
        me = gis.users.me
        existing = {_folder_display_name(f).lower() for f in (getattr(me, 'folders', None) or [])}
        if folder_name.lower() in existing:
            log_message(f"Portal folder '{folder_name}' already exists for {me.username}", 'info')
            return
        # arcgis >= 2.3: gis.content.folders.create(); fall back to the deprecated create_folder() on older API.
        try:
            gis.content.folders.create(folder_name)
        except Exception:
            gis.content.create_folder(folder_name)
        log_message(f"Created Portal folder '{folder_name}' for {me.username}", 'info')
    except Exception as e:
        log_message(f"Could not ensure Portal folder '{folder_name}' (publish may still create it): {e}", 'info')

def get_feature_datasets():
    global feature_import_df, csv_import_file_path, specific_features_to_import
    feature_datasets = []
    
    if csv_import_file_path != '':
        # csv path supplied via the CLI positional arg or the .env file
        import_file = 'Y'
    else:
        import_file = get_user_input("Import from a csv file (Y/N)?", default_value='Y')
    if import_file.upper() == 'Y':
        if csv_import_file_path == '':
            print('\t*** CSV columns names: feature_name,title,summary,description,tags,credits,instance,portal_groups,categories')
            print("\t*** Optional columns: instance,portal_groups,categories")
            print("\t*** 'instance' may contain 'shared' or 'dedicated' or nothing. Nothing will default to 'shared'.")
            # get the csv file path from the user
            csv_import_file_path = get_user_input("Full path to the import file")
            if csv_import_file_path == "":
                log_message("No import file provided. Exiting...", 'error')
                return feature_datasets
        if not os.path.exists(csv_import_file_path):
            log_message(f"Import file {csv_import_file_path} does not exist. Exiting...", 'error')
            return feature_datasets
        if csv_import_file_path.split('.')[-1].lower() != 'csv':
            log_message(f"Invalid CSV file provided: {csv_import_file_path}. Exiting...", 'error')
            return feature_datasets
        try:
            feature_import_df = pd.read_csv(csv_import_file_path, encoding=get_file_encoding(csv_import_file_path))
            # set feature_datasets to the feature_name values in the import_df
            feature_datasets = feature_import_df['feature_name'].tolist()
        except Exception as e:
            log_message(f"Failed to read the import file {csv_import_file_path}: {e}", 'error')
    else:
        # get feature database information from the user
        specific_features_to_import = get_user_input("Name of the feature dataset(s) separated by commas", value_to_check=specific_features_to_import)
        if specific_features_to_import == "":
            print('\t*** Workspace:', arcpy.env.workspace)
            publish_all = get_user_input("Publish all feature datasets from the workspace (Y/N)?", default_value='N')
            if publish_all.upper() == 'Y':
                # determine all feature datasets in the geodatabase specified by workspace_full_path
                log_message('Gathering all features known to the geodatabase...')
                try:
                    feature_datasets = arcpy.ListRasters()
                    # print length of feature_datasets
                    log_message(f"Found {len(feature_datasets)} feature datasets in the workspace", 'info')
                    if limit_to_first_n_datasets > 0:
                        feature_datasets = feature_datasets[:limit_to_first_n_datasets]
                except Exception as e:
                    log_message(f"Failed to get the feature datasets: {e}", 'error')
        else:
            if ',' in specific_features_to_import:
                for feature in specific_features_to_import.split(','):
                    feature_datasets.append(format_feature_name(feature.strip()))
            else:
                feature_datasets = [format_feature_name(specific_features_to_import)]
    return feature_datasets

def stage_service(sddraft_filepath, sd_filepath):
    if os.path.exists(sd_filepath):
        log_message(f"Service definition file exists: {sd_filepath}. Skipping staging...", 'info')
        return True
    log_message(f"Start Staging service definition file '{sddraft_filepath}' to '{sd_filepath}'", 'info')
    service_staged = False
    stage_service = True
    while stage_service and not service_staged:
        try:
            arcpy.StageService_server(sddraft_filepath, sd_filepath)
            warnings = arcpy.GetMessages(1)
            errors = arcpy.GetMessages(2)
            log_message(warnings, 'info')
            log_message(errors, 'error')
            if errors != '' or errors:
                return service_staged
            # If data store is not registered
            if "24011" in warnings:
                # # Register data store
                # register_res = register_datastore_item(portal_url, portal_username, portal_password, sde_conn_file, data_store_name, federated_server_url)
                # if not register_res:
                log_message("Unable to register the data store with portal. Stopping all publishing!", 'error')
                exit()
                # # Stage the service again
                # stage_service = True
                stage_service = False
            else:
                stage_service = False
            if warnings == '':
                if os.path.exists(sd_filepath):
                    service_staged = True
        except arcpy.ExecuteError:
            log_message(arcpy.GetMessages(2), 'error')
            return service_staged
        except Exception as e:
            log_message(f"Failed to stage service: {e}", 'error')
            return service_staged
    if service_staged:
        log_message("Service staged successfully", 'info')
    else:
        log_message("Service staging failed", 'error')
    return service_staged

def record_published_to_ledger(feature_name, service_name=None):
    """Best-effort: mark the migration status-ledger row whose dest_feature_class == feature_name as
    'published_to_portal', recording the new Enterprise item id + service url. The ledger is keyed by
    SOURCE item_id (set by the copy phase, Step 3/3c); the publish phase only knows the dest
    feature_name, so we join on dest_feature_class. Skipped-with-warning if the helper is unavailable
    or no matching row exists (e.g. the copy phase did not record this item). Never raises.

    service_name (default feature_name) is the PUBLISHED service/item name used for the portal-item
    lookups -- it differs from feature_name when --CreateNewIfExisting bumped the service to a free
    suffixed name; the ledger JOIN still uses the original feature_name (the SDE feature class).

    Returns (source_item_id, enterprise_item_id) so the caller can drive the post-publish symbology
    apply; either/both may be None when nothing could be resolved."""
    lookup_name = service_name or feature_name
    if ledger_mod is None:
        log_message("ledger: helper not importable; published state not recorded", 'info')
        return None, None
    try:
        match_id = None
        for item_id, row in ledger_mod.get_ledger().rows.items():
            if (row.get('dest_feature_class') or '').lower() == feature_name.lower():
                match_id = item_id
                break
        if not match_id:
            log_message(f"ledger: no row with dest_feature_class == '{feature_name}'; published state "
                        f"not recorded (run the copy phase first, or add the row)", 'info')
            return None, None
        ent_item_id, ent_url = '', ''
        try:
            qry = 'title:"' + lookup_name + '"'
            items = gis.content.search(query=qry, max_items=10, sort_field='modified', sort_order='desc')
            for it in (items or []):
                if it.get('type', '') == 'Feature Service':
                    ent_item_id = it.get('id', '')
                    ent_url = getattr(it, 'url', '') or ''
                    break
        except Exception as e:
            log_message(f"ledger: could not look up published item for '{lookup_name}': {e}", 'info')
        # Fallback: the title search can miss the just-published item (indexing lag / title mismatch). Resolve
        # it from the on-server service instead (URL-matched), so we don't advance the state with a BLANK
        # enterprise_item_id (the bug where a row showed published_to_portal but no item id).
        if not ent_item_id:
            try:
                svcs = find_existing_services(lookup_name.replace(' ', '_'), arcgisServerFolderName)
                if svcs:
                    ent_item_id, ent_url = find_portal_item_for_service(svcs[0], lookup_name, '')
                    if ent_item_id:
                        log_message(f"ledger: resolved enterprise item for '{lookup_name}' via on-server "
                                    f"service lookup -> {ent_item_id}", 'info')
            except Exception as e:
                log_message(f"ledger: on-server fallback lookup for '{feature_name}' failed: {e}", 'info')
        notes = None
        if not ent_item_id:
            # Still couldn't resolve it -- record the state (the upload DID succeed) but flag it loudly and
            # leave a note so the missing id is visible and can be backfilled, instead of silently empty.
            log_message(f"ledger: WARNING item {match_id} published but enterprise_item_id could NOT be "
                        f"resolved for '{feature_name}'; recorded with a blank id -- resolve/backfill "
                        f"manually.", 'info')
            notes = _append_ledger_note(match_id,
                                        "published_to_portal recorded but enterprise_item_id unresolved "
                                        "(title + on-server lookups found no portal item); backfill manually.")
        ledger_mod.set_state(match_id, "published_to_portal",
                             enterprise_item_id=ent_item_id, enterprise_service_url=ent_url,
                             **({'notes': notes} if notes else {}))
        log_message(f"ledger: item {match_id} -> published_to_portal (enterprise item "
                    f"{ent_item_id or 'UNKNOWN'})", 'info')
        return match_id, (ent_item_id or None)
    except Exception as e:
        log_message(f"ledger update skipped: {e}", 'info')
    return None, None


def ledger_source_for_feature(feature_name):
    """Resolve the SOURCE item_id for a destination feature name via the ledger join
    (dest_feature_class == feature_name), so a publish FAILURE can be recorded against the right row.
    Returns the source item_id or None. Best-effort -- never raises."""
    if ledger_mod is None:
        return None
    try:
        for item_id, row in ledger_mod.get_ledger().rows.items():
            if (row.get('dest_feature_class') or '').lower() == feature_name.lower():
                return item_id
    except Exception as e:
        log_message(f"ledger: source lookup for '{feature_name}' failed: {e}", 'info')
    return None


# ----------------------------------------------------------------------------
# Existing-service guard helpers
# ----------------------------------------------------------------------------
# Before creating/publishing a service, check whether one of the same name already exists on the federated
# server. These helpers (a) find any matching server Service object(s), (b) read each one's manifest to test
# whether it references the SAME SDE feature class by reference, and (c) resolve the Enterprise portal item
# for an existing service so it can be recorded in the ledger. All are best-effort -- a transient admin/REST
# failure returns an empty/"unknown" result rather than raising, so publishing is never blocked by a hiccup.

def _get_federated_server():
    """Return the portal's first federated ArcGIS Server admin object, or None. Best-effort."""
    try:
        servers = gis.admin.servers.list() if gis is not None else []
        return servers[0] if servers else None
    except Exception as e:
        log_message(f"Could not list federated servers (existing-service check skipped): {e}", 'info')
        return None

def _service_name_of(svc):
    """Best-effort read of a server Service object's serviceName (falls back to parsing its URL)."""
    for getter in (lambda: svc.properties['serviceName'],
                   lambda: svc.properties.serviceName,
                   lambda: getattr(svc, '_serviceName', '')):
        try:
            v = getter()
            if v:
                return str(v)
        except Exception:
            pass
    try:
        # .../<name>/MapServer or .../<name>/FeatureServer -> the segment before the type
        parts = (svc.url or '').rstrip('/').split('/')
        if len(parts) >= 2:
            return parts[-2]
    except Exception:
        pass
    return ''

def find_existing_services(service_name, server_folder=''):
    """Return a list of server Service objects whose serviceName matches service_name (case-insensitive),
    searching the target server folder first, then root, then every other folder. Best-effort -> []."""
    matches = []
    server = _get_federated_server()
    if server is None:
        return matches
    target = (service_name or '').replace(' ', '_').lower()
    if not target:
        return matches
    try:
        all_folders = list(server.services.folders)
    except Exception:
        all_folders = ['/']
    # Ordered, de-duped folder search list: target folder, root, then the rest.
    search_folders = []
    for f in ([server_folder] if server_folder else []) + ['/'] + all_folders:
        fnorm = f or '/'
        if fnorm not in search_folders:
            search_folders.append(fnorm)
    for folder in search_folders:
        try:
            svc_list = server.services.list(folder=(None if folder == '/' else folder))
        except Exception as e:
            log_message(f"\tCould not list services in folder '{folder}': {e}", 'info')
            continue
        for svc in (svc_list or []):
            try:
                if _service_name_of(svc).lower() == target:
                    matches.append(svc)
            except Exception:
                pass
    return matches

def service_references_dataset(svc, qualified_dataset_name):
    """Return (referenced: bool, detail: str). Reads the service manifest and tests whether any referenced
    dataset matches the expected SDE feature class (qualified name, e.g. RRGOrg.ws.World_Provinces). Matches
    case-insensitively on the full qualified onServerName/onPremisePath (equality or '.'-suffix), then falls
    back to the bare table name. Best-effort -> (False, reason) when the manifest can't be read/parsed."""
    expected = (qualified_dataset_name or '').strip().lower()
    expected_bare = expected.split('.')[-1] if expected else ''
    if not expected:
        return False, "no expected dataset name to compare"
    try:
        raw = svc.service_manifest('json')
    except Exception as e:
        return False, f"manifest unavailable: {e}"
    try:
        manifest = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        return False, f"manifest parse failed: {e}"
    found = []
    try:
        for db in (manifest.get('databases') or []):
            for ds in (db.get('datasets') or []):
                for k in ('onServerName', 'onPremisePath'):
                    name = ds.get(k) or ''
                    if name:
                        found.append(name)
    except Exception as e:
        return False, f"manifest structure unexpected: {e}"
    found_lower = [n.lower() for n in found]
    for n in found_lower:
        if n == expected or n.endswith('.' + expected):
            return True, f"matched dataset '{n}' to expected '{expected}'"
    if expected_bare:
        for n in found_lower:
            bare = n.replace('\\', '/').split('/')[-1].split('.')[-1]
            if bare == expected_bare:
                return True, f"matched bare table '{bare}' (in '{n}') to expected '{expected_bare}'"
    return False, f"no referenced dataset matched '{expected}' (found: {found})"

def find_portal_item_for_service(svc, feature_name, title=''):
    """Resolve the Enterprise portal item id + url for an already-published service. Searches portal content
    by title/feature name and prefers an item whose URL matches the service URL; otherwise returns the first
    Feature Service. Best-effort -> ('', service_url-or-'')."""
    svc_url = ''
    try:
        svc_url = (svc.url or '') if svc is not None else ''
    except Exception:
        svc_url = ''
    try:
        seen, candidates = set(), []
        for q in ([('title:"' + title + '"')] if title else []) + ['title:"' + feature_name + '"']:
            for it in (gis.content.search(query=q, max_items=25, sort_field='modified', sort_order='desc') or []):
                if it.id not in seen:
                    seen.add(it.id)
                    candidates.append(it)
        # service-url match first (most reliable join), restricted to service-type items
        norm = svc_url.lower().split('/services/')[-1].rstrip('/') if svc_url else ''
        if norm:
            for it in candidates:
                it_url = (getattr(it, 'url', '') or '').lower()
                if norm in it_url and it.type in ('Feature Service', 'Map Image Layer', 'Map Service'):
                    return it.id, (getattr(it, 'url', '') or '')
        # fall back to the first Feature Service
        for it in candidates:
            if it.type == 'Feature Service':
                return it.id, (getattr(it, 'url', '') or '')
    except Exception as e:
        log_message(f"Could not resolve portal item for existing service '{feature_name}': {e}", 'info')
    return '', svc_url

def _append_ledger_note(src_id, note):
    """Append ' | '-joined note text to a ledger row's notes column (preserving any existing notes)."""
    try:
        existing = ((ledger_mod.get_ledger().rows.get(src_id) or {}).get('notes') or '').strip()
        return (existing + ' | ' + note) if existing else note
    except Exception:
        return note

def record_existing_service_as_published(feature_name, svc, title, note):
    """Record an EXISTING (already on-server) service as this item's published_to_portal milestone: resolve
    the source ledger row (dest_feature_class join), find the Enterprise item id/url for the existing service,
    set the state, and append a note explaining the decision. Best-effort -- never raises."""
    if ledger_mod is None:
        log_message("ledger: helper not importable; existing-service state not recorded", 'info')
        return
    try:
        src_id = ledger_source_for_feature(feature_name)
        if not src_id:
            log_message(f"ledger: no row with dest_feature_class == '{feature_name}'; existing-service "
                        f"state not recorded", 'info')
            return
        ent_item_id, ent_url = find_portal_item_for_service(svc, feature_name, title)
        ledger_mod.set_state(src_id, "published_to_portal",
                             enterprise_item_id=ent_item_id, enterprise_service_url=ent_url,
                             notes=_append_ledger_note(src_id, note))
        log_message(f"ledger: item {src_id} -> published_to_portal via existing service "
                    f"(enterprise item {ent_item_id or 'UNKNOWN -- resolve manually'})", 'info')
    except Exception as e:
        log_message(f"ledger: could not record existing-service state for '{feature_name}': {e}", 'info')

def record_ledger_note(feature_name, note):
    """Append a note to this item's ledger row (dest_feature_class join) WITHOUT changing its state.
    Best-effort -- never raises."""
    if ledger_mod is None:
        return
    try:
        src_id = ledger_source_for_feature(feature_name)
        if src_id:
            ledger_mod.update(src_id, notes=_append_ledger_note(src_id, note))
    except Exception as e:
        log_message(f"ledger: could not record note for '{feature_name}': {e}", 'info')

def _split_trailing_int(name):
    """Split a trailing '_<int>' suffix off a name: 'Foo_polygons_1' -> ('Foo_polygons', 1);
    'Foo_polygons' -> ('Foo_polygons', 0). Used to increment the suffix for --CreateNewIfExisting."""
    if '_' in name:
        stem, tail = name.rsplit('_', 1)
        if tail.isdigit():
            return stem, int(tail)
    return name, 0

def next_free_service_name(base_name, server_folder=''):
    """Return the next service name (suffix-incremented) that does NOT already exist on the federated server,
    starting from base_name's trailing integer + 1 (e.g. 'X_polygons_1' -> first free of 'X_polygons_2',
    '_3', ...; 'X_polygons' -> 'X_polygons_1', '_2', ...). Returns None if none is free in a sane range or
    the server can't be queried (caller then falls back to an error). Best-effort -- never raises."""
    name = (base_name or '').replace(' ', '_')
    if not name:
        return None
    stem, n = _split_trailing_int(name)
    try:
        for _ in range(1, 1000):
            n += 1
            candidate = f"{stem}_{n}"
            if not find_existing_services(candidate, server_folder):
                return candidate
    except Exception as e:
        log_message(f"\tCould not compute a free service name from '{base_name}': {e}", 'info')
    return None

def resolve_existing_service_action(feature_name, qualified_dataset_name, title):
    """Existing-service guard, run BEFORE creating/publishing a service. Decides what to do when a service of
    the same name already exists on the federated server:
      * --OverrideExisting set                          -> ('proceed', None) (overwrite/republish; note recorded).
      * existing service references the SAME SDE feature -> ('use_existing', None) (do NOT republish; record
        published_to_portal + enterprise item id + note). This is automatic and independent of the flags.
      * --UseExisting set (same ref not confirmed)      -> ('use_existing', None) (assume existing is intended).
      * --CreateNewIfExisting set (same ref not confirmed) -> ('create_new', '<free suffixed name>') (publish a
        NEW service under that free name, still referencing OUR SDE feature class).
      * none of the above                               -> ('error', None) (record a ledger error; skip row).
    Returns (action, new_service_name). When no service of this name exists, returns ('proceed', None).
    A failure to query the server returns ('proceed', None) so a transient admin error does not block
    publishing (the upload step still guards against a true name clash). Precedence: override > use > create."""
    service_name = (feature_name or '').replace(' ', '_')
    existing = find_existing_services(service_name, arcgisServerFolderName)
    if not existing:
        return 'proceed', None
    log_message(f"Service name '{service_name}' already exists on the server "
                f"({len(existing)} matching service(s) found).", 'info')
    # 1) Explicit override wins: republish over the existing service.
    if override_existing:
        note = f"--OverrideExisting set: overwriting existing service '{service_name}'."
        log_message(note, 'info')
        record_ledger_note(feature_name, note)
        return 'proceed', None
    # 2) Auto-detect a service that references the SAME SDE feature class by reference.
    detail = ''
    for svc in existing:
        referenced, detail = service_references_dataset(svc, qualified_dataset_name)
        log_message(f"\tExisting service '{_service_name_of(svc)}' reference check: {detail}", 'info')
        if referenced:
            note = (f"Existing service '{service_name}' already references the same SDE feature class "
                    f"'{qualified_dataset_name}' ({detail}); used existing service (not republished).")
            log_message(note, 'info')
            record_existing_service_as_published(feature_name, svc, title, note)
            return 'use_existing', None
    # 3) --UseExisting: accept the existing service as the intended one.
    if use_existing:
        svc = existing[0]
        note = (f"--UseExisting set: assuming existing service '{service_name}' is the intended feature "
                f"(same SDE reference NOT confirmed: {detail}); used existing (not republished).")
        log_message(note, 'info')
        record_existing_service_as_published(feature_name, svc, title, note)
        return 'use_existing', None
    # 4) --CreateNewIfExisting: leave the existing service alone, publish a NEW one under a free suffixed name
    #    that still references OUR SDE feature class (qualified_dataset_name).
    if create_new_if_existing:
        new_name = next_free_service_name(service_name, arcgisServerFolderName)
        if new_name:
            note = (f"--CreateNewIfExisting set: existing service '{service_name}' is a different dataset "
                    f"(same SDE reference NOT confirmed: {detail}); publishing a NEW service '{new_name}' "
                    f"referencing '{qualified_dataset_name}'.")
            log_message(note, 'info')
            record_ledger_note(feature_name, note)
            return 'create_new', new_name
        log_message(f"--CreateNewIfExisting set but could not compute a free service name from "
                    f"'{service_name}'; skipping this item.", 'error')
        return 'error', None
    # 5) Nothing told us what to do -> record an error (auto-funneled to the ledger by log_message) and skip.
    log_message(f"Service name '{service_name}' already exists and does not reference the same SDE feature "
                f"class '{qualified_dataset_name}' ({detail}). None of --OverrideExisting / --UseExisting / "
                f"--CreateNewIfExisting was set; skipping this item.", 'error')
    return 'error', None


# DataDump cache (same location the Step 6 symbology apply reads). Holds the captured AGOL item JSON,
# including the ORIGINAL item description. Override with env METADATA_DUMP_DIR.
METADATA_DUMP_DIR = os.getenv(
    "METADATA_DUMP_DIR",
    r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\DataDump")

def get_source_description(src_item_id):
    """Return the ORIGINAL AGOL item's description (HTML) from the cached DataDump
    'AGOL_<id>_description_*.json' (or '_get'), so the published Enterprise items can mirror the source
    description instead of the CSV summary. Returns '' if not found. Never raises."""
    if not src_item_id:
        return ''
    try:
        if not os.path.isdir(METADATA_DUMP_DIR):
            log_message(f"\t(DataDump dir not found for source description: {METADATA_DUMP_DIR})", 'info')
            return ''
        prefix = f"agol_{src_item_id.lower()}"
        candidates = [fn for fn in os.listdir(METADATA_DUMP_DIR)
                      if fn.lower().startswith(prefix) and fn.lower().endswith('.json')
                      and '_data' not in fn.lower()
                      and ('_description' in fn.lower() or '_get' in fn.lower())]
        # prefer the _description file over _get
        candidates.sort(key=lambda f: ('_description' not in f.lower(), f))
        for fn in candidates:
            with open(os.path.join(METADATA_DUMP_DIR, fn), 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            desc = data.get('description')
            if desc:
                log_message(f"\tSource description loaded from {fn} ({len(desc)} chars)", 'info')
                return desc
    except Exception as e:
        log_message(f"\t(could not read source description for {src_item_id}: {e})", 'info')
    return ''

def validate_and_update_portal_item(current_title, new_title, portal_group_names='', categories='', src_item_id=''):
    global portal_group_dict
    log_message(f"Validating and updating portal item for {current_title} to {new_title}", 'info')
    item_id = ''
    try:
        qry = 'title:"' + current_title + '"' + ' OR title:"' + new_title + '"'
        gis_items = gis.content.search(query=qry, max_items=10, sort_field='modified', sort_order='desc')
        if gis_items or (not gis_items is None):
            # get the first result (used below for categories/groups)
            gis_item = gis_items[0]
            item_id = gis_item.get('id', '')
            if item_id != '':
                # Title + description sync across the PUBLISHED PAIR. A referenced publish creates a
                # MapServer + FeatureServer that share the service name as their title, so update BOTH so
                # the two portal items match (decision #9). The description is taken from the ORIGINAL AGOL
                # item (cached _description.json) rather than the concise CSV summary.
                src_description = get_source_description(src_item_id) if src_item_id else ''
                for pub_item in gis_items:
                    try:
                        p_type = pub_item.get('type', '')
                        p_url = (pub_item.get('url', '') or '')
                        p_name = (pub_item.get('name', '') or '')
                        # restrict to the just-published pair (Feature/Map service carrying the service name)
                        if p_type not in ('Feature Service', 'Map Service', 'Map Image Layer'):
                            continue
                        if (f"/{current_title}/" not in p_url) and (current_title.lower() not in p_name.lower()):
                            continue
                        props = {}
                        p_title = pub_item.get('title', '')
                        if new_title and p_title != new_title:
                            props['title'] = new_title
                        if src_description:
                            props['description'] = src_description
                        if props:
                            pub_item.update(item_properties=props)
                            log_message(f"\tUpdated {p_type} item {pub_item.get('id','')}: "
                                        f"{', '.join(props.keys())}", 'info')
                    except Exception as e:
                        log_message(f"Failed to update item {pub_item.get('id','')}: {e}", 'error')
                    
                '''
                try:
                    # Attempt to update popupInfo title in order to enable the Data JSON
                    popupModified = False
                    hasLayers = False
                    if 'layers' in gis_item:
                        for layer in gis_item.layers:
                            # Update popupInfo title for each layer
                            hasLayers = True
                            try:
                                if 'popupInfo' in layer:
                                    popup_info = layer.popupInfo
                                    popup_info['title'] = new_title
                                    layer.manager.update_definition({'popupInfo': popup_info})
                                    popupModified = True
                                    log_message(f"\tUpdated popupInfo title to '{new_title}' for layer {layer.name}", 'info')
                                elif 'popupInfo' in layer.properties:
                                    popup_info = layer.properties.popupInfo
                                    popup_info['title'] = new_title
                                    layer.manager.update_definition({'popupInfo': popup_info})
                                    popupModified = True
                                    log_message(f"\tUpdated popupInfo title to '{new_title}' for layer {layer.properties.name}", 'info')
                            except Exception as e:
                                log_message(f"Failed to update popupInfo title: {e}", 'error')
                    else:
                        log_message(f"Item does not have layers", 'info')
                    if not popupModified:
                        if hasLayers:
                            log_message(f"Failed to update popupInfo title for any layer", 'error')
                        else:
                            log_message(f"Item does not have layers", 'info')
                            # attempt to create a new layer
                            img_svc_url = gis_item.url
                            new_lyr = Service(url_or_item=img_svc_url, server=gis)
                except Exception as e:
                    log_message(f"Failed to update popupInfo title: {e}", 'error')
                '''
                try:
                    if categories is not None and not (isinstance(categories, float) and pd.isnull(categories)) and categories != '':
                        if isinstance(categories, list):
                            category_list = categories
                        else:
                            category_list = str(categories).split(',')
                        # drop blanks and stray 'nan' (empty CSV cell read as NaN -> 'nan')
                        category_list = [c.strip() for c in category_list
                                         if c is not None and c.strip() != '' and c.strip().lower() != 'nan']
                        if category_list != []:
                            gis_item.update(item_properties={"categories": category_list})
                            log_message(f"\tUpdated item categories to {category_list}", 'info')
                except Exception as e:
                    log_message(f"Failed to update item categories: {e}", 'error')
                
                try:
                    if portal_group_names != '':
                        portal_group_ids = []
                        sharing_portal_group_ids = []
                        if isinstance(portal_group_names, str):
                            portal_group_names_list = portal_group_names.split(',')
                        elif isinstance(portal_group_names, list):
                            portal_group_names_list = portal_group_names
                        else:
                            try:
                                # try to convert portal_group_names to a string
                                portal_group_names_str = str(portal_group_names)
                                portal_group_names_list = portal_group_names_str.split(',')
                            except:
                                portal_group_names_list = [portal_group_names]
                        for portal_group_name in portal_group_names_list:
                            # Search for the group by name and get its ID
                            portal_group_name = portal_group_name.strip()
                            # lookup the portal group id in the global dictionary
                            portal_group = portal_group_dict.get(portal_group_name, None)
                            if portal_group is None:
                                # search for the portal group by name
                                group_search = gis.groups.search(portal_group_name)
                                if group_search:
                                    portal_group = group_search[0]
                                    # log_message('group_search return:', 'info', portal_group)
                                    if portal_group:
                                        # store the portal group name and id in the global dictionary
                                        portal_group_dict[portal_group_name] = portal_group
                                        
                            if portal_group:
                                # log_message('group id: ', log_level='info', message_details=portal_group.get('id', ''))
                                # log_message('group capabilities: ', log_level='info', message_details=portal_group.get('capabilities', []))
                                group_capabilities = portal_group.get('capabilities', [])
                                if group_capabilities != []:
                                    if 'updateitemcontrol' in group_capabilities:
                                        sharing_portal_group_ids.append(portal_group.get('id', ''))
                                        continue
                                portal_group_ids.append(portal_group.get('id', ''))
                        if portal_group_ids != [] or sharing_portal_group_ids != []:
                            if portal_group_ids != []:
                                log_message(f"Sharing portal item with groups", 'info', message_details=portal_group_ids)
                                gis_item.share(groups=portal_group_ids)
                            if sharing_portal_group_ids != []:
                                log_message(f"Sharing portal item with shared update capable groups", 'info', message_details=sharing_portal_group_ids)
                                gis_item.share(groups=sharing_portal_group_ids, allow_members_to_edit=True)
                            log_message(f"Updated portal item with groups: {portal_group_names}", 'info')
                except Exception as e:
                    log_message(f"Failed to update item groups: {e}", 'error')
    except Exception as e:
        log_message(f"Failed to update item '{new_title}' ({item_id}): {e}", 'error')
    if item_id != '':
        log_message(f"Validated portal item '{new_title}' ({item_id})", 'info')
    return item_id


# Begin Main

init_logging()

cli_args = parse_cli_args()

init_global_variables()

# CLI args take precedence over .env (which still falls back to interactive prompts).
apply_cli_overrides(cli_args)

repository_id_error = False
if repository_id == '':
    repository_id_known = get_user_input("Do you know the repository ID (Y/N)?", default_value='Y')
    if repository_id_known.upper() == 'Y':
        repository_id = get_user_input("Repository ID", default_value='0')
    else:
        use_default_repository_id = get_user_input("Would you like to use '0' as the repository ID (Y/N)?", default_value='N')
        if use_default_repository_id.upper() == 'Y':
            repository_id = '0'
        else:
            repository_id_error = True
if repository_id != '':
    repository_id_error = False
    try:
        repository_id_int = int(repository_id)
        if repository_id_int < 0:
            repository_id_error = True
    except:
        repository_id_error = True
if repository_id_error:
    log_message('\t*** Find the RepositoryID in the manifest.xml of a service manually published to Portal from Pro for the same connection. See \\nbs-app2\c$\arcgisserver\directories\arcgissystem\arcgisinput.')
    get_user_input('Press enter to quit...')
    if repository_id == '':
        log_message('\t*** RepositoryID is required.', 'error')
    else:
        log_message("\t*** Invalid repository ID '{repository_id}'", 'error')
    exit()
    
env_set = set_arcpy_environment()
if not env_set:
    exit()

if stageService:
    # prompt to use https://maps.rrgnbs.com/arcgisserver as the federated_server_url or input a different url
    federated_server_url = get_user_input("Federated server URL", default_value='https://maps.rrgnbs.com/arcgisserver', value_to_check=federated_server_url)
    connected_to_portal = connect_to_portal()
    if not connected_to_portal:
        exit()

feature_datasets = get_feature_datasets()
if feature_datasets == []:
    log_message("No feature datasets found. Exiting...", 'error')
    exit()

if instance_type == 'dedicated':
    is_shared_instance = False
elif instance_type == 'shared':
    is_shared_instance = True
else:
    # prompt user for is_shared_instance
    publish_as_shared = get_user_input("Published as shared instance(s) by default (Y/N)?", default_value='Y')
    if publish_as_shared.upper() == 'Y':
        is_shared_instance = True
    else:
        is_shared_instance = False
    
# Portal/server folders are resolved PER-ROW (CSV columns portal_folder / server_folder, or the mapped
# Portal_Server_Folder via agol_owner_folder + Folder_Map.csv), so do NOT prompt here. Any run-level value
# (.env / --portal-folder / --server-folder) is only the fallback for rows that omit them. A 'ROOT' sentinel
# (any case) means the root / no folder -> normalized to '' here and in the per-row override path.
if (arcgisPortalFolderName or '').strip().upper() == 'ROOT':
    arcgisPortalFolderName = ''
if (arcgisServerFolderName or '').strip().upper() == 'ROOT':
    arcgisServerFolderName = ''
log_message(f"Run-level folders (fallback for rows that omit them): portal='{arcgisPortalFolderName}', "
            f"server='{arcgisServerFolderName}' (blank = root)", 'info')

default_empty_tags = "by reference"
default_tags = get_user_input("Tags to be appended to all datasets in this import", value_to_check=default_tags)
if default_tags != "":
    default_empty_tags = default_tags
    
# Capture the run-level (CLI / .env / prompt) environment as the BASE. Optional per-row CSV columns
# (workspace_full_path / database_name / database_owner / server_manager_db / workspace_type) override
# these per row, so one CSV can publish across multiple databases and schemas in a single run. Rows
# without those columns fall back to the base; apply_row_env_overrides resets to the base each row so
# an override never bleeds into the next row.
base_env = {
    'workspace_full_path': workspace_full_path,
    'workspace_type': workspace_type,
    'database_name': database_name,
    'database_owner_name': database_owner_name,
    'server_manager_db_name': server_manager_db_name,
    'arcgisPortalFolderName': arcgisPortalFolderName,
    'arcgisServerFolderName': arcgisServerFolderName,
}

if feature_import_df.empty:
    # JSON data to import will come from the RRGEnterprise_all_json_data.json file within the Input directory
    # set the input_path to the Input directory within the script's directory
    input_path = current_dir
    # Create the Input directory if it does not exist
    if os.path.exists(os.path.join(current_dir, 'Input')):
        input_path = os.path.join(current_dir, 'Input')
    all_json_data_file_path = os.path.join(input_path, 'RRGEnterprise_all_json_data.json')

# cycle through all feature datasets in feature_datasets
len_feature_datasets = len(feature_datasets)
log_message(f"Processing {len_feature_datasets} feature datasets")
for feature_dataset in feature_datasets:
    current_feature_name = ''   # clear between items so a stray error isn't attributed to the prior feature
    log_message(f"****************************************************", 'info', message_details=None, reset_log_hist=True)

    feature_dataset = str(feature_dataset)
    
    # Output locations for the service definition draft and final .sd file
    sddraft_output_filepath = os.path.join(sd_output_dir, f"{feature_dataset}.sddraft")
    sd_output_filepath = sddraft_output_filepath.replace('.sddraft', '.sd')
    log_message(sddraft_output_filepath, 'info')
    log_message(sd_output_filepath, 'info')
    
    tags = ''
    summary = ''
    title = ''
    description = ''
    credits = ''
    feature_is_shared_instance = is_shared_instance
    portal_groups = ''
    categories = ''
    spatialReference = ''
    data_found = False
    feature_name = feature_dataset.split(".")[-1]
    # Attribute any 'error' logged during this item's publish to its ledger row (see _record_error_to_ledger).
    # This is the dest_feature_class the ledger join uses; later in-place edits to feature_name (e.g. space->_)
    # don't affect the join because the CSV feature_name has no spaces.
    current_feature_name = feature_name

    if feature_import_df.empty:
        feature_dataset_DBpath = feature_dataset
        feature_dataset_json = find_json_data(feature_dataset)
        if feature_dataset_json:
            data_found = True
            feature_name = feature_dataset_json.get('name', feature_name)
            title = feature_dataset_json.get('nbs_title', '')
            summary = feature_dataset_json.get('nbs_summary', '')
            description = feature_dataset_json.get('nbs_description', '')
            tags = feature_dataset_json.get('nbs_tags', '')
            spatialReference = feature_dataset_json.get('nbs_spatialReference', '')
        else:
            log_message('Summary set to feature name', 'info')
            summary = feature_name
    else:
        # get data from the import file
        feature_dataset_row = feature_import_df.loc[feature_import_df['feature_name'] == feature_name]
        if feature_dataset_row.empty:
            log_message(f"\tERROR: No data found for {feature_name}", 'error')
            feature_dataset_DBpath = format_feature_name(feature_name)
        else:
            data_found = True
            # Honor the run-scope allowlist (MIGRATION_ITEM_ALLOWLIST): skip a CSV row whose SOURCE item_id is
            # outside the current batch's scope, so --max-items bounds publishing too. No-op when the env var
            # is unset or the row has no item_id (then we can't scope it and publish it as before).
            if ledger_mod is not None:
                row_item_id = get_row_value(feature_dataset_row, 'item_id', 'agol_item_id')
                if row_item_id and not ledger_mod.item_allowed(row_item_id):
                    log_message(f"Skipping '{feature_name}' (item {row_item_id}): outside run-scope "
                                f"allowlist (MIGRATION_ITEM_ALLOWLIST).", 'info')
                    continue
                # Ledger work-selection gate -- the SAME helper the deprecate gate / resume use, so one place
                # decides "is this row workable". row_eligible_to_advance(row, done_state='published_to_portal')
                # skips a row that:
                #   * carries a recorded error (e.g. still at 'copied_to_gdb' after a failed copy/load) --
                #     must be resolved + cleared (ledger clear_errors) before the next run picks it up; we do
                #     NOT publish on top of a bad/incomplete SDE load, and
                #   * has already reached 'published_to_portal' (on the server already -- re-publishing only
                #     re-detects the existing service + re-appends a 'used existing service' note each sweep).
                # --OverrideExisting forces a republish of an ALREADY-PUBLISHED row, but never of an errored
                # (or out-of-scope) one. A not-yet-in-ledger row (no row object) is published as before.
                ledger_row = ledger_mod.get_row(row_item_id) if row_item_id else None
                if ledger_row is not None:
                    eligible, why = ledger_mod.row_eligible_to_advance(
                        ledger_row, done_state="published_to_portal")
                    if (not eligible) and override_existing and not ledger_mod.row_has_error(ledger_row):
                        # Only the 'already reached published_to_portal' reason remains (allowlist passed
                        # above, no error) -- honor --OverrideExisting and force the republish.
                        log_message(f"--OverrideExisting: re-publishing '{feature_name}' (item "
                                    f"{row_item_id}) despite ledger gate ({why}).", 'info')
                        eligible = True
                    if not eligible:
                        log_message(f"Skipping '{feature_name}' (item {row_item_id}): {why}", 'info')
                        continue
            # Apply OPTIONAL per-row workspace/database/schema overrides BEFORE building the qualified
            # name (format_feature_name uses the database/owner globals). Skip the row if its workspace
            # is missing/invalid. Rows without the override columns keep the run-level base env.
            if not apply_row_env_overrides(feature_dataset_row, base_env):
                continue
            feature_dataset_DBpath = format_feature_name(feature_name)
            title = feature_dataset_row['title'].values[0]
            summary = feature_dataset_row['summary'].values[0]
            description = feature_dataset_row['description'].values[0]
            tags = feature_dataset_row['tags'].values[0]
            credits = feature_dataset_row['credits'].values[0]
            if 'instance' in feature_dataset_row:
                instance = feature_dataset_row['instance'].values[0].lower()
                if instance == 'dedicated':
                    feature_is_shared_instance = False
            if 'portal_groups' in feature_dataset_row:
                pg = feature_dataset_row['portal_groups'].values[0]
                portal_groups = '' if pd.isnull(pg) else str(pg).strip()
            if 'categories' in feature_dataset_row:
                cat = feature_dataset_row['categories'].values[0]
                categories = '' if pd.isnull(cat) else str(cat).strip()
    
    if not data_found:
        if len_feature_datasets < 10:
            log_message("Prompt user for missing data", 'info')
            print(f'Enter the following information for {feature_name}:')
            title = get_user_input("Title", default_value=feature_name)
            summary = get_user_input("Summary", default_value=title)
            description = get_user_input("Description", default_value=summary)
            tags = get_user_input("Tags", default_value=default_empty_tags)
        else:
            log_message(f"\tERROR: No json data found for {feature_name}", 'error')
            continue
    
    title = remove_non_ascii(title)
    summary = remove_non_ascii(summary)
    description = remove_non_ascii(description)
    credits = remove_non_ascii(credits)
    tags = remove_non_ascii(tags)
    if spatialReference != '':
        if spatialReference == 'GCS_WGS_1984':
            spatialReference = 'WGS84,wkid4326'
        if tags == "" or tags is None:
            tags = spatialReference
        else:
            tags = tags + ',' + spatialReference
    elif tags == "" or tags is None:
        log_message(f"Empty Tags set to '{default_empty_tags}'", 'info')
        tags = default_empty_tags
    else:
        if default_tags != "":
            tags += ',' + default_tags
    
    log_message(f"feature: {feature_dataset_DBpath}", 'info')
    log_message(f"\tImageSDDraft: {sddraft_output_filepath}", 'info')
    log_message(f"\tfeature Name: {feature_name}", 'info')
    log_message(f"\tTitle: {title}", 'info')
    log_message(f"\tSummary: {summary}", 'info')
    log_message(f"\tDescription: {description}", 'info')
    log_message(f"\tTags: {tags}", 'info')
    log_message(f"\tIs Shared Instance: {feature_is_shared_instance}", 'info')
    
    if title == "" or summary == "" or description == "" or title is None or summary is None or description is None:
        if title == "" or title is None:
            title = feature_name
        if summary == "" or summary is None:
            summary = title
        if description == "" or description is None:
            description = summary
        if title == "" or summary == "" or description == "" or title is None or summary is None or description is None:
            log_message(f"\tMissing title, summary or description.", 'error')
            continue

    # The PUBLISHED service name. Defaults to the SDE feature-class name (feature_name), but
    # --CreateNewIfExisting can bump it to a free suffixed name below so a new service can coexist with an
    # existing same-name one. feature_name itself stays the SDE feature class (data reference + ledger join).
    service_name = (feature_name or '').replace(' ', '_')

    # Existing-service guard: BEFORE building/publishing the service, check whether one of the same name
    # already exists on the federated server (only relevant when we are actually publishing). Depending on the
    # --OverrideExisting / --UseExisting / --CreateNewIfExisting flags and whether the existing service
    # references the SAME SDE feature class, this either proceeds (overwrite), uses the existing service
    # (records it as published and skips republishing), publishes a NEW suffixed service, or records a ledger
    # error and skips the item. See resolve_existing_service_action.
    if stageService and uploadToServer:
        existing_action, new_service_name = resolve_existing_service_action(
            feature_name, feature_dataset_DBpath, title)
        if existing_action in ('error', 'use_existing'):
            # 'error': recorded against the ledger row by log_message's funnel; 'use_existing': already
            # recorded as published_to_portal. Either way there is nothing more to publish for this item.
            continue
        if existing_action == 'proceed' and override_existing:
            # Force-regenerate any stale by-reference SD/draft from a PRIOR non-override run so the new SD is
            # staged with overwriteExistingService=True baked in (the upload won't overwrite otherwise).
            file_removed = remove_file(sddraft_output_filepath)
            file_removed = remove_file(sd_output_filepath)
        if existing_action == 'create_new' and new_service_name:
            # Publish under the new free name. Re-point the SD/draft paths at it and drop any stale files so the
            # draft we stage carries the NEW service name (a leftover draft would bake in the old name).
            service_name = new_service_name
            log_message(f"Publishing a NEW service '{service_name}' (referencing SDE feature class "
                        f"'{feature_dataset_DBpath}') instead of overwriting the existing same-name service.",
                        'info')
            sddraft_output_filepath = os.path.join(sd_output_dir, f"{service_name}.sddraft")
            sd_output_filepath = sddraft_output_filepath.replace('.sddraft', '.sd')
            file_removed = remove_file(sddraft_output_filepath)
            file_removed = remove_file(sd_output_filepath)

    errors = {}
    warnings = {}
    messages = {}
    total_warnings = 0
    if os.path.exists(sddraft_output_filepath):
        log_message(f"Using existing Service Draft", 'info')
    else:
        sddraft_result = {}
        try:
            # append database name and schema name to feature_name to get feature_dataset_path
            feature_dataset_path = os.path.join(arcpy.env.workspace, feature_dataset_DBpath)
            if not arcpy.Exists(feature_dataset_path):
                log_message(f"feature dataset {feature_dataset_path} does not exist. Skipping...", 'error')
                continue
            else:
                # ensure the feature_name does not have any spaces
                feature_name = feature_name.replace(" ", "_")
                tags = tags.replace(" ", "_")
                
                # project_template_path = r"C:\MS\OneDrive - RRG Nature Based Solutions, Inc\Documents\ArcGIS\ProjectTemplates\MapWithAllSDEDatabases.aptx"
                
                temp_project_path = os.path.join(sd_output_dir, f"{feature_name}.aprx")
                if not os.path.exists(temp_project_path):
                    log_message(f"Creating temporary project from {project_template_path}", 'info')
                    aprx = arcpy.mp.ArcGISProject(project_template_path)
                    
                    log_message(f"Saving temporary project {temp_project_path}", 'info')
                    aprx.saveACopy(temp_project_path)
                else:
                    log_message(f"Temporary project {temp_project_path} exists")
                    
                log_message(f"Opening temporary project {temp_project_path}", 'info')
                aprx = arcpy.mp.ArcGISProject(temp_project_path)
                
                log_message("Getting the map from the temporary project", 'info')
                maps = aprx.listMaps()
                if len(maps) == 0:
                    log_message(f"Creating map for {feature_name}", 'info')
                    temp_map = aprx.createMap(feature_name)
                    aprx.save()
                
                    log_message(f"Making Feature Layer for {feature_dataset_path}", 'info')
                    temp_layer = arcpy.MakeFeatureLayer_management(feature_dataset_path, feature_name)
                    
                    log_message(f"Adding feature dataset {feature_dataset_path} to temporary project", 'info')
                    temp_map.addLayer(temp_layer.getOutput(0))
                    aprx.save()
                else:
                    log_message(f"Using existing map for {feature_name}", 'info')
                    temp_map = maps[0]

                # Strip any basemap layers. createMap() (and a template map) can carry a default basemap
                # (e.g. "Topographic") whose tiled/online data source FAILS staging for a referenced service
                # (Analyzer ERROR 24078 "Layer's data source is not supported"). The published referenced
                # service only needs the operational feature layer, so remove basemaps before staging.
                removed_basemaps = []
                for _lyr in temp_map.listLayers():
                    try:
                        if getattr(_lyr, "isBasemapLayer", False):
                            temp_map.removeLayer(_lyr)
                            removed_basemaps.append(_lyr.name)
                    except Exception as _bm_e:
                        log_message(f"\t(could not inspect/remove a layer for basemap check: {_bm_e})", 'info')
                if removed_basemaps:
                    log_message(f"Removed basemap layer(s) before publishing: {removed_basemaps}", 'info')
                    aprx.save()

                map_cim = temp_map.getDefinition('V3')
                if not map_cim.useServiceLayerIDs:
                    log_message(f"Allowing assignment of unique numeric IDs", 'info')
                    map_cim.useServiceLayerIDs = True
                    temp_map.setDefinition(map_cim)
                    aprx.save()
                
                # A REFERENCED feature service on a federated server is published as a MAP_IMAGE service
                # BY REFERENCE (copyDataToServer=False) with Feature Access enabled -- this yields the
                # MapServer + FeatureServer pair (plan decision #9). NOTE: service_type="FEATURE" is NOT
                # valid with server_type="FEDERATED_SERVER" (arcpy validation_map allows FEATURE only on
                # HOSTING_SERVER/MY_HOSTED_SERVICES), so MAP_IMAGE is the correct type here. Feature Access
                # is switched on in finalize_sddraft() after export. By-reference works because RRGOrg is a
                # registered data store -- no offline workaround / connection-string DOM injection needed.
                log_message(f"Creating FEDERATED_SERVER MAP_IMAGE sharing draft (referenced) for {service_name}", 'info')
                sddraft = temp_map.getWebLayerSharingDraft(server_type="FEDERATED_SERVER",
                                                           service_type="MAP_IMAGE",
                                                           service_name=service_name)
                log_message(f"Setting sharing draft properties for {service_name}", 'info')
                sddraft.federatedServerUrl = federated_server_url
                sddraft.copyDataToServer = False     # by reference -- data stays in the registered RRGOrg SDE
                # sddraft.allowExporting = True
                # sddraft.checkUniqueIDAssignment = False
                # sddraft.offline = True
                # sddraft.offlineTarget = 'ENTERPRISE_11'
                # Overwrite only when --OverrideExisting was requested (the existing-service guard above has
                # already decided this item should overwrite). Otherwise stage a non-overwriting SD as before.
                sddraft.overwriteExistingService = override_existing
                sddraft.summary = summary
                sddraft.tags = tags
                sddraft.description = description
                try:
                    sddraft.credits = credits
                except Exception:
                    pass
                if arcgisServerFolderName:
                    sddraft.serverFolder = arcgisServerFolderName   # REST folder (e.g. MaxEnt)
                if arcgisPortalFolderName:
                    sddraft.portalFolder = arcgisPortalFolderName   # blank -> portal ROOT (folder set at Phase 8 reassign)

                log_message(f"Exporting sddraft for {feature_name}", 'info')
                sddraft.exportToSDDraft(sddraft_output_filepath)
                
                '''
                # Create an Image Service Draft
                sddraft_result = arcpy.CreateImageSDDraft(raster_or_mosaic_layer=raster_dataset_path, 
                                                    out_sddraft=sddraft_output_filepath, 
                                                    service_name=raster_name, 
                                                    server_type="ARCGIS_SERVER",
                                                    connection_file_path=None,
                                                    copy_data_to_server=False, 
                                                    summary=summary, 
                                                    tags=tags)
                '''
        except Exception as e:
            errors = {f"Failed to create Service Draft for {feature_name}": str(e)}
            log_message(f"Failed to create Service Draft: {e}", 'error')
        
        total_warnings = 0
        build_pyramids = False
        calculate_statistics = False
        
        if (sddraft_result and sddraft_result != {}) or errors != {}:
            log_message('CreateSDDraft Errors, Warnings, and Messages', 'info')
            
            if errors != {}:
                # append errors from sddraft_result to errors
                errors.update(sddraft_result.get('errors', {}))
            else:
                errors = sddraft_result.get('errors', {})
            messages = sddraft_result.get('messages', {})
            warnings = sddraft_result.get('warnings', {})
            
            if messages != {}:
                log_message("Messages:", 'info', messages)
                
            if warnings == {}:
                total_warnings = 0
            else:
                log_message("WARNINGS:", 'info', warnings)
                total_warnings = len(warnings)
                if any(code == 10029 for (message, code), details in warnings.items()):
                    build_pyramids = True
                    # log_message("+++++++++++++++ Build Pyramids", 'info')
                if any(code == 10010 for (message, code), details in warnings.items()):
                    calculate_statistics = True
                    # log_message("+++++++++++++++ Calculate Statistics", 'info')
            
            if errors != {}:
                log_message("ERRORS:", 'error', errors)
                continue
        else:
            log_message(f"Created Service Draft for {feature_name}")
        '''
        if build_pyramids:
            log_message('Building pyramids', 'info')
            try:
                # Build pyramids with specific parameters
                arcpy.management.BuildPyramids(in_raster_dataset=raster_dataset_path,
                                                pyramid_level="-1",
                                                SKIP_FIRST="NONE",
                                                resample_technique="BILINEAR",
                                                compression_type="DEFAULT",
                                                compression_quality=75,
                                                skip_existing="SKIP_EXISTING")
                log_message(f"Pyramids built for {raster_name}", message_details=arcpy.GetMessages())
                total_warnings = total_warnings - 1
            except arcpy.ExecuteError:
                log_message(arcpy.GetMessages(2), 'error')
            except Exception as e:
                log_message(f"Failed to build pyramids: {e}", 'error')
            
        if calculate_statistics:
            log_message('Calculating Statistics', 'info')
            try:
                arcpy.management.CalculateStatistics(raster_dataset_path)
                log_message(f"Statistics Calculated for {raster_name}", message_details=arcpy.GetMessages())
                total_warnings = total_warnings - 1
            except arcpy.ExecuteError:
                log_message(arcpy.GetMessages(2), 'error')
            except Exception as e:
                log_message(f"Failed to Calculate Statistics: {e}", 'error')
        '''
    
    if os.path.exists(sddraft_output_filepath):
        # if not update_sddraft_dom(sddraft_output_filepath, feature_name, title, description, credits, is_shared_instance=feature_is_shared_instance, repository_id=repository_id):
        # Enable Feature Access + set the instance provider; do NOT rewrite the by-reference/Databases
        # blocks (arcpy already produced a correct referenced SD via copyDataToServer=False).
        if not finalize_sddraft(sddraft_output_filepath, is_shared_instance=feature_is_shared_instance):
            continue
    else:
        errors = {f"Failed to create Service Draft for {feature_name}": "No sddraft file found"}
        log_message(f"Failed to create Service Draft for {feature_name}", 'error')
        continue
    
    if stageService:
        if (errors == {}) and (total_warnings == 0):
            # Make sure the target Portal content folder exists (create it under the publishing user if
            # missing) so PortalFolderName resolves and the item is not stranded in root.
            ensure_portal_folder(arcgisPortalFolderName)
            if backup_sddraft_files:
                # backup sddraft_output_filepath
                backup_sddraft_output_filepath = sddraft_output_filepath.replace('.sddraft', '_backup_2.sddraft')
                try:
                    shutil.copyfile(sddraft_output_filepath, backup_sddraft_output_filepath)
                    log_message(f"Backup saved to {backup_sddraft_output_filepath}")
                except Exception as e:
                    log_message(f"Failed to backup {sddraft_output_filepath} to {backup_sddraft_output_filepath}: {e}", 'info')
            
            uploaded = False
            # Stage and upload the service
            service_staged = stage_service(sddraft_output_filepath, sd_output_filepath)
            if service_staged:
                if uploadToServer:
                    # Resolve the federated server URL the PORTAL uses to ADMINISTER the server. The
                    # configured web-adaptor URL (federated_server_url) usually has administrative access
                    # disabled, so arcpy's "check if service exists" fails with ERROR 002901 -- even though
                    # the folder-creation step above reached the server admin fine via the portal federation.
                    # gis.admin.servers.list()[0].url is that admin-capable URL (= Portal > Settings > Servers).
                    upload_server = federated_server_url
                    try:
                        _fed = gis.admin.servers.list() if gis is not None else []
                        _fed_url = (getattr(_fed[0], 'url', '') if _fed else '') or ''
                        if _fed_url:
                            upload_server = _fed_url
                            # remove /admin from end of upload_server if it exists
                            if upload_server.endswith('/admin'):
                                upload_server = upload_server[:-6]
                            log_message(f"Federated server URL (from portal federation): {upload_server}", 'info')
                        else:
                            log_message(f"Could not read federated server URL from portal; using configured '{federated_server_url}'.", 'info')
                    except Exception as e:
                        log_message(f"Could not resolve federated server URL from portal (using '{federated_server_url}'): {e}", 'info')
                    log_message(f"Start Publishing Service from '{sd_output_filepath}' to '{upload_server}'", 'info')
                    log_message(f"\tarcpy.UploadServiceDefinition_server(", 'info')
                    log_message(f"\t\tin_sd_file='{sd_output_filepath}',", 'info')
                    log_message(f"\t\tin_server='{upload_server}',", 'info')
                    log_message(f"\t\tin_service_name='{service_name}',", 'info')
                    log_message(f"\t\tin_cluster='',", 'info')
                    log_message(f"\t\tin_startupType='STARTED',", 'info')
                    log_message(f"\t\tin_override='OVERRIDE_DEFINITION',", 'info')
                    log_message(f"\t\tin_my_contents='SHARE_ONLINE',", 'info')
                    log_message(f"\t\tin_public='PRIVATE',", 'info')
                    log_message(f"\t\tin_organization='NO_SHARE_ORGANIZATION',", 'info')
                    log_message(f"\t\tin_groups=None", 'info')

                    if arcgisServerFolderName.strip() != '':
                        log_message(f"\t\tin_folder_type='EXISTING',", 'info')
                        log_message(f"\t\tin_folder='{arcgisServerFolderName}'", 'info')
                        # if arcgisServerFolderName is not empty, try again with in_folder_type="EXISTING" and in_folder=arcgisServerFolderName
                        try:
                            log_message(f"Upload with in_folder_type='EXISTING' and in_folder='{arcgisServerFolderName}'", 'info')
                            # arcpy.UploadServiceDefinition_server(in_sd_file=sd_output_filepath,
                            arcpy.server.UploadServiceDefinition(in_sd_file=sd_output_filepath,
                                                                    in_server=upload_server,
                                                                    in_service_name=service_name,
                                                                    in_folder_type="EXISTING",
                                                                    in_folder=arcgisServerFolderName,
                                                                    in_startupType="STARTED",
                                                                    in_override="OVERRIDE_DEFINITION",
                                                                    in_my_contents="SHARE_ONLINE",
                                                                    in_public="PRIVATE",
                                                                    in_organization="NO_SHARE_ORGANIZATION")
                            log_message(f"Finished Publishing Service for {service_name}", 'info')
                            uploaded = True
                        except Exception as e:
                            log_message(f"Failed to upload service with in_folder_type='EXISTING': {e}", 'info')
                            # log traceback
                            log_message(traceback.format_exc(), 'info')
                    
                    if (not uploaded):
                        try:
                            log_message(f"Retry upload with in_folder_type='FROM_SERVICE_DEFINITION'", 'info')
                            # arcpy.UploadServiceDefinition_server(in_sd_file=sd_output_filepath,
                            arcpy.server.UploadServiceDefinition(in_sd_file=sd_output_filepath,
                                                                in_server=upload_server,
                                                                in_service_name=service_name,
                                                                in_folder_type="FROM_SERVICE_DEFINITION",
                                                                in_startupType="STARTED",
                                                                in_override="OVERRIDE_DEFINITION",
                                                                in_my_contents="SHARE_ONLINE",
                                                                in_public="PRIVATE",
                                                                in_organization="NO_SHARE_ORGANIZATION")
                            # in_cluster="", in_folder="", in_groups=None
                            log_message(f"Finished Publishing Service for {service_name}")
                            uploaded = True
                        except Exception as e:
                            # The 'error' log below is auto-recorded against this item's ledger row by
                            # log_message -> _record_error_to_ledger (no explicit record_error needed here).
                            log_message(f"Failed to upload service with in_folder_type='FROM_SERVICE_DEFINITION': {e}", 'error')
                            # log traceback
                            log_message(traceback.format_exc(), 'error')

                    
                    if uploaded == True:
                        # Resolve the source AGOL item id first (ledger join) so the title/description
                        # sync can pull the original description; then update both portal items.
                        src_item_id, ent_item_id = record_published_to_ledger(feature_name, service_name)
                        validate_and_update_portal_item(service_name, title, portal_groups, categories,
                                                         src_item_id=src_item_id)
                        # Post-publish (Step 6): apply the source AGOL item's renderer + pop-ups +
                        # visibility range + default view to the new Enterprise item, and sync its Map
                        # Image Layer. Best-effort -- a symbology failure must NOT fail the publish.
                        # Requires Step 1 to have captured the source renderer; the source item id comes
                        # from the ledger join above (dest_feature_class == feature_name).
                        if apply_symbology and src_item_id and ent_item_id:
                            try:
                                log_message(f"Applying symbology/pop-ups to Enterprise item {ent_item_id} "
                                            f"from source AGOL item {src_item_id}", 'info')
                                # regen_thumbnail=False: the Enterprise thumbnail is set later by the
                                # thumb_copy_portal pipeline stage (copy from the AGOL original, fallback
                                # render), so the publish does NOT render it here.
                                applied = apply_symbology(gis, ent_item_id, src_item_id,
                                                          target_portal_url=portal_url,
                                                          enterprise_portal_url=portal_url,
                                                          regen_thumbnail=False)
                                log_message(f"Symbology apply for {feature_name}: "
                                            f"{'OK' if applied else 'skipped/failed -- see Step 6 log'}", 'info')
                            except Exception as e:
                                log_message(f"Symbology apply failed for {feature_name} "
                                            f"(publish unaffected): {e}", 'error')
                        elif apply_symbology:
                            log_message(f"Symbology apply skipped for {feature_name}: no source/enterprise "
                                        f"item id resolved from the ledger. Run Step 6 manually with the "
                                        f"published item id.", 'info')
                        else:
                            log_message("Symbology apply skipped: migration_poc_step6_apply_symbology "
                                        "not importable.", 'info')
                        if remove_sddraft_files:
                            file_removed = remove_file(sddraft_output_filepath)
                            file_removed = remove_file(os.path.join(sd_output_dir, f"{feature_name}.aprx"))
                            
                        if remove_sd_files:
                            file_removed = remove_file(sd_output_filepath)
                else:
                    log_message(f"Service Definition file created: {sd_output_filepath}")
    else:
        log_message(f"Service Definition file created: {sd_output_filepath}")

# log_message('portal_groups:', 'info', message_details=portal_group_dict)

log_message(f'Script completed. See log file for details: {general_log_file_path}')
if error_count > 0:
    log_message(f"Errors occurred. Please see error log file for details: {error_log_file_path}", 'error')
else:
    # close error_logger
    for handler in error_logger.handlers[:]:
        handler.close()
    error_logger.removeHandler(handler)
    # if error_log_file_path exists, delete it
    if os.path.exists(error_log_file_path):
        os.remove(error_log_file_path)
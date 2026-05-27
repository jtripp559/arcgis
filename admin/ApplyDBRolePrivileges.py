# ApplyDBRolePrivileges.py
#
# Created By:   Julie Tripp
#
#               12/04/2025
#
# Description:
#   This script applies standard user role privileges to all datasets, feature classes, tables, and rasters
#   in all enterprise geodatabases found in a specified directory containing .sde connection files.
#

# Initialize parameters:
# SDE files/directory configuration
SDE_DIRECTORY = r"D:\GenericArcGISConnectionsDir"
SDE_FILE_MASK = "*_sde*.sde"
SDE_FILE_MASK_EXCLUDE = "*old*.sde"
SPECIFIC_SDE_FILES = []  # e.g., [r"C:\path\to\connection1.sde", r"C:\path\to\connection2.sde"]

# User role privileges
# Format: {role_name: (view_permission, edit_permission)}
ROLE_PRIVILEGES = {
    'data creator': ('GRANT', 'GRANT'),
    'data editor': ('GRANT', 'GRANT'),
    'data viewer': ('GRANT', 'AS_IS')
}

import arcpy
import os
import glob
import fnmatch
import logging
from datetime import datetime

# global variables
timestamp = datetime.now()
timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
month_str = timestamp.strftime("%Y%m")
script_dir = os.path.dirname(os.path.realpath(__file__))
output_dir = os.path.join(script_dir, "Output")
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
output_file_base = os.path.join(output_dir, f"ApplyDBRolePrivileges_")

# Set up logging to file, console, and error file
log_file = f"{output_file_base}{month_str}.log"
log_err_file = f"{output_file_base}{timestamp_str}.err.log"
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_format)
error_file_handler = logging.FileHandler(log_err_file)
error_file_handler.setLevel(logging.ERROR)
error_file_handler.setFormatter(log_format)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)
logger.addHandler(file_handler)
logger.addHandler(error_file_handler)
logger.addHandler(console_handler)


def find_sde_files(directory):
    """
    Find .sde connection files based on configuration.
    1. If SPECIFIC_SDE_FILES is populated, use only those files
    2. Otherwise, search directory using SDE_FILE_MASK (include) and SDE_FILE_MASK_EXCLUDE (exclude)
    Pattern matching is case-insensitive.
    """
    logging.debug(f"Searching for SDE files")
    sde_files = []
    
    # Use specific files if provided
    if SPECIFIC_SDE_FILES:
        logging.info(f"Using {len(SPECIFIC_SDE_FILES)} specific SDE files from SPECIFIC_SDE_FILES")
        for sde_file in SPECIFIC_SDE_FILES:
            if os.path.exists(sde_file):
                sde_files.append(sde_file)
                logging.debug(f"Found specific SDE file: {sde_file}")
            else:
                logging.warning(f"Specific SDE file not found: {sde_file}")
        logging.info(f"Total specific SDE files found: {len(sde_files)}")
        return sde_files
    
    # Search directory with masks
    if not os.path.exists(directory):
        logging.error(f"Directory does not exist: {directory}")
        return sde_files
    
    # Get all .sde files first (case-insensitive), then apply masks
    all_sde_pattern = os.path.join(directory, "*.[sS][dD][eE]")
    all_sde_files = glob.glob(all_sde_pattern)
    logging.debug(f"Total .sde files in directory: {len(all_sde_files)}")
    
    if SDE_FILE_MASK is None:
        matched_files = all_sde_files
        logging.debug(f"No include mask specified, using all .sde files")
    else:
        # Apply include mask (case-insensitive using fnmatch)
        logging.debug(f"Include mask: {SDE_FILE_MASK}")
        matched_files = [f for f in all_sde_files if fnmatch.fnmatch(os.path.basename(f).lower(), SDE_FILE_MASK.lower())]
        logging.debug(f"Files matching include mask: {len(matched_files)}")
    
    # Apply exclude mask if specified (case-insensitive)
    if SDE_FILE_MASK_EXCLUDE:
        logging.debug(f"Exclude mask: {SDE_FILE_MASK_EXCLUDE}")
        exclude_mask_lower = SDE_FILE_MASK_EXCLUDE.lower()
        
        for file_path in matched_files:
            filename_lower = os.path.basename(file_path).lower()
            if not fnmatch.fnmatch(filename_lower, exclude_mask_lower):
                sde_files.append(file_path)
                logging.debug(f"Found SDE file: {os.path.basename(file_path)}")
            else:
                logging.debug(f"Excluded SDE file: {os.path.basename(file_path)}")
    else:
        sde_files = matched_files
        for file_path in sde_files:
            logging.debug(f"Found SDE file: {os.path.basename(file_path)}")
    
    logging.info(f"Total SDE files found: {len(sde_files)}")
    return sde_files


def get_all_datasets(workspace):
    """
    Get all datasets, feature classes, tables, and rasters from a geodatabase.
    Uses arcpy.da.Walk() with no datatype filter for a single pass through the geodatabase.
    Returns list of dataset names as returned by arcpy (schema.name format for enterprise GDBs).
    """
    logging.debug(f"Getting all datasets from workspace: {workspace}")
    datasets = []
    try:
        for dirpath, dirnames, filenames in arcpy.da.Walk(workspace):
            if dirpath == workspace:
                datasets.extend(dirnames)
            datasets.extend(filenames)
        logging.info(f"Total datasets found in {os.path.basename(workspace)}: {len(datasets)}")
    except Exception as e:
        logging.error(f"Error getting datasets from {workspace}: {e}")
    
    return datasets


def get_missing_permissions(sde_file):
    """
    Query the database once to find ALL tables/roles missing required permissions.
    Returns a list of tuples: (schema_name, table_name, role_name, view_permission, edit_permission)
    
    This is much more efficient than checking one dataset at a time.
    Uses arcpy.ArcSDESQLExecute to run a bulk SQL query against sys.database_permissions.
    """
    logging.debug(f"Running bulk query for missing permissions in: {sde_file}")
    missing_permissions = []
    
    try:
        sde_conn = arcpy.ArcSDESQLExecute(sde_file)
        
        # Build the role list for the SQL query from ROLE_PRIVILEGES
        role_names = "', '".join(ROLE_PRIVILEGES.keys())
        
        # SQL query to find all tables missing permissions for each role
        # This mirrors the logic from GrantDBPermissions.sql stored procedure
        # For each role, we check if SELECT permission exists (for view)
        # and if UPDATE/INSERT exists (for edit, where applicable)
        sql = f"""
        WITH RolePermissions AS (
            SELECT 
                s.name AS schema_name,
                o.name AS table_name,
                dp.name AS role_name,
                dp.principal_id,
                o.object_id
            FROM sys.objects o
            INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
            CROSS JOIN (
                SELECT name, principal_id 
                FROM sys.database_principals 
                WHERE name IN ('{role_names}')
            ) dp
            WHERE o.type = 'U'
              AND o.name NOT LIKE 'SDE_%'
              AND o.name NOT LIKE 'i_%'
              AND o.name NOT LIKE 'a_%'
              AND o.name NOT LIKE 'D_%'
              AND o.name NOT LIKE 'GDB_%'
              AND o.name NOT LIKE 'sys%'
        ),
        CurrentPermissions AS (
            SELECT 
                rp.schema_name,
                rp.table_name,
                rp.role_name,
                MAX(CASE WHEN p.permission_name = 'SELECT' THEN 1 ELSE 0 END) AS has_select,
                MAX(CASE WHEN p.permission_name IN ('UPDATE', 'INSERT', 'DELETE') THEN 1 ELSE 0 END) AS has_edit
            FROM RolePermissions rp
            LEFT JOIN sys.database_permissions p 
                ON p.major_id = rp.object_id
                AND p.grantee_principal_id = rp.principal_id
                AND p.permission_name IN ('SELECT', 'UPDATE', 'INSERT', 'DELETE')
            GROUP BY rp.schema_name, rp.table_name, rp.role_name
        )
        SELECT 
            schema_name,
            table_name,
            role_name,
            has_select,
            has_edit
        FROM CurrentPermissions
        WHERE has_select = 0  
           OR (role_name IN ('data creator', 'data editor') AND has_edit = 0)  
        ORDER BY table_name, role_name;
        """
        
        logging.debug(f"Executing bulk permissions query...")
        result = sde_conn.execute(sql)
        if result and result is not True:
            # Result can be a single row or list of rows
            if isinstance(result, list):
                rows = result
            else:
                rows = [result]
            
            for row in rows:
                if isinstance(row, (list, tuple)) and len(row) >= 5:
                    schema_name = row[0]
                    table_name = row[1]
                    role_name = row[2]
                    has_select = row[3]
                    has_edit = row[4]
                    
                    # Get the desired permissions for this role
                    if role_name in ROLE_PRIVILEGES:
                        view_perm, edit_perm = ROLE_PRIVILEGES[role_name]
                        
                        # Only add if actually missing required permissions
                        needs_view = (view_perm == 'GRANT' and has_select == 0)
                        needs_edit = (edit_perm == 'GRANT' and has_edit == 0)
                        
                        if needs_view or needs_edit:
                            missing_permissions.append((schema_name, table_name, role_name, view_perm, edit_perm))
                            logging.debug(f"  Missing: {schema_name}.{table_name} -> {role_name} (needs_view={needs_view}, needs_edit={needs_edit})")
        
        logging.info(f"Bulk query found {len(missing_permissions)} table/role combinations needing permission updates")
        
    except Exception as e:
        logging.error(f"Error running bulk permissions query for {sde_conn}: {e}", exc_info=True)
    
    return missing_permissions


def apply_privileges(dataset_path, user, view_permission, edit_permission):
    """
    Apply privileges to a dataset for a specific user/role.
    
    Args:
        dataset_path: Full path to the dataset
        user: User or role name
        view_permission: 'GRANT', 'REVOKE', or 'AS_IS'
        edit_permission: 'GRANT', 'REVOKE', or 'AS_IS'
    
    Returns:
        tuple: (success: bool, message: str)
    """
    logging.debug(f"apply_privileges called: dataset={dataset_path}, user={user}, view={view_permission}, edit={edit_permission}")
    try:
        # Apply the privileges
        logging.debug(f"  Calling arcpy.management.ChangePrivileges...")
        arcpy.management.ChangePrivileges(
            in_dataset=dataset_path,
            user=user,
            View=view_permission,
            Edit=edit_permission
        )
        logging.debug(f"  ChangePrivileges completed successfully")
        return (True, "Success")
        
    except arcpy.ExecuteError as e:
        error_msg = f"ArcPy Error: {arcpy.GetMessages(2)}"
        logging.error(f"  ArcPy ExecuteError in apply_privileges: {error_msg}")
        return (False, error_msg)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logging.error(f"  Exception in apply_privileges: {error_msg}")
        return (False, error_msg)


def process_geodatabase(sde_file):
    """
    Process a single geodatabase using bulk query approach.
    1. Run ONE SQL query to find all tables/roles missing permissions
    2. Only call ChangePrivileges for those specific combinations
    """
    gdb_name = os.path.basename(sde_file)
    logging.info(f"Processing sde file: {gdb_name}")
    logging.debug(f"Full path: {sde_file}")
    
    try:
        # Set workspace
        logging.debug(f"Setting arcpy.env.workspace to: {sde_file}")
        arcpy.env.workspace = sde_file
        
        # Get all datasets (for counting/reporting purposes)
        logging.debug(f"Retrieving all datasets from geodatabase...")
        datasets = get_all_datasets(sde_file)
        if not datasets:
            logging.warning(f"No datasets found in {gdb_name}")
            return 0, 0, 0
        
        total_datasets = len(datasets)
        total_possible = total_datasets * len(ROLE_PRIVILEGES)
        logging.info(f"Found {total_datasets} datasets in {gdb_name} ({total_possible} total dataset/role combinations)")
        
        # Build a set of valid dataset names for quick lookup (normalize to lowercase for comparison)
        # Include both the full name and just the table portion for matching
        valid_datasets = set()
        for ds in datasets:
            # Add the full dataset name (as returned by arcpy)
            valid_datasets.add(ds.lower())
            # Also add just the table name portion (after the last dot or backslash)
            base_name = os.path.basename(ds).split('.')[-1].lower()
            valid_datasets.add(base_name)
        logging.debug(f"Valid dataset names for matching: {len(valid_datasets)} entries")
        
        # Use bulk query to find only the tables/roles that need permission updates
        missing_permissions = get_missing_permissions(sde_file)
        if not missing_permissions:
            logging.info(f"All permissions are already correct in {gdb_name} - nothing to update")
            return 0, 0, total_possible
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        not_found_count = 0
        logging.info(f"Found {len(missing_permissions)} dataset/role combinations needing updates from SQL query")
        
        # Process only the missing permissions
        for idx, (schema_name, table_name, role_name, view_perm, edit_perm) in enumerate(missing_permissions, 1):
            # Build the full dataset path using schema.table format
            dataset_name = f"{schema_name}.{table_name}"
            dataset_path = os.path.join(sde_file, dataset_name)
            
            # Validate that this dataset exists in ArcGIS's view of the geodatabase
            # Check both the full schema.table name and just the table name
            if dataset_name.lower() not in valid_datasets and table_name.lower() not in valid_datasets:
                logging.debug(f"Skipping {dataset_name} -> {role_name}: not found in ArcGIS dataset list (may be a system table or orphaned object)")
                not_found_count += 1
                continue
            
            logging.debug(f"Processing {idx}/{len(missing_permissions)}: {dataset_name} -> {role_name}")
            
            success, message = apply_privileges(dataset_path, role_name, view_perm, edit_perm)
            
            if success:
                success_count += 1
                status = "Success"
            else:
                error_count += 1
                status = f"Error: {message}"
                logging.error(f"Failed to update {dataset_name} for {role_name}: {message}")
            
            logging.debug(f"{gdb_name}, {dataset_name}, Role: {role_name}, View: {view_perm}, Edit: {edit_perm}, Status: {status}")
        
        # Calculate skipped as: total possible - (success + error + not_found)
        skipped_count = total_possible - success_count - error_count - not_found_count
        
        logging.info(f"Geodatabase {gdb_name} summary: Success={success_count}, Errors={error_count}, Skipped (already correct)={skipped_count}, Not in ArcGIS={not_found_count}")
        return success_count, error_count, skipped_count
        
    except Exception as e:
        logging.error(f"Error processing {gdb_name}: {e}")
        return 0, 1, 0


def main():
    """Main function to run the privilege update process."""
    logging.info("=" * 80)
    logging.info("Starting ApplyDBRolePrivileges")
    logging.debug(f"Script directory: {script_dir}")
    logging.debug(f"Output directory: {output_dir}")
    logging.debug(f"Log file: {log_file}")
    logging.debug(f"Error log file: {log_err_file}")
    logging.debug(f"SDE directory: {SDE_DIRECTORY}")
    
    # Display role privileges
    logging.info("Standard Role Privileges to Apply:")
    for role, (view, edit) in ROLE_PRIVILEGES.items():
        logging.info(f"  {role}: VIEW={view}, EDIT={edit}")
    
    # Find all .sde files
    sde_files = find_sde_files(SDE_DIRECTORY)
    if not sde_files:
        logging.warning(f"No SDE files found")
        return
    
    total_success = 0
    total_errors = 0
    total_skipped = 0
    
    # Process each connection file
    for idx, sde_file in enumerate(sde_files, 1):
        logging.info(f"Processing file {idx} of {len(sde_files)}: {os.path.basename(sde_file)}")
        success, errors, skipped = process_geodatabase(sde_file)
        logging.debug(f"Results for {os.path.basename(sde_file)}: success={success}, errors={errors}, skipped={skipped}")
        total_success += success
        total_errors += errors
        total_skipped += skipped
    
    # Summary
    logging.info(f"Processing Complete: Success={total_success}, Errors={total_errors}, Skipped={total_skipped}")
    
    # Shutdown logging
    logging.info("Shutting down logging...")
    logging.shutdown()
    
    try:
        # Delete error log file if it's empty (no errors were logged)
        if os.path.exists(log_err_file) and os.path.getsize(log_err_file) == 0:
            os.remove(log_err_file)
            print(f"Removed empty error log file: {log_err_file}")
    except Exception as e:
        print(f"Error removing empty error log file: {e}")
        
if __name__ == "__main__":
    main()

"""
Name: upgrade_gdb.py
Description: Provide connection information to an Enterprise geodatabase
and upgrade the geodatabase
Type upgrade_gdb.py -h or upgrade_gdb.py --help for usage
"""

# Import system modules
import arcpy
import sys
import traceback
from datetime import datetime

prereq_test_only = True
backup_db = False
disconnect_users = True
Connection_File_Name_full_path = r"C:\Admin\Tools\Connections\ENT_DB3_dbadmin.sde"


backup_full_path = r"D:\GenericArcGISDataDir\Systems\Backups\ENT_DB3_backup_" + datetime.now().strftime("%Y%m%d") + ".xml"

def disconnect_users(connection_file):
    current_users = arcpy.ListUsers(connection_file)
    if len(current_users) == 0:
        print("No users connected to the geodatabase. Continuing...")
        return
    for user in current_users:
        connection_duration = datetime.now() - user.ConnectionTime
        print(f"User: {user.Name}, Connected at: {user.ConnectionTime}, ID: {user.ID}, Client: {user.ClientName}, Duration: {connection_duration}")
    try:
        print("Disconnecting all users...")
        arcpy.DisconnectUser(connection_file, "ALL")
        print("All users disconnected.")
    except Exception as e:
        print("Failed to disconnect users:")
        print(str(e))
        traceback.print_exc()
        sys.exit("Upgrade did not run.")

# Check if value entered for option
try:
    # Get the current product license
    product_license=arcpy.ProductInfo()
    
    # Checks required license level to upgrade
    if product_license.upper() == "ARCVIEW" or product_license.upper() == 'ENGINE':
        print("\n" + product_license + " license found!" + "  Enterprise geodatabase upgrade requires an ArcGIS Desktop Standard or Advanced, ArcGIS Engine with the Geodatabase Update extension, or ArcGIS Server license.")
        sys.exit("Re-authorize ArcGIS before upgrading.")
    else:
        print("\n" + product_license + " license available!  Continuing to upgrade...")
        arcpy.AddMessage("+++++++++")
    
    # Check whether geodatabase needs upgrade
    isCurrent = arcpy.Describe(Connection_File_Name_full_path).currentRelease
    if isCurrent == True:
        print("The geodatabase is already at the current release and cannot be upgraded!")
        sys.exit("Upgrade did not run.")
    else:
        print("The geodatabase is not at the current release and can be upgraded!")
        print("Geodatabase version: " + arcpy.Describe(Connection_File_Name_full_path).release)
        arcpy.AddMessage("+++++++++")
    
    if backup_db:
        print("Backing up geodatabase...\n")
        arcpy.management.ExportXMLWorkspaceDocument(
			in_data=Connection_File_Name_full_path,
			out_file=backup_full_path,
			export_type="DATA",
			storage_type="BINARY",
			export_metadata="METADATA"
		)
        print(f"Backup of geodatabase complete! Backup file: {backup_full_path}")
    
    if disconnect_users:
        disconnect_users(Connection_File_Name_full_path)
        
    # Process: Upgrade geodatabase...
    if prereq_test_only:
        print("Running Pre-Requisite Check...\n")
        arcpy.UpgradeGDB_management(input_workspace=Connection_File_Name_full_path, input_prerequisite_check="PREREQUISITE_CHECK", input_upgradegdb_check="NO_UPGRADE")
        for i in range(arcpy.GetMessageCount()):
            print(arcpy.GetMessage(i))
            arcpy.AddReturnMessage(i)
        arcpy.AddMessage("+++++++++\n")
    else:
        print("Upgrading Geodatabase...\n")
        arcpy.UpgradeGDB_management(input_workspace=Connection_File_Name_full_path, input_prerequisite_check="PREREQUISITE_CHECK", input_upgradegdb_check="UPGRADE")
        for i in range(arcpy.GetMessageCount()):
            print(arcpy.GetMessage(i))
            arcpy.AddReturnMessage(i)
        arcpy.AddMessage("+++++++++\n")
except arcpy.ExecuteError:
    print(arcpy.GetMessages(2))
    traceback.print_exc()
    sys.exit("Upgrade did not run.")
except Exception as e:
    print(str(e))
    traceback.print_exc()
    sys.exit("Upgrade did not run.")

print("Completed successfully!")
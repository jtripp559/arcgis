'''
Name: CreateSDEFilesBulk.py
Developed by: Julie Tripp
Date: 06/02/2026

Summary:
    Bulk version of CreateSDEFiles.py. Creates Microsoft SQL Server enterprise
    geodatabase connection (.sde) files for several users in one run -- the
    geodatabase administrator (sde) plus each schema/data-owner user -- using
    arcpy.CreateDatabaseConnection_management.

    The connecting user's default schema determines where the data it creates is
    stored and who owns it, so there is one connection file per schema owner:
        RRGOrg_sde.sde   -> geodatabase administrator (system tables; not for data)
        RRGOrg_clim.sde  -> owns/creates RRGOrg.clim.*
        RRGOrg_crop.sde  -> owns/creates RRGOrg.crop.*
        RRGOrg_land.sde  -> owns/creates RRGOrg.land.*
        RRGOrg_ws.sde    -> owns/creates RRGOrg.ws.*

Usage:
    Run the script and follow the prompts. Shared values (output folder, server,
    database) are asked once; each user's password is asked in turn.

    Run order: create the schema-owner users FIRST with CreateGDBUsers.py, then
    run this script -- otherwise a user's connection test fails until it exists
    (the .sde file is still written either way).
'''
import arcpy
import os
import getpass

# Users to create connection files for. 'sde' is the geodatabase administrator;
# the rest are the schema/data owners (schema name == user name in SQL Server).
connection_users = ["sde", "clim", "crop", "land", "ws"]

# Default output location and connection settings (match CreateSDEFiles.py).
script_dir = r"T:\ArcGISDataset\Enterprise\Creators\Connections"
database_platform = "SQL_SERVER"
account_authentication = "DATABASE_AUTH"
save_user_pass = "SAVE_USERNAME"

# Prompt once for the shared values
output_dir = input(f"Enter the directory to output the sde files to (Default: {script_dir}): ")
if output_dir == '' or output_dir is None:
    output_dir = script_dir
server = input("Enter the server name (Default: NBS-APP1): ")
if server == '' or server is None:
    server = "NBS-APP1"
database = input("Enter the database name (Default: RRGOrg): ")
if database == '' or database is None:
    database = "RRGOrg"
instance = f"{server}\\frutsql01"

print(f"\nCreating connection files in: {output_dir}")
print(f"Instance: {instance}   Database: {database}")

# Create a connection file for each user
created_count = 0
for username in connection_users:
    print(f"\nUser '{username}':")
    password = getpass.getpass(f"  Enter the {username} password: ")
    sde_filename = database + "_" + username + ".sde"
    sde_file_path = output_dir + "\\" + sde_filename
    print(f"  File will be saved as: {sde_filename}")
    # Execute CreateDatabaseConnection
    failure = True
    try:
        arcpy.CreateDatabaseConnection_management(output_dir, sde_filename, database_platform, instance,
                                              account_authentication, username, password,
                                              save_user_pass, database)
        failure = False
        created_count += 1
        print("  Created sde file successfully.")
    except arcpy.ExecuteError:
        print("  Connection failed")
        print(arcpy.GetMessages(2))
    except Exception as e:
        print("  An unexpected error occurred")
        print(str(e))
    if not failure:
        # test the sde file
        print("  Testing the sde file...")
        try:
            sde_conn = arcpy.ArcSDESQLExecute(sde_file_path)
            print("  Connection successful.")
        except arcpy.ExecuteError:
            print("  Connection test failed (does the user exist yet?)")
            print(arcpy.GetMessages(2))
        except Exception as e:
            print("  An unexpected error occurred during the connection test")
            print(str(e))

print(f"\nCreated {created_count} of {len(connection_users)} sde files in '{output_dir}'.")
print("Script completed.")

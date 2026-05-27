import arcpy
import os
import getpass
# import datetime
# now = datetime.datetime.now()
# Get the directory of the current script
# script_dir = os.path.dirname(os.path.realpath(__file__))
script_dir = r"D:\GenericArcGISEnterpriseDir\Creators\Connections"
# Set the workspace to the script directory
# arcpy.env.workspace = script_dir
# set output_dir to current directory
# output_dir = arcpy.env.workspace
# output_dir = r"D:\GenericArcGISConnectionsDir\general"
output_dir = input(f"Enter the directory to output the sde file to (Default: {script_dir}): ")
if output_dir == '' or output_dir is None:
    output_dir = script_dir
# print('File will be saved to:', output_dir)
# Set local variables
database_platform = "SQL_SERVER"
account_authentication = "DATABASE_AUTH"
save_user_pass = "SAVE_USERNAME"
# Prompt the user for values
server = input("Enter the server name (Default: ORG-APP1): ")
if server == '' or server is None:
    server = "ORG-APP1"
database = input("Enter the database name: ")
username = input("Enter the server username (Default: general): ")
if username == '' or username is None:
    username = "general"
password = getpass.getpass(f"Enter the {username} password: ")
instance = f"{server}\\frutsql01"
sde_filename = database + "_" + username + ".sde"
sde_file_path = output_dir + "\\" + sde_filename
print('File will be saved as:', sde_filename)
# Execute CreateDatabaseConnection
failure = True
try:
    arcpy.CreateDatabaseConnection_management(output_dir, sde_filename, database_platform, instance, 
                                          account_authentication, username, password, 
                                          save_user_pass, database)
    failure = False
    print("Created sde file successfully.")
except arcpy.ExecuteError:
    print(f"Connection failed")
    print(arcpy.GetMessages(2))
except Exception as e:
    print("An unexpected error occurred")
    print(str(e))
if not failure:
    # test the sde file
    print("Testing the sde file...")
    try:
        sde_conn = arcpy.ArcSDESQLExecute(sde_file_path)
        print("Connection successful.")
    except arcpy.ExecuteError:
        print(f"Connection failed")
        print(arcpy.GetMessages(2))
    except Exception as e:
        print("An unexpected error occurred")
        print(str(e))
print("Script completed.")

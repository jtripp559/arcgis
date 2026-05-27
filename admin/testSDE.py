# import sys
import arcpy
from arcpy import ExecuteError
import getpass
# Prompt the user to enter the database name
sde_connection_path = input("Enter the full path to the sde file: ")
failure = True
if sde_connection_path != "":
    print("SDE connection path:", sde_connection_path)
    # Test the connection
    try:
        sde_conn = arcpy.ArcSDESQLExecute(sde_connection_path)
        failure = False
    # except Exception as e:
    except arcpy.ExecuteError:
        print(f"Connection failed")
        print(arcpy.GetMessages(2))
    except Exception as e:
        print("An unexpected error occurred")
        print(str(e))
if failure:
    # Prompt the user to enter the database name
    database = input("Enter the database name: ")
    # Get the password from the user
    password = getpass.getpass("Enter the sde password: ")
    print('Attempting to connect using the sde connection string...')
    # Test the connection
    try:
        sde_conn = arcpy.ArcSDESQLExecute(server="ORG-APP1", instance="ORG-APP1\\frutsql01", database=database, user="sde", password=password)
        failure = False
    # except Exception as e:
    except arcpy.ExecuteError:
        print(f"Connection failed")
        print(arcpy.GetMessages(2))
    except Exception as e:
        print("An unexpected error occurred")
        print(str(e))
if not failure:
    print("Connection successful.")
    print(sde_conn)
    
import arcpy
import getpass

db_admin_username = "dbadmin"
sde_username = "sde"
db_instance = r"ORG-APP1\frutsql01"
output_dir = r"D:\GenericArcGISConnectionsDir"

db_acct_auth = "DATABASE_AUTH"
db_platform = "SQL_SERVER"

def create_geodatabase():
    db_created = False
    try:
        out_result = arcpy.management.CreateEnterpriseGeodatabase(
            database_platform=db_platform, 
            instance_name=db_instance, 
            database_name=db_name, 
            account_authentication=db_acct_auth, 
            database_admin=db_admin_username, 
            database_admin_password=gdb_pw, 
            sde_schema="SDE_SCHEMA", 
            gdb_admin_name=sde_username, 
            gdb_admin_password=gdb_pw, 
            tablespace_name="", 
            authorization_file=r"\\org-app2\c$\Program Files\esri\License11.5\sysgen\keycodes", 
            spatial_type="")
        print(out_result)
        db_created = True
    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as e:
        print(e)
    return db_created

def create_db_connection(return_conn_username=""):
    return_conn_file_path = None
    
    # Create SDE connection files
    save_user_pass = "SAVE_USERNAME"
    users = [db_admin_username, sde_username]
    for username in users:
        sde_filename = f"{db_name}_{username}.sde"
        sde_file_path = f"{output_dir}\\{sde_filename}"
        
        # if sde_file_path already exists, skip creating the file
        if not arcpy.Exists(sde_file_path):
            # If admin user connection doesn't exist, ensure geodatabase is created
            if username == db_admin_username:
                create_geodatabase()
            print(f"\nCreating SDE connection file for {username}...")
            try:
                arcpy.CreateDatabaseConnection_management(
                    output_dir, 
                    sde_filename, 
                    db_platform, 
                    db_instance, 
                    db_acct_auth, 
                    username, 
                    gdb_pw, 
                    save_user_pass, 
                    db_name
                )
                print(f"Created {sde_filename} successfully.")
                    
            except arcpy.ExecuteError:
                print(f"Failed to create SDE file for {username}")
                print(arcpy.GetMessages(2))
            except Exception as e:
                print(f"An unexpected error occurred creating SDE file for {username}")
                print(str(e))
            
        # Test the SDE file
        print(f"Testing {sde_filename}...")
        try:
            sde_conn = arcpy.ArcSDESQLExecute(sde_file_path)
            if username == return_conn_username:
                return_conn_file_path = sde_file_path
            print(f"Connection test successful for {username}.")
        except arcpy.ExecuteError:
            print(f"Connection test failed for {username}")
            print(arcpy.GetMessages(2))
        except Exception as e:
            print(f"An unexpected error occurred testing {username} connection")
            print(str(e))
            
    return return_conn_file_path

def create_roles(sde_conn_file):
    if not sde_conn_file:
        print("No connection file provided for role creation.")
        return
    db_roles = {'data creator', 'data editor', 'data viewer'}
    for role in db_roles:
        try:
            arcpy.management.CreateRole(sde_conn_file, role)
            print(f"Created role: {role}")
        except arcpy.ExecuteError:
            print(f"Failed to create role: {role}")
            print(arcpy.GetMessages(2))
        except Exception as e:
            print(f"An unexpected error occurred creating role: {role}")
            print(str(e))

print(f"This script will create a geodatabase on the SQL Server instance: {db_instance}")

db_name = input("Enter new database name: ")
if not db_name:
    print("Database name is required.")
    exit(1)
gdb_pw = getpass.getpass(prompt="Enter database password: ")
if not gdb_pw:
    print("Password is required.")
    exit(1)

print("\nCreating geodatabase and SDE connection files...")
admin_conn_file = create_db_connection(return_conn_username=db_admin_username)
print("\nCreating database roles...")
create_roles(admin_conn_file)

print("Script completed.")
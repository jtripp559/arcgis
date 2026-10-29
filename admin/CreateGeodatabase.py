import arcpy
import getpass

db_admin_username = "rrggis"
sde_username = "sde"
db_instance = r"NBS-APP1\frutsql01"
output_dir = r"T:\ArcGISDataset\Enterprise\Connections"

db_acct_auth = "DATABASE_AUTH"
db_platform = "SQL_SERVER"

# Database-level privileges to grant per role: {role_name: [privilege, ...]}.
# Add more roles here in the future (e.g. "data editor", "data viewer") with their own privilege
# lists and they will be granted automatically. These are all database-scoped permissions in SQL
# Server; each is run as its own GRANT statement (no GO -- that is an SSMS batch separator, not
# T-SQL). GRANT is idempotent, so re-running is harmless. For now only [data creator] is granted;
# data editor / data viewer are intentionally left as-is.
ROLE_DB_PRIVILEGES = {
    "data creator": [
        "ALTER",
        "CREATE PROCEDURE",
        "CREATE SYNONYM",
        "CREATE TABLE",
        "CREATE VIEW",
        "DELETE",
        "EXECUTE",
        "INSERT",
        "REFERENCES",
        "SELECT",
        "UPDATE",
        "VIEW DEFINITION",
    ],
    # "data editor": ["SELECT", "INSERT", "UPDATE", "DELETE", "EXECUTE", "VIEW DEFINITION"],
    # "data viewer": ["SELECT", "VIEW DEFINITION"],
}

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
            authorization_file=r"\\nbs-app2\c$\Program Files\esri\License11.5\sysgen\keycodes", 
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

def grant_role_privileges(sde_conn_file):
    # Grant the database-level privileges in ROLE_DB_PRIVILEGES to each configured role.
    # Runs over the db-admin (rrggis) connection, which has authority to GRANT. Each role must
    # already exist (created by create_roles). Each statement is executed separately.
    if not sde_conn_file:
        print("No connection file provided for granting privileges.")
        return
    if not ROLE_DB_PRIVILEGES:
        print("No roles configured in ROLE_DB_PRIVILEGES; skipping grants.")
        return
    try:
        sde_conn = arcpy.ArcSDESQLExecute(sde_conn_file)
    except Exception as e:
        print(f"Failed to open a SQL connection for grants: {e}")
        return
    for role, privileges in ROLE_DB_PRIVILEGES.items():
        print(f"\nGranting database privileges to [{role}]...")
        granted = 0
        for priv in privileges:
            sql = f"GRANT {priv} TO [{role}];"
            try:
                sde_conn.execute(sql)
                granted += 1
                print(f"  GRANT {priv} TO [{role}]")
            except Exception as e:
                print(f"  Failed: GRANT {priv} TO [{role}] -> {e}")
        print(f"Granted {granted}/{len(privileges)} privileges to [{role}].")


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

print("\nGranting database privileges to configured roles...")
grant_role_privileges(admin_conn_file)

print("Script completed.")
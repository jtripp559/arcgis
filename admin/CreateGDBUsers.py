'''
Name: CreateGDBUsers.py
Developed by: Julie Tripp
Date: 06/02/2026

Summary:
    Creates the schema-owner database users (and their matching schemas) in a
    Microsoft SQL Server enterprise geodatabase, using the Esri "Create Database
    User" geoprocessing tool (arcpy.management.CreateDatabaseUser).

    In a SQL Server enterprise geodatabase, data ownership is by database user and
    each data-owner user gets a schema of the SAME name. So to end up with schemas
    clim / crop / land / ws, you create four users with those names. Data they
    create is then stored and owned as e.g. RRGOrg.clim.<FeatureClass>. The 'sde'
    user owns the geodatabase system tables only -- do NOT store data in sde.

    For SQL Server, CreateDatabaseUser creates a login, a database user, a schema
    with the same name set as the user's default schema, and grants the privileges
    a geodatabase data owner needs (CREATE TABLE / VIEW / PROCEDURE).

    After each user is created, it is added (membership) to the database role named
    by USER_ROLE (default 'data creator') using arcpy.management.CreateRole, which
    creates the role if it does not already exist. The role's actual dataset-level
    privileges are granted separately by ApplyDBRolePrivileges.py once data exists.
    Set USER_ROLE to "" to skip the role step.

Usage:
    Run this script and follow the prompts. You can either point it at an existing
    administrator .sde connection file, or, if you don't have one (or the one you
    give is not valid), enter the connection details/credentials and the script will
    build a temporary administrator connection (deleted at the end). Either way, each
    user is created through that admin connection.

    Run order:
        1. Run THIS script (CreateGDBUsers.py) to create the schema-owner users.
        2. Then run CreateSDEFiles.py to create one .sde connection file per user
           (the per-user connection test will only pass once the users exist).

    IMPORTANT: The administrator account you enter must have permission to create
    logins/users in the instance (typically a SQL Server sysadmin such as 'sa', or
    the geodatabase administrator 'sde' if it has been granted that right). The
    geodatabase admin password is required.
'''
import arcpy
import os
import getpass
import tempfile

# Schema-owner users to create (schema name == user name in SQL Server).
SCHEMA_USERS = ["general"] # ["clim", "crop", "land", "ws"]

# Database role to add each new schema owner to (membership). The role is created
# automatically if it does not exist (arcpy.management.CreateRole). The role's actual
# dataset privileges are granted separately by ApplyDBRolePrivileges.py. Schema owners
# create/own data, so 'data creator' is the usual fit. Set to "" or None to skip.
USER_ROLE = "data creator"

# Connection settings (match CreateSDEFiles.py).
database_platform = "SQL_SERVER"
account_authentication = "DATABASE_AUTH"
save_user_pass = "SAVE_USERNAME"
# Authentication type for the NEW users: "DATABASE_USER" (SQL login) or "OPERATING_SYSTEM_USER".
new_user_auth = "DATABASE_USER"

def grant_role(admin_sde_path, role, user):
    # Add a database user to a database role (membership) using the Create Role tool.
    # CreateRole creates the role if it does not already exist, then grants the named
    # user membership (grant_revoke="GRANT"). Run through the admin connection.
    try:
        arcpy.management.CreateRole(
            input_database=admin_sde_path,
            role=role,
            grant_revoke="GRANT",
            user_name=user)
        print(f"  Added '{user}' to role '{role}'.")
        return True
    except arcpy.ExecuteError:
        print(f"  WARNING: could not add '{user}' to role '{role}':")
        print(arcpy.GetMessages(2))
        return False
    except Exception as e:
        print(f"  WARNING: could not add '{user}' to role '{role}': {e}")
        return False


def validate_sde_connection(sde_path):
    # Return True if sde_path is an existing, usable enterprise geodatabase
    # connection file (.sde). Tries to describe the workspace so a stale or
    # bad-credential connection is rejected, not just a missing file.
    if not sde_path:
        return False
    if not os.path.isfile(sde_path):
        print(f"  '{sde_path}' does not exist.")
        return False
    try:
        desc = arcpy.Describe(sde_path)
        if getattr(desc, "dataType", None) != "Workspace":
            print(f"  '{sde_path}' is not a workspace connection.")
            return False
        # Touch the connection so invalid credentials / unreachable server fail here
        # rather than later when creating users.
        if desc.workspaceType != "RemoteDatabase":
            print(f"  '{sde_path}' is not an enterprise database connection.")
            return False
        prev_ws = arcpy.env.workspace
        try:
            arcpy.env.workspace = sde_path
            arcpy.ListDatasets()  # forces an actual connection attempt
        finally:
            arcpy.env.workspace = prev_ws
        return True
    except Exception as e:
        print(f"  '{sde_path}' is not a valid/usable connection: {e}")
        return False


# --- Obtain an administrator connection for the Create Database User tool ---
# First ask for an existing admin .sde connection file. If none is given, or the one
# given is not valid, fall back to prompting for credentials and building a temporary
# admin connection (deleted at the end).
temp_dir = None
admin_sde_path = ""
created_temp_connection = False
admin_ok = False

existing_path = input(
    "Enter the path to an existing admin .sde connection file "
    "(leave blank to enter credentials instead): ").strip().strip('"')

if existing_path and validate_sde_connection(existing_path):
    admin_sde_path = existing_path
    admin_ok = True
    print(f"Using existing admin connection: {admin_sde_path}")
else:
    if existing_path:
        print("Provided .sde connection is missing or not valid; "
              "falling back to entering credentials.\n")

    # --- Prompt for shared connection values ---
    server = input("Enter the server name (Default: NBS-APP1): ").strip() or "NBS-APP1"
    instance_suffix = input("Enter the SQL instance (Default: frutsql01): ").strip() or "frutsql01"
    instance = f"{server}\\{instance_suffix}"
    database = input("Enter the database (geodatabase) name (Default: RRGOrg): ").strip() or "RRGOrg"

    # --- Administrator credentials (must be able to create logins/users) ---
    admin_user = input("Enter the geodatabase/DB admin username (Default: sde): ").strip() or "sde"
    admin_password = getpass.getpass(f"Enter the {admin_user} password: ")

    # --- Build a temporary administrator connection ---
    temp_dir = tempfile.mkdtemp()
    admin_sde_name = f"{database}_{admin_user}_admin.sde"
    admin_sde_path = os.path.join(temp_dir, admin_sde_name)
    print(f"\nCreating temporary admin connection: {admin_sde_path}")
    try:
        arcpy.management.CreateDatabaseConnection(
            out_folder_path=temp_dir,
            out_name=admin_sde_name,
            database_platform=database_platform,
            instance=instance,
            account_authentication=account_authentication,
            username=admin_user,
            password=admin_password,
            save_user_pass=save_user_pass,
            database=database)
        admin_ok = True
        created_temp_connection = True
        print("Admin connection created.")
    except arcpy.ExecuteError:
        print("Failed to create admin connection:")
        print(arcpy.GetMessages(2))
    except Exception as e:
        print(f"Unexpected error creating admin connection: {e}")

# --- Create each schema-owner user ---
created = 0
if admin_ok:
    for user in SCHEMA_USERS:
        print(f"\nCreating database user/schema: {user}")
        pwd = getpass.getpass(f"  Enter a password for new user '{user}': ")
        if pwd == "":
            print(f"  Skipping '{user}' -- no password entered.")
            continue
        try:
            arcpy.management.CreateDatabaseUser(
                input_database=admin_sde_path,
                user_authentication_type=new_user_auth,
                user_name=user,
                user_password=pwd)
            print(f"  Created user '{user}' with schema '{user}'.")
            created += 1
            if USER_ROLE:
                grant_role(admin_sde_path, USER_ROLE, user)
        except arcpy.ExecuteError:
            print(f"  Failed to create user '{user}':")
            print(arcpy.GetMessages(2))
        except Exception as e:
            print(f"  Unexpected error creating user '{user}': {e}")

# --- Clean up the temporary admin connection (only if we created it) ---
if created_temp_connection:
    try:
        if os.path.exists(admin_sde_path):
            os.remove(admin_sde_path)
        if temp_dir and os.path.isdir(temp_dir):
            os.rmdir(temp_dir)
    except Exception as e:
        print(f"Could not clean up temp connection: {e}")

print(f"\nCreated {created} of {len(SCHEMA_USERS)} users.")
print("Next step: run CreateSDEFiles.py to create the .sde connection files.")
print("Script completed.")

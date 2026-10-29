import arcpy
import traceback
import getpass

workspace_full_path = r"T:\ArcGISDataset\Enterprise\Connections\NBS_WaterBalance_sde.sde"
portal_url="https://maps.rrgnbs.com/arcgisportal"

input_feature = f"{workspace_full_path}/SDE.RRG_L0BASINATLAS_V10_LEV09"
output_feature = f"{workspace_full_path}/SDE.BasinATLAS_lev09"

fields_to_keep = ["HYBAS_ID", "hybas_lev_idx", "hybas_level", "region_id"]

connected = False
try:
    # Set the workspace to your enterprise geodatabase connection
    arcpy.env.workspace = workspace_full_path
    print(f"Workspace set to {workspace_full_path}")
    connected = True
except Exception as e:
    print(f"Failed to set the workspace to {workspace_full_path}: {e}")
    env_set = False
    
if connected:
    connected = False
    portal_username = 'rrgadmin'
    portal_password = getpass.getpass(f"**  ArcGIS Portal Password for {portal_username}: ")
    if portal_username == "" or portal_password == "":
        print("Missing portal username or password.")
    else:
        try:
            arcpy.SignInToPortal(portal_url, portal_username, portal_password)
            connected = True
            print(f"Connected to {portal_url} as {portal_username}")
        except Exception as e:
            print(f"Failed to connect to {portal_url}: {e}")
success = True

success = False
if connected:
    try:
        # Create a field mapping object
        field_mappings = arcpy.FieldMappings()
        
        # Add only the fields to keep
        for field in fields_to_keep:
            field_map = arcpy.FieldMap()
            field_map.addInputField(input_feature, field)
            field_mappings.addFieldMap(field_map)
            
        arcpy.conversion.ExportFeatures(
            in_features=input_feature,
            out_features=output_feature,
            where_clause="",
            use_field_alias_as_name="NOT_USE_ALIAS",
            field_mapping=field_mappings,
            sort_field="hybas_lev_idx ASCENDING"
        )
        success = True
        print(f"Exported {input_feature} to {output_feature}")
    except Exception as ex:
        tb = traceback.format_exc()
        print(f"An error occurred during ExportFeatures: {str(ex)}\nTraceback: {tb}")


# grant privileges to role data_viewer, data_creator, data_editor
if success:
    try:
        arcpy.management.ChangePrivileges(
            in_dataset=output_feature,
            user="data_viewer",
            View="GRANT",
            Edit="REVOKE"
        )
        arcpy.management.ChangePrivileges(
            in_dataset=output_feature,
            user="data_creator",
            View="GRANT",
            Edit="GRANT"
        )
        arcpy.management.ChangePrivileges(
            in_dataset=output_feature,
            user="data_editor",
            grant="GRANT",
            revoke="GRANT"
        )
    except Exception as ex:
        tb = traceback.format_exc()
        print(f"An error occurred during ChangePrivileges: {str(ex)}\nTraceback: {tb}")

'''
if success:
    try:
        arcpy.management.DeleteField(
            in_table=output_feature,
            drop_field=";".join(fields_to_keep),
            method="KEEP_FIELDS"
        )
    except Exception as ex:
        tb = traceback.format_exc()
        print(f"An error occurred during DeleteField: {str(ex)}\nTraceback: {tb}")
'''

print("Done.")
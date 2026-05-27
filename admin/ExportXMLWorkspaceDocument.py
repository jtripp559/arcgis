import arcpy
print('starting ExportXMLWorkspaceDocument')
arcpy.management.ExportXMLWorkspaceDocument(
    in_data=r"C:\Admin\Tools\Connections\ENT_DB3_dbadmin.sde",
    out_file=r"C:\Admin\Tools\Output\ENT_DB3_ExportXML_DataSchema_20250127.xml",
    export_type="DATA",
    storage_type="BINARY",
    export_metadata="METADATA"
)
print('finished ExportXMLWorkspaceDocument')

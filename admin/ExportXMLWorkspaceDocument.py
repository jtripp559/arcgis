import arcpy
print('starting ExportXMLWorkspaceDocument')
arcpy.management.ExportXMLWorkspaceDocument(
    in_data=r"C:\Admin\Tools\Connections\RRG_TestEnterprise_rrggis.sde",
    out_file=r"C:\Admin\Tools\Output\RRG_TestEnterprise_ExportXML_DataSchema_20250127.xml",
    export_type="DATA",
    storage_type="BINARY",
    export_metadata="METADATA"
)
print('finished ExportXMLWorkspaceDocument')

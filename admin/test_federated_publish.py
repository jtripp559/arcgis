# -*- coding: utf-8 -*-
"""
test_federated_publish.py  -- ISOLATION TEST for the AGOL->RRGOrg migration Phase 5.

Publishes ONE SDE feature class to the federated ArcGIS Server as a REFERENCED service using the
CANONICAL arcpy path for a referenced FEATURE service on a federated server:

    server_type = "FEDERATED_SERVER"
    service_type = "MAP_IMAGE"          # FEATURE is NOT valid with FEDERATED_SERVER (arcpy validation_map);
                                        # a referenced publish is a Map Image service with Feature Access on,
                                        # which yields the MapServer + FeatureServer pair (plan decision #9).
    copyDataToServer = False            # by reference -- data stays in the registered RRGOrg SDE
    + enable the FeatureServer extension in the sddraft (Feature Access)

NO offline workaround, NO connection-string DOM injection. Purpose: confirm this path succeeds where
PublishFromDBToFeatureService.py's HOSTING_SERVER + offline + FEATURE draft fails with ERROR 002901.

Run on nbs-app2 in the ArcGIS Pro/Server conda env:
    python test_federated_publish.py

Portal login comes from the Windows Credential Manager (key 'portal' -> nbs_arcgis_admin), prompt fallback.
"""

import os
import sys
import traceback
from xml.dom import minidom as DOM

import arcpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import credential_store

# ---- config -----------------------------------------------------------------
PORTAL_URL    = "https://maps.rrgnbs.com/arcgisportal"
FED_SERVER    = "https://maps.rrgnbs.com/arcgisserver"     # federated server (federatedServerUrl / in_server)
SDE           = r"T:\ArcGISDataset\Enterprise\Connections\RRGOrg_ws.sde"
FC            = "RRGOrg.ws.Change_in_SW_Supply_by_2030"    # fully-qualified, already in the SDE
SERVICE_NAME  = "TEST_Federated_Change_SW"                 # throwaway test service name
SERVER_FOLDER = "MaxEnt"                                   # set "" to publish to the server root
COPY_DATA     = False                                      # False = BY REFERENCE (RRGOrg is registered)
APRX          = r"C:\Admin\Tools\ArcGIS Admin\Input\BlankTemplateProject\BlankTemplateProject.aprx"
OUT_DIR       = r"T:\ArcGISDataset\Data Science Scripts\Other scripts\Admin\Metadata\Output\AGOL\Migrate\Staging"


def enable_feature_access(sddraft_path):
    """Turn on the FeatureServer extension (Feature Access) in a Map Image sddraft so the referenced
    publish produces a FeatureServer alongside the MapServer."""
    doc = DOM.parse(sddraft_path)
    enabled_any = False
    for ext in doc.getElementsByTagName("SVCExtension"):
        type_names = ext.getElementsByTagName("TypeName")
        if type_names and type_names[0].firstChild and type_names[0].firstChild.data == "FeatureServer":
            for en in ext.getElementsByTagName("Enabled"):
                if en.firstChild:
                    en.firstChild.data = "true"
                    enabled_any = True
    with open(sddraft_path, "w") as f:
        doc.writexml(f)
    print(f"FeatureServer extension enabled in sddraft: {enabled_any}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    sddraft_path = os.path.join(OUT_DIR, SERVICE_NAME + ".sddraft")
    sd_path      = os.path.join(OUT_DIR, SERVICE_NAME + ".sd")
    tmp_aprx     = os.path.join(OUT_DIR, SERVICE_NAME + ".aprx")
    for p in (sddraft_path, sd_path):
        if os.path.exists(p):
            os.remove(p)

    # Shared helper: stored 'portal' credential FIRST, Pro/prompt fallback, and sign_in_arcpy=True so arcpy
    # (used for the publish below) is signed in to the same portal -- FATAL if that arcpy sign-in fails.
    gis = credential_store.connect(PORTAL_URL, key="portal", default_username="rrgadmin", sign_in_arcpy=True)
    print(f"signed in to {PORTAL_URL} as {gis.properties.user.username}")

    arcpy.env.overwriteOutput = True

    print(f"opening template {APRX}")
    aprx = arcpy.mp.ArcGISProject(APRX)
    aprx.saveACopy(tmp_aprx)
    aprx = arcpy.mp.ArcGISProject(tmp_aprx)

    maps = aprx.listMaps()
    m = maps[0] if maps else aprx.createMap(SERVICE_NAME)
    for lyr in m.listLayers():
        try:
            m.removeLayer(lyr)
        except Exception:
            pass

    src = os.path.join(SDE, FC)
    if not arcpy.Exists(src):
        print(f"!! source FC not found: {src}")
        return
    print(f"adding layer {src}")
    fl = arcpy.management.MakeFeatureLayer(src, SERVICE_NAME)
    m.addLayer(fl.getOutput(0))

    cim = m.getDefinition("V3")
    cim.useServiceLayerIDs = True
    m.setDefinition(cim)
    aprx.save()

    print("creating FEDERATED_SERVER MAP_IMAGE sharing draft (referenced)")
    sddraft = m.getWebLayerSharingDraft(server_type="FEDERATED_SERVER",
                                        service_type="MAP_IMAGE",
                                        service_name=SERVICE_NAME)
    sddraft.federatedServerUrl = FED_SERVER
    sddraft.copyDataToServer = COPY_DATA          # False -> by reference (data stays in RRGOrg SDE)
    sddraft.overwriteExistingService = True
    sddraft.summary = "Isolation test: federated referenced publish"
    sddraft.tags = "test, referenced"
    try:
        if SERVER_FOLDER:
            sddraft.serverFolder = SERVER_FOLDER
    except Exception as e:
        print(f"(serverFolder not settable on this draft: {e})")

    print(f"exporting sddraft -> {sddraft_path}")
    sddraft.exportToSDDraft(sddraft_path)

    enable_feature_access(sddraft_path)

    print(f"staging -> {sd_path}")
    arcpy.server.StageService(sddraft_path, sd_path)

    print(f"uploading to {FED_SERVER} ...")
    arcpy.server.UploadServiceDefinition(sd_path, FED_SERVER)
    print("=== PUBLISHED OK ===  (FEDERATED_SERVER + MAP_IMAGE + Feature Access path works)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("=== FAILED ===")
        traceback.print_exc()

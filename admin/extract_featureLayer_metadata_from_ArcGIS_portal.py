"""
================================================================================
Script Name : extract_featureLayer_metadata_from_ArcGIS_portal.py
Description : Connects to the RRG NBS internal ArcGIS Enterprise Portal and
              retrieves all Feature Serviceitems from a
              specified folder (It helped to set a folder in ArcGIS Portal).
              Outputs a Python list-of-dicts (layer_list)
              containing each layer's title, REST URL, snippet, and description,
              ready to be copied into downstream publishing or inventory scripts.

Usage       : Run interactively in an ArcGIS Pro Python command or Jupyter Notebook
              or from a conda environment with the arcgis package installed.
              Active Portal sign-in (GIS("pro")) is required.

Inputs      : TARGET_FOLDER  - name of the Portal folder where features are located
                               (Example here: "RRGNBS Cacao Suitability")

Outputs     : Printed Python list literal (layer_list) to stdout.
              Copy-paste output into script `publish_features_to_agol_bulk.py.py` as needed.

Dependencies: arcgis (ArcGIS API for Python)
              Active ArcGIS Pro / Portal session

Author: guillermo.ponce@rrgnbs.com
Created     : 2026-03-26
Last Modified: 2026-03-27
================================================================================
"""

from arcgis.gis import GIS

# 1. Connect to  Internal Portal (set Portal as active portal in ArcGIS Pro session)
gis_portal = GIS("pro")
# This is the folder where all the features are located in ArcGIS Portal
TARGET_FOLDER = "RRGNBS Cacao Suitability"

print("layer_list = [")

# Search for all items in that specific folder
user = gis_portal.users.me
folder_items = user.items(folder=TARGET_FOLDER)

for item in folder_items:
    if item.type in ["Feature Service", "Image Service"]:
        # For the cases where internal description is empty, just a fallback
        final_desc = item.description if item.description else ""
        final_snippet = item.snippet if item.snippet else item.title

        print(f"    {{")
        print(f'        "title": "{item.title}",')
        print(f'        "url": "{item.url}",')
        print(f'        "snippet": "{final_snippet}",')
        print(f'        "description": """{final_desc}"""')
        print(f"    }},")

print("]")

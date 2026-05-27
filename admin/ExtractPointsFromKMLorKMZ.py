from arcgis.features import GeoAccessor
import zipfile
import os
import pandas as pd
# import geopandas as gpd
# import gc
import arcpy
import traceback

file_list_kmz_or_kml = [r"C:\GIS\Edizione\MaitenChacay.kmz", r"C:\GIS\Edizione\LelequeFondo2.kmz"]

def find_kml_file(folder):
    kml_file_path = None
    kml_files = [f for f in os.listdir(folder) if f.endswith('.kml')]
    if len(kml_files) > 0:
        # return the first KML file found in the folder
        kml_file_path = os.path.join(folder, kml_files[0])
        print(f"KML file: {kml_file_path}")
    return kml_file_path
    
    

def get_kml_file(file_path):
    kml_file_path = None
    file_path = file_path.lower()
    if file_path.endswith('.kmz'):
        kml_file_name = os.path.basename(file_path).replace('.kmz', '.kml')
        # change output_folder to output_folder + kml_file_name less extension
        output_folder = os.path.join(os.path.dirname(file_path), kml_file_name.replace('.kml', ''))
        # Create the output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        kml_file_path = find_kml_file(output_folder)
        # kml_file_path = os.path.join(output_folder, kml_file_name)
        # if not os.path.exists(kml_file_path):
        if kml_file_path is None:
            try:
                # Extract the KMZ file
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(output_folder)
                kml_file_path = find_kml_file(output_folder)
            except Exception as e:
                print(f"Error extracting KMZ file: {e}")
                kml_file_path = None
            if not os.path.exists(kml_file_path):
                print(f"Error extracting KMZ file: '{kml_file_path}' not found")
                kml_file_path = None
    return kml_file_path

def extract_points_from_kml(kml_file_path, write_to_csv=True):
    print(f"Extracting points from KML file: {kml_file_path}")
    points_df = None
    try:
        # Define the output geodatabase and feature class names
        output_gdb = os.path.join(os.path.dirname(kml_file_path), 'temp.gdb')
        arcpy.env.overwriteOutput = True
        
        # Create a temporary geodatabase
        if not arcpy.Exists(output_gdb):
            arcpy.CreateFileGDB_management(os.path.dirname(kml_file_path), 'temp.gdb')
        
        # Convert KML to Layer
        arcpy.KMLToLayer_conversion(kml_file_path, os.path.dirname(output_gdb), 'temp_layer')
        
        # Get the path to the feature class
        layer_folder = os.path.join(os.path.dirname(output_gdb), 'temp_layer.gdb')
        arcpy.env.workspace = layer_folder
        
        datasets = arcpy.ListDatasets()
        print(f"Datasets: {datasets}")
        
        feature_class = None
        feature_class_type = None
        
        for dataset in datasets:
            arcpy.env.workspace = os.path.join(layer_folder, dataset)
            dataset_feature_classes = arcpy.ListFeatureClasses()
            print(f"Feature classes: {dataset_feature_classes} in dataset: {dataset}")
            # determine if dataset_feature_classes has a feature class of type Points or Polygons
            for fc in dataset_feature_classes:
                if 'Points' in fc:
                    feature_class_type = 'Points'
                    feature_class = fc
                    break
                elif 'Polygons' in fc:
                    feature_class_type = 'Polygons'
                    feature_class = fc
                    break
        if not feature_class:
            raise FileNotFoundError("Feature class not found in the converted KML.")

        print(f"Feature class: {feature_class}")
        print(f"Feature class type: {feature_class_type}")
        
        # Extract latitude and longitude of each point
        points = []
        if feature_class_type == 'Points':
            with arcpy.da.SearchCursor(feature_class, ['SHAPE@XY']) as cursor:
                for row in cursor:
                    print(f"Row: {row}")
                    x, y = row[0]
                    points.append({'latitude': y, 'longitude': x})
        elif feature_class_type == 'Polygons':
            with arcpy.da.SearchCursor(feature_class, ['SHAPE@']) as cursor:
                for row in cursor:
                    geom = row[0]
                    if geom is not None:
                        print(f"Geometry: {geom}")
                        print(f"Geometry type: {geom.type}")
                        if geom.type == 'point':
                            x, y = geom.firstPoint.X, geom.firstPoint.Y
                            points.append({'latitude': y, 'longitude': x})
                        else:
                            centroid = geom.centroid
                            points.append({'latitude': centroid.Y, 'longitude': centroid.X})
                            '''
                            for part in geom:
                                for pnt in part:
                                    x, y = pnt.X, pnt.Y
                                    points.append({'latitude': y, 'longitude': x})
                            '''
        
        # Create a DataFrame
        points_df = pd.DataFrame(points)
        
        # make points_df unique values only
        points_df = points_df.drop_duplicates()
        
        if write_to_csv:
            output_file_path = kml_file_path.replace('.kml', '_points.csv')
            points_df.to_csv(output_file_path, index=False, header=True)
            print(f"Points saved to: {output_file_path}")
        
        # Clean up temporary files
        arcpy.Delete_management(output_gdb)
        
    except Exception as e:
        print(f"Error reading KML file: {e}")
        print(traceback.format_exc())
    return points_df

print("Extracting points from KML or KMZ files...")
for file in file_list_kmz_or_kml:
    kml_file_path = get_kml_file(file)
    if kml_file_path is None:
        continue
    points_df = extract_points_from_kml(kml_file_path)

print("Done")
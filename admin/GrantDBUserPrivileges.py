# GrantDBUserPrivileges.py
#
# Created By:	Julie Tripp
#				julie.tripp@rrgnbs.com
# 				03/01/2024
#
# Description: 
# 	This script grants privileges to a database user or role for a list of datasets, feature classes, tables, or rasters in an enterprise geodatabase.
#
# Developer Notes:
# 	1. For quick execution, Execute this script from the ArcGIS Server machine.
#   2. ArcGIS DB Roles: data editor, data viewer, data creator
#
# Usage:
#	1. Create a CSV file with a column for the dataset names.
#	2. Run the script in a Python IDE or command line.
#	3. Enter the input file path when prompted.
#	4. Enter the output file path when prompted.
#	5. Enter the database connection file path when prompted.
#	6. Enter the user or role to update when prompted.
#	7. Review the output file for the status of the privilege updates.
#
# Script Workflow:
# 	1. Prompt the user for the input file, output file, database connection file, and the user or role to update.
# 	2. Read the input file and get the dataset values from the specified column.
# 	3. Grant privileges to the specified user or role for each dataset in the input file.
# 	4. Write the results to the output file.
# 	5. Display the number of datasets to import and the output file path.
#
# Input File:
# 	The input file must be a CSV file with a column for the dataset names. 
# 	If the input file has a header, the column name should be 'dataset'. 
# 		Otherwise, the first column should contain the dataset names.
# 	The dataset names may include or exclude the database connection file path.
# 		If the database connection file path is not included, the user must provide 
# 		the database connection file path when prompted by the script.
#
# Output File:
# 	The output file will be a CSV file with two columns: 'Dataset' and 'Status'.
# 	The 'Dataset' column will contain the dataset names from the input file.
# 	The 'Status' column will contain the status of the privilege update (Success or Error).
# 	The output file will be saved to the specified output file path.
# 	If the output file path is not specified, the output file will be saved to the 'Output' folder in the current directory.
# 	If the output file path ends with '.csv', the script will append a timestamp to the output file name.
#
# Database Connection File:
# 	The database connection file is the path to the enterprise geodatabase connection file (.sde).
#	If the database connection file path is not included in the dataset names, 
# 		the entered database connection file path will be prepended to the dataset names.
#
# User or Role to Update:
# 	The user or role to update must be a valid database user or role in the enterprise geodatabase.
# 	If the user or role to update is not specified, the script will default to 'sde'.
#
# Example Input File:
# 	dataset
# 	RRG_TestEnterprise_rrggis.DBO.COUNTIES
# 	RRG_TestEnterprise_rrggis.DBO.CITIES
# 	RRG_TestEnterprise_rrggis.DBO.STATES
#
# Example Output File:
# 	Dataset,Status
# 	RRG_TestEnterprise_rrggis.DBO.COUNTIES,Success
# 	RRG_TestEnterprise_rrggis.DBO.CITIES,Success
# 	RRG_TestEnterprise_rrggis.DBO.STATES,Success
#
#
import arcpy
import csv
from tqdm import tqdm
import pandas as pd
import datetime
import os

# Get the current date and time
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# print("Example user roles: data_editor, data_viewer, data_creator")
print("Example user roles: data editor, data viewer, data creator")
user_to_update = input("Enter the database user or role to update: ")
if not user_to_update:
    print("User or role is required.")
    exit()
    # user_to_update = 'sde'

# input view grant or revoke
view_permission = input("Enter the view permission (GRANT, REVOKE, AS_IS): ")
if not view_permission:
    view_permission = 'GRANT'

# input edit grant or revoke
edit_permission = input("Enter the edit permission (GRANT, REVOKE, AS_IS): ")
if not edit_permission:
    edit_permission = 'AS_IS'

# prompt the user for the database connection file
db_connection_file = input("Enter the path to the database connection file: ")
if not db_connection_file:
    print("Database connection file is required.")
    exit()
#    db_connection_file = r"T:\ArcGISDataset\Enterprise\RRG_TestEnterprise_rrggis.sde"

try:
    # Set the workspace to your enterprise geodatabase connection
    arcpy.env.workspace = db_connection_file
    print(f"Workspace set to {db_connection_file}")
    connected = True
except Exception as e:
    print(f"Failed to set the workspace to {db_connection_file}: {e}")
    exit()

# Prompt the user for an input file path
input_file = input("Enter the path to the input file (OPTIONAL): ")
# if not input_file:
#     input_file = "Input\\DBDatasetsToGrantPrivileges.csv"

# Prompt the user for an output file path
output_file_input = input("Enter the desired path to the output file (OPTIONAL): ")
if output_file_input:
    output_file_input = os.path.dirname(output_file_input)
    if not os.path.exists(output_file_input):
        try:
            print('Creating output directory:', output_file_input)
            os.makedirs(output_file_input)
        except Exception as e:
            print('Error: ' + str(e))
            output_file_input = None
if not output_file_input:
    output_file_input = None
    try:
        script_path = os.path.abspath(__file__)
    except Exception as ex:
        print('Error: ' + str(e))
        print('trying os.getcwd')
        try:
            script_path = os.getcwd()
        except Exception as ex:
            print('Error: ' + str(e))
            script_path = None
    if not script_path is None:
        try:
            output_directory = os.path.dirname(script_path)
            output_directory = os.path.join(output_directory, "Output")
            if not os.path.exists(output_directory):
                os.makedirs(output_directory)
            output_file_input = os.path.join(output_directory, f"GrantDBUserPrivileges.csv")
        except Exception as ex:
            output_file_input = None
else:
    if not output_file_input.lower().endswith(".csv"):
        output_file_input = f"{output_file_input}.csv"
if not output_file_input is None:
    # Append timestamp to output file name
    output_file = output_file_input.replace(".csv", f"_{timestamp}.csv")
    print('Output File Path:', output_file)

datasets = []
if input_file:
    print("Reading input file...")
    # Read the first line of the input file
    first_line = pd.read_csv(input_file, nrows=1, header=None)
    # Check if 'dataset' is in the first line
    if 'dataset' in first_line.values[0]:
        # If 'dataset' is in the first line, assume it's a header
        df = pd.read_csv(input_file)
        df.columns = df.columns.str.lower()
        dataset_column = 'dataset'
    else:
        # If 'dataset' is not in the first line, assume there's no header
        df = pd.read_csv(input_file, header=None)
        dataset_column = df.columns[0]
    # Get the dataset values
    datasets = df[dataset_column].tolist()
else:
    # Get all the datasets from the database connection file
    print("Getting datasets from the database connection file...")
    # would you like to continue with the database connection file?
    continue_with_db = input("Use all datasets from the specified connection? (Y/N): ")
    if continue_with_db.lower() == 'n':
        exit()
    print("Setting workspace to", db_connection_file)
    try:
        arcpy.env.workspace = db_connection_file
        # Get datasets
        print("Retrieving items to update... This may take a few minutes.")
        print("Retrieving datasets")
        ds = arcpy.ListDatasets()
        if ds is not None:
            datasets.extend(ds)
        # Get feature classes
        print('Retrieving Feature Classes')
        fc = arcpy.ListFeatureClasses()
        if fc is not None:
            datasets.extend(fc)
        # Get tables
        print('Retrieving Tables')
        tb = arcpy.ListTables()
        if tb is not None:
            datasets.extend(tb)
        # Get rasters
        print('Retrieving Rasters')
        rs = arcpy.ListRasters()
        if rs is not None:
            datasets.extend(rs)
        # remove the database connection file path from the dataset names
        # datasets = [dataset.split('.')[-1] for dataset in datasets]
    except Exception as e:
        print('Error: ' + str(e))
if not datasets:
    print("No datasets found.")
    exit()

if datasets:
    dataset_count = len(datasets)
    print(f"Number of datasets to update: {dataset_count}")
    if not output_file_input is None:
        # create csv file and write datasets to it
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Dataset', 'Status'])
            for dataset in datasets:
                writer.writerow([dataset, 'Pending'])

    print('Updating privileges for ' + user_to_update)
    for dataset in tqdm(datasets):
        '''
        if db_connection_file:
            if db_connection_file not in dataset:
                dataset_path = db_connection_file + '\\' + dataset
        else:
            dataset_path = dataset
        '''
        dataset_path = dataset
        try:
            arcpy.management.ChangePrivileges(
                in_dataset=dataset_path,
                user=user_to_update,
                View=view_permission,
                Edit=edit_permission
            )
            status = 'Success'
        except arcpy.ExecuteError as e:
            print('Failed to update privileges for ' + dataset_path + '. Error: ' + str(e))
            exit()
        except Exception as e:
            status = 'Error: ' + str(e)
        if output_file_input is None:
            print(dataset + ' :: ' + status)
        else:
            with open(output_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([dataset, status])
    print('Privileges updated.')
    if not output_file_input is None:
        print('See ' + output_file + ' for details.')
else:
    print("No datasets, feature classes, tables, or rasters found.")

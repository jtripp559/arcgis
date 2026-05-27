# example: https://gis.example.com/arcgisserver/rest/services/WebTools/FarmGeneric/GPServer/Jobs/j17563ca436064fdb8aa965fdaf688039
# test running from Pro, Python, Spyder, etc.

import os
import sys
import importlib
import shutil
import json
import chardet
from datetime import datetime
import logging
import pyodbc
from dotenv import load_dotenv
from getpass import getpass
import xml.etree.ElementTree as ET
import re
# from sqlalchemy import create_engine, inspect

# Import send_email_using_powerautomate module with reload capability
mods = [r'D:\GenericScriptsDir\send_email_using_powerautomate']
for path in mods:
    sys.path.append(path)
module_name = "send_email_using_powerautomate"
if module_name in sys.modules:
    del sys.modules[module_name]
send_email_using_powerautomate = importlib.import_module(module_name)

source_directory = r'\\org-app2\c$\arcgisserver\directories\arcgisjobs'
output_directory = r'\\org-app2\D$\GenericArcGISDataDir\ArcGISServer\Tools\Outputs\Archive'

# Get the current timestamp and format it as a string
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
date = datetime.now().strftime('%Y%m%d')

def init_logging():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    log_dir = os.path.join(script_dir, 'Logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, 'GeoprocessingToolMonitor' + '_' + date + '.log')
    log_file_handler = logging.FileHandler(log_file)
    log_file_handler.setLevel(logging.INFO)
    log_console_handler = logging.StreamHandler()
    log_console_handler.setLevel(logging.ERROR)
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[log_file_handler, log_console_handler])

'''
def insert_jobinfo_to_feature_class(jobinfo):
    logging.info("Inserting jobinfo into the feature class...")
    try:
        # load variables from .env
        load_dotenv()
        sde_file_path = os.getenv('SDE_FILE_PATH')
        feature_class_name = os.getenv('FEATURE_CLASS_NAME')
        
        # Set the workspace to the SDE file
        arcpy.env.workspace = sde_file_path
        
        # Access the feature class
        feature_class = os.path.join(sde_file_path, feature_class_name)
        
        # Prepare the feature attributes
        attributes = {
            'jobId': jobinfo['jobId'],
            'source_directory': jobinfo['source_directory'],
            'archive_directory': jobinfo['archive_directory'],
            'archive_timestamp': jobinfo['archive_timestamp'],
            'definition': json.dumps(jobinfo['definition'])
        }
        
        # Create an insert cursor
        with arcpy.da.InsertCursor(feature_class, attributes.keys()) as cursor:
            cursor.insertRow(attributes.values())
        
        logging.info(f"Inserted jobinfo into the feature class '{feature_class_name}'")
    except Exception as e:
        logging.exception(f"An error occurred while inserting jobinfo into the feature class: {e}")
'''
    
def connect_to_database():
    logging.info("Connecting to the database...")
    try:
        # load variables from .env
        load_dotenv()
        server_name = os.getenv('GPTOOLMONITOR_DB_SERVER')
        db_name = os.getenv('GPTOOLMONITOR_DB_NAME')
        username = os.getenv('GPTOOLMONITOR_DB_USER')
        password = os.getenv('GPTOOLMONITOR_DB_PASSWORD')
        # if no DB_PASSWORD, prompt user to enter password
        if password == None:
            password = getpass(f"Enter the database password for {username}: ")
        # create a connection string
        conn_str = (
            r'DRIVER={ODBC Driver 17 for SQL Server};'
            f'SERVER={server_name};'
            f'DATABASE={db_name};'
            f'UID={username};'
            f'PWD={password};'
        )
        # create a connection from the connection string
        conn = pyodbc.connect(conn_str)
        logging.info("Connected to the database")
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[1]
        logging.exception(f"The connection failed. SQL state: {sqlstate}")
        return None
    except Exception as e:
        logging.exception(f"An error occurred: {e}")
        return None

def insert_jobinfo_to_database(jobinfo):
    table_name = 'sde.GeoprocessingToolMonitor'
    conn = connect_to_database()
    if conn:
        logging.info("Connected to the database")
        try:
            ''' engine = create_engine('mssql+pyodbc://', creator=lambda: conn)
            inspector = inspect(engine)
            if inspector.has_table(table_name): '''
            sql = f"INSERT INTO {table_name} (jobId, source_directory, archive_directory, archive_timestamp, definition) VALUES (?, ?, ?, ?, ?)"
            try:
                with conn.cursor() as cursor:
                    logging.info(f"Inserting jobinfo into '{table_name}'")
                    try:
                        cursor.execute(sql, (jobinfo['jobId'], jobinfo['source_directory'], jobinfo['archive_directory'], jobinfo['archive_timestamp'], json.dumps(jobinfo['definition'])))
                    except Exception as e:
                        # try without json.dumps
                        cursor.execute(sql, (jobinfo['jobId'], jobinfo['source_directory'], jobinfo['archive_directory'], jobinfo['archive_timestamp'], jobinfo['definition']))
                    conn.commit()
                logging.info(f"Inserted jobinfo into '{table_name}'")
            except Exception as e:
                logging.exception(f"An error occurred while inserting jobinfo into '{table_name}': {e}")
            # else:
            #    logging.error(f"Table '{table_name}' does not exist in the database.")
        except Exception as e:
            logging.exception(f"An error occurred while connecting to the database: {e}")
        finally:
            conn.close()
            logging.info("Connection to the database closed.")

def extract_datetime(datetime_string):
    # # Define the regular expression pattern to match the day of the week and the date and time
    # pattern = r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+ \d+, \d+ \d+:\d+:\d+ [APM]+)'
    # Define the regular expression pattern to match the date and time starting from the month
    # pattern = r'(\w+ \d+, \d+ \d+:\d+:\d+ [APM]+)'
    pattern = r'(\w+ \d+, \d+ \d+:\d+:\d+ [APM]+|\w+ \d+, \d{2} \d+:\d+:\d+ [APM]+)'
    try:
        # Search for the pattern in the string with case-insensitive matching
        match = re.search(pattern, datetime_string, re.IGNORECASE)
        # print(f"match: {match}")
        if match:
            # Extract the date and time string
            date_str = match.group(1)
            # print(f"date_str: {date_str}")
            date_parts = date_str.split()
            # Determine the format of the date and time string
            if len(date_parts[2]) == 2:  # Check if the year is in two-digit format
                if len(date_parts[0]) == 3:  # Check if the month is in abbreviated form
                    date_format = '%b %d, %y %I:%M:%S %p'
                else:
                    date_format = '%B %d, %y %I:%M:%S %p'
            else:
                if len(date_parts[0]) == 3:  # Check if the month is in abbreviated form
                    date_format = '%b %d, %Y %I:%M:%S %p'
                else:
                    date_format = '%B %d, %Y %I:%M:%S %p'
            # print(f"date_format: {date_format}")
            # Convert the string to a datetime object
            # print(datetime.strptime(date_str, date_format))
            return datetime.strptime(date_str, date_format)
        else:
            return datetime.fromisoformat(datetime_string)
    except Exception as e:
        logging.exception(f"An error occurred while extracting datetime: {e}")
        return None

def get_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    result = chardet.detect(raw_data)
    # print(f"Detected encoding for {file_path}: {result['encoding']}")
    return result['encoding']

def read_file_with_fallback(file_path):
    try:
        file_encoding = get_file_encoding(file_path)
        with open(file_path, 'r', encoding=file_encoding) as f:
            return f.read()
    except UnicodeDecodeError as e:
        # print(f"Failed to read {file_path} with encoding {file_encoding}: {e}")
        # Try reading with 'latin-1' as a fallback
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except UnicodeDecodeError as e:
            logging.error(f"Failed to read '{file_path}' with fallback encoding 'latin-1': {e}")
            return ''

def sanitize_filename(filename):
    # Remove invalid characters
    sanitized_filename = ''.join(c for c in filename if c.isalnum())
    return sanitized_filename

def sanitize_string(string_value):
    # Remove invalid characters
    # sanitized_string = string_value.replace('\0', '')
    sanitized_string = ''.join(c for c in string_value if ord(c) < 128 and ord(c) > 0)
    return sanitized_string

def get_base_name(path):
    basename = os.path.basename(path)
    basename = sanitize_filename(basename)
    return basename

def get_file_output_directory(parent_directory, output_directory):
    output_file_directory = output_directory
    try:
        toolname = ''
        toolname_file = os.path.join(parent_directory, 'toolname.dat')
        if os.path.exists(toolname_file):
            toolname = read_file_with_fallback(toolname_file)
            '''
            file_encoding = get_file_encoding(toolname_file)
            with open(toolname_file, 'r', encoding=file_encoding) as f:
                toolname = f.read()
            '''
            if toolname != '' and toolname != None:
                # remove first character from toolname
                toolname = toolname.strip()
                toolname = toolname[1:]
                toolname = sanitize_filename(toolname)
        if toolname == '':
            # get the next directory up from the parent directory
            next_directory_up = os.path.dirname(parent_directory)
            # get the directory name only of the next directory up, not the full path
            toolname = get_base_name(next_directory_up)
            # if _gpserver is in the toolname, remove it
            if '_gpserver' in toolname:
                toolname = toolname.replace('_gpserver', '')
            
        if toolname != '':
            # append toolname to the destination directory
            output_file_directory = os.path.join(output_file_directory, toolname)
        # else:
            # print(f"toolname is empty for {parent_directory}")
        logging.info(f"toolname: {toolname}")
        
        parent_directory_name = get_base_name(parent_directory)
        # append the parent_directory_name to the output_file_directory
        output_file_directory = os.path.join(output_file_directory, parent_directory_name)
        # output_file_directory = sanitize_string(output_file_directory)
    except Exception as e:
        logging.error(f"Error getting output file directory: {e}")
    
    logging.info(f"Output file directory: '{output_file_directory}'")
    
    return output_file_directory

def get_string_from_brackets(input_string, start_char):
    extracted_string = ''
    try:
        # Define the matching closing character
        if start_char == '(':
            close_char = ')'
        elif start_char == '[':
            close_char = ']'
        elif start_char == '{':
            close_char = '}'
        else:
            raise ValueError("Unsupported start character. Use '(', '[', or '{'.")
        
        # Initialize counters and flags
        open_count = 0
        in_double_quotes = False
        start_index = -1
        
        # Iterate through the input_string to find the closing character
        for index, char in enumerate(input_string):
            if char == '"':
                in_double_quotes = not in_double_quotes
                # print(f"index: {index}, char: {char}, in_double_quotes: {in_double_quotes}")
                
            if start_index > -1:
                try:
                    if ord(char) == 0:
                        continue
                except Exception as e:
                    continue
                # print(f"index: {index}, char: {char}, ascii: {ord(char)}")
            
                extracted_string += char
            
            if not in_double_quotes:
                if char == start_char:
                    if open_count == 0:
                        start_index = index
                        extracted_string = char
                    open_count += 1
                elif char == close_char:
                    open_count -= 1
                
                # When the counts match, we found the closing character
                if open_count == 0 and start_index != -1:
                    # print(f"Extracted string: {input_string[start_index:index + 1]}")
                    # print(f"Extracted string: {extracted_string}")
                    return extracted_string # input_string[start_index:index + 1]
    except Exception as e:
        logging.error(f"Error getting string within brackets: {e}")
    
    # If no matching closing character is found
    # print(f"Extracted string: {extracted_string}")
    return extracted_string

def get_xml_value(xml_file, data_tag, parent_tag=None, search_child_tag=None, search_tag_value=None, reverse_search=False):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        # namespaces = {node[0]: node[1] for _, node in ET.iterparse(xml_file, events=['start-ns'])}
        if parent_tag:
            parent_tag = './/' + parent_tag
            parent_elem = root.find(parent_tag)
            if parent_elem is not None:
                elements = reversed(root.findall(parent_tag)) if reverse_search else root.findall(parent_tag)
                for elem in elements:
                    if search_child_tag and search_tag_value:
                        if elem.find(search_child_tag).text == search_tag_value:
                            find_elem = elem.find(data_tag)
                            if find_elem is not None:
                                return find_elem.text
                            else:
                                logging.info(f"Tag '{data_tag}' not found in XML under parent tag '{parent_tag}' with search criteria '{search_child_tag}={search_tag_value}'.")
                                return ''
                    else:
                        find_elem = elem.find(data_tag)
                        if find_elem is not None:
                            return find_elem.text
                        else:
                            logging.info(f"Tag '{data_tag}' not found in XML under parent tag '{parent_tag}'.")
                            return ''
            else:
                logging.info(f"Parent tag '{parent_tag}' not found in XML.")
                return ''
        else:
            if reverse_search:
                data_tag = './/' + data_tag
                for elem in reversed(root.findall(data_tag)):
                    return elem.text
            else:
                elem = root.find(data_tag)
                if elem is not None:
                    return elem.text
    except ET.ParseError as e:
        logging.info(f"Error parsing XML file '{xml_file}': {e}")
    except Exception as e:
        logging.info(f"Error reading XML file '{xml_file}': {e}")
    
    return ''

def search_for_excel_files():
    logging.info("Searching for Excel files in '" + source_directory + "'.")
    for root, dirs, files in os.walk(source_directory):
        for file in files:
            # initialize jobinfo as an empty dictionary
            jobinfo = {}
            output_file_directory = ''
            try:
                if file.lower().endswith('.xlsx') or file.lower().endswith('.xls') or file.lower().endswith('.xlsm'):
                    logging.info("Found Excel file: " + file)
                    source_file = os.path.join(root, file)
                    
                    # get the parent directory of the source_file
                    parent_directory = os.path.dirname(root)
                    
                    output_file_directory = get_file_output_directory(parent_directory, output_directory)
                    if not os.path.exists(output_file_directory):
                        os.makedirs(output_file_directory)
                    '''
                    else:
                        # continue to the next file
                        continue
                    '''
                    
                    output_file = os.path.join(output_file_directory, file)
                    if os.path.exists(output_file):
                        logging.info(f"Skipped '{file}' because it already exists in '{output_file_directory}'")
                        continue
                
                    shutil.copy(source_file, output_file_directory)
                    logging.info(f"Copied '{file}' to '{output_file_directory}'")
                    
                    
                    # if the jobinfo.json file exists in the parent_directory, read the whole file into a python dictionary
                    jobinfo_file = os.path.join(parent_directory, 'jobinfo.json')
                    if os.path.exists(jobinfo_file):
                        logging.info(f"Found '{jobinfo_file}'")
                        # convert the string return from read_file_with_fallback to a python dictionary
                        file_read = read_file_with_fallback(jobinfo_file)
                        if file_read != '':
                            jobinfo = json.loads(file_read)
                    
                    # add jobID to the jobinfo dictionary
                    jobID = get_base_name(parent_directory)
                    jobinfo['jobId'] = jobID
                    jobinfo['source_directory'] = parent_directory
                    jobinfo['archive_directory'] = output_file_directory.replace('\\org-app2\D$', 'D:')
                    jobinfo['archive_timestamp'] = timestamp
                    
                    # search the parent directory for relevant files
                    messages_file = os.path.join(root, 'messages.xml')
                    if os.path.exists(messages_file):
                        shutil.copy(messages_file, output_file_directory)
                        logging.info(f"Copied '{messages_file}' to '{output_file_directory}'")
                        
                        execution_start_descr = get_xml_value(messages_file, 'MessageDesc', parent_tag='GPMessage', search_child_tag='MessageType', search_tag_value='2', reverse_search=False)
                        execution_end_descr = get_xml_value(messages_file, 'MessageDesc', parent_tag='GPMessage', search_child_tag='MessageType', search_tag_value='3', reverse_search=True)

                        jobinfo['execution_start_description'] = execution_start_descr
                        jobinfo['execution_end_description'] = execution_end_descr
                        jobinfo['execution_start_datetime'] = extract_datetime(execution_start_descr)
                        jobinfo['execution_end_datetime'] = extract_datetime(execution_end_descr)
                    
                    definition_file = os.path.join(parent_directory, 'definition.dat')
                    if os.path.exists(definition_file):
                        shutil.copy(definition_file, output_file_directory)
                        logging.info(f"Copied '{definition_file}' to '{output_file_directory}'")
                        
                        definition = ''
                        definition_json_string = ''
                        # read the definition.dat file and get the string between the first set of brackets {
                        definition = read_file_with_fallback(definition_file)
                        if definition != '' and definition != None:
                            definition_json_string = get_string_from_brackets(definition, '{')
                            if definition_json_string != '':
                                try:
                                    # convert the definition_json string to a python dictionary
                                    definition_dict = json.loads(definition_json_string)
                                    # add the definition_dict to the jobinfo dictionary
                                    jobinfo['definition'] = definition_dict
                                    logging.info("Added definition to jobinfo dictionary as a dictionary")
                                except Exception as e:
                                    # add the definition_json_string to the jobinfo dictionary under the key 'definition' as a string
                                    jobinfo['definition'] = definition_json_string
                                    logging.info("Added definition to jobinfo dictionary as a string")
                        if definition_json_string == '':
                            definition = sanitize_string(definition)
                            # print(f"definition: {definition}")
                            if definition != '':
                                # search for GEOGCS[ within the definition string
                                if 'GEOGCS[' in definition:
                                    logging.info("GEOGCS[ found in definition string")
                                    # truncate definition string at the first occurrence of GEOGCS[
                                    trunc_definition = definition[definition.index('GEOGCS['):]
                                    # print(f"trunc_definition: {trunc_definition}")
                                    definition_json_string = get_string_from_brackets(trunc_definition, '[')
                                    if definition_json_string != '':
                                        # remove all spaces from the definition_json string
                                        # definition_json_string = definition_json_string.replace(' ', '')
                                        # add definition_json_string to the jobinfo dictionary under the key 'definition' and the key 'GEOGCS'
                                        jobinfo['definition'] = {'GEOGCS': definition_json_string}
                                    else:
                                        # add definition to the jobinfo dictionary under the key 'definition'
                                        # print('no string found between brackets')
                                        jobinfo['definition'] = definition
                                else:
                                    # add definition to the jobinfo dictionary under the key 'definition'
                                    logging.info("GEOGCS[ not found in definition string")
                                    jobinfo['definition'] = definition
            except Exception as e:
                logging.error(f"Error processing file {file}: {e}")
            
            if jobinfo != {}:
                logging.info(f"jobinfo: {jobinfo}")
                if output_file_directory != '':
                    # add the jobinfo dictionary to a json file in the output directory
                    jobinfo_file = os.path.join(output_file_directory, 'jobinfo.json')
                    with open(jobinfo_file, 'w', encoding='utf-8') as f:
                        json.dump(jobinfo, f, indent=4)
                    logging.info(f"Copied 'jobinfo.json' to '{output_file_directory}'")
                else:
                    logging.error(f"output_file_directory is empty for '{file}'")





# Main execution

init_logging()

# Track errors during execution
errors_found = []

try:
    search_for_excel_files()
except Exception as e:
    error_msg = f"Error during search_for_excel_files: {e}"
    logging.exception(error_msg)
    errors_found.append(error_msg)

# Send email notification if errors were found
if errors_found:
    error_content = "\n\n".join(errors_found)
    subject = "Geoprocessing Tool Monitor - Errors Detected"
    print(f"Sending error notification with {len(errors_found)} error(s)")
    try:
        send_email_using_powerautomate.send_email(
            content=error_content,
            subject=subject,
            filename=f"GeoprocessingToolMonitor_ERRORS_{timestamp}.txt"
        )
        print('Error notification sent via email successfully')
    except Exception as e:
        logging.error(f"Failed to send error notification via email: {e}")

logging.info('Finished Geoprocessing Tool Monitor.')

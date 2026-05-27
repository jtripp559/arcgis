# MonitorArcGISEnterpriseLogs.py
#
# Developer:    Julie Tripp
#
# Date: 06/11/2024
#
# Description:  This script connects to an ArcGIS Enterprise instance and retrieves the logs from the Portal and Server.
#               The logs are filtered by the log level and the age of the log messages.
#               The log messages are written to a CSV file and saved to a specified directory.
#               PowerAutomate looks for the CSV file and sends an email with the log messages as an attachment.
#               The script is intended to be run as a scheduled task to monitor the logs for errors.
#
# Sample env file:
# PORTAL_URL=https://<portal>.com/portal
# PORTAL_USERNAME=<username>
# ORG_ARCGIS_MS_CREDS_NAME=<credential name>
# ARCGIS_LOG_REPORT_LEVEL=SEVERE
# ARCGIS_LOG_REPORT_AGING_MINUTES=5
#

LOGS_FROM_PORTAL = True
LOGS_FROM_SERVER = True
LOGS_FROM_ADMIN = False

import traceback
import logging
import datetime as dt

from datetime import timedelta
from dotenv import load_dotenv
import os
import sys
import importlib
import keyring
import pandas as pd
# import httplib
import http.client as httplib
# import urllib
from urllib.parse import urlencode
import json
from pprint import pprint
# import time
import requests
from xml.etree import ElementTree as ET
from dateutil.parser import parse
import csv

mods = [r'D:\GenericScriptsDir\send_email_using_powerautomate']
for path in mods:
    sys.path.append(path)
# Import send_email_using_powerautomate module with reload capability
module_name = "send_email_using_powerautomate"
if module_name in sys.modules:
    del sys.modules[module_name]
send_email_using_powerautomate = importlib.import_module(module_name)

# initialize variables
EXCEPTION_MESSAGE = ''
TIMESTAMP = dt.datetime.now()
TIMESTAMP_STR = TIMESTAMP.strftime('%Y%m%d_%H%M%S')
MONTH_STR = TIMESTAMP.strftime('%Y%m')

script_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(script_dir, 'Output')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
# Configure logging
log_file_path = os.path.join(OUTPUT_DIR, f'MonitorArcGISEnterpriseLogs_{MONTH_STR}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)

if LOGS_FROM_PORTAL or LOGS_FROM_SERVER:
    try:
        from arcgis.gis import GIS
        # from arcgis.gis.server import Server,LogManager
    except Exception as import_exc:
        error_msg = f"Failed to import arcgis.gis.GIS: {import_exc}\nTraceback: {traceback.format_exc()}"
        logging.error(error_msg)
        try:
            logging.error(error_msg)
        except Exception:
            pass
        # Optionally, set a global EXCEPTION_MESSAGE so the rest of the script can handle this
        EXCEPTION_MESSAGE = error_msg

# Load environment variables from .env file
load_dotenv()
# arcgis_server_manager_url = os.getenv('ARCGIS_SERVER_MANAGER_URL')
ARCGIS_URL = os.getenv('PORTAL_URL')
USERNAME = os.getenv('PORTAL_USERNAME')
MS_CRED_NAME = os.getenv('ORG_ARCGIS_MS_CREDS_NAME')
ARCGIS_LOG_LEVEL = os.getenv('ARCGIS_LOG_REPORT_LEVEL', 'SEVERE')
AGING_MINUTES_ENV = int(os.getenv('ARCGIS_LOG_REPORT_AGING_MINUTES', '5'))
file_directory = r'C:\MS\OneDrive - Example Organization, Inc\SharePoint - ORG - GIS and IT\Programming\Monitoring\ORG ArcGIS Server Logs'
if not os.path.exists(file_directory):
    # if file_directory does not exist, use the Output subfolder in the script folder
    file_directory = OUTPUT_DIR
FILE_NAME = ARCGIS_LOG_LEVEL.lower() + '_logs_' + TIMESTAMP_STR + '.csv'
FILE_PATH = os.path.join(file_directory, FILE_NAME)
LOGMESSAGES_DF = pd.DataFrame(columns=['logSource', 'type', 'time', 'code', 'source', 'process', 'thread', 'methodName', 'machine', 'user', 'elapsed', 'requestID', 'message'])
# aging_minutes = TIMESTAMP - timedelta(minutes=AGING_MINUTES_ENV)
# Convert AGING_MINUTES to milliseconds since epoch
# start_time = int(time.mktime(AGING_MINUTES.timetuple())) * 1000

EXCLUDED_CODES = [30204, 2180343, 204084]
# 30204 - Webhook log: Error in Webhook Processor. init WebhookProcessors failed. FS Webhook processor init failed Connecting to queue : ededb6e9-d7b5-4a79-abac-8ca96f5d0cc8_FS_Raw_Events_Queue failed. Could not create a queue with id : [ededb6e9-d7b5-4a79-abac-8ca96f5d0cc8_FS_Raw_Events_Queue] Connection refused: connect.
# 2180343 - The ArcGIS Enterprise deployment has not been backed up since it was created. Strongly consider backing up the deployment using the WebGIS DR tool available within the tools directory.
# 204084 - Invalid SSL certificate found. PKIX path building failed: sun.security.provider.certpath.SunCertPathBuilderException: unable to find valid certification path to requested target

SCRIPT_LOG_FILE_PATH = os.path.join(OUTPUT_DIR, f'monitor_arcgis_enterprise_logs.log')

logging.info('=' * 80)
logging.info('Starting ArcGIS Enterprise Log Monitor')
logging.info(f'Log level: {ARCGIS_LOG_LEVEL}')
logging.info(f'Aging minutes: {AGING_MINUTES_ENV}')

# Get password from Windows Credential Manager
try:
    logging.info(f'Retrieving credentials for user: {USERNAME}')
    PASSWORD = keyring.get_password(MS_CRED_NAME, USERNAME)
    logging.info('Credentials retrieved successfully')
except Exception as e:
    EXCEPTION_MESSAGE = f'Failed to get password from Windows Credential Manager: {e}'
    EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
    logging.error(EXCEPTION_MESSAGE)

if EXCEPTION_MESSAGE == '':
    if LOGS_FROM_PORTAL or LOGS_FROM_SERVER:
        # Connect to ArcGIS Enterprise
        try:
            logging.info(f'Connecting to ArcGIS Enterprise: {ARCGIS_URL}')
            gis = GIS(ARCGIS_URL, USERNAME, PASSWORD)
            logging.info(f'Connected to ArcGIS Enterprise: {ARCGIS_URL}')
        except Exception as e:
            EXCEPTION_MESSAGE += f'\nFailed to connect to ArcGIS Enterprise: {e}'
            EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
            logging.error(EXCEPTION_MESSAGE)
            
#A function that checks that the input JSON object
#  is not an error object.    
# Based on https://gis.miamigov.com/portal/portalhelp/en/server/latest/administer/windows/example-query-the-arcgis-server-logs.htm
def assertJsonSuccess(data):
    global EXCEPTION_MESSAGE
    obj = json.loads(data)
    if 'status' in obj and obj['status'] == "error":
        EXCEPTION_MESSAGE += "\nError: JSON object returns an error. " + str(obj)
        logging.error(EXCEPTION_MESSAGE)
        return False
    else:
        return True

#A function to generate a token given USERNAME, PASSWORD and the adminURL.
def getToken(): #serverName, serverPort):
    global USERNAME, PASSWORD, EXCEPTION_MESSAGE
    # Token URL is typically http://server[:port]/arcgis/admin/generateToken
    # tokenURL = "/arcgis/admin/generateToken"
    tokenURL = "/arcgisserver/admin/generateToken"
    
    try:
        # URL-encode the token parameters
        # params = urllib.urlencode({'username': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': 'json'})
        params = urlencode({'USERNAME': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': 'json'})
        headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
        
        # Connect to URL and post parameters
        # httpConn = httplib.HTTPConnection(serverName, serverPort)
        httpConn = httplib.HTTPSConnection("gis.example.com")
        httpConn.request("POST", tokenURL, params, headers)
        
        # Read response
        response = httpConn.getresponse()
        if (response.status != 200):
            httpConn.close()
            EXCEPTION_MESSAGE += "\nError while fetching tokens from admin URL. Please check the URL and try again."
            logging.error(EXCEPTION_MESSAGE)
            return
        else:
            data = response.read()
            httpConn.close()
            # Check that data returned is not an error object
            if not assertJsonSuccess(data):            
                return
            # Extract the toke from it
            token = json.loads(data)
            return token['token']
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to get token: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)
        return

def record_last_log_to_file(function_name, function_params={}):
    # print(f'Recording last log for {function_name}')
    log_lines = {}
    # if SCRIPT_LOG_FILE_PATH does exist, read it
    if os.path.exists(SCRIPT_LOG_FILE_PATH):
        try:
            with open(SCRIPT_LOG_FILE_PATH, 'r') as f:
                log_lines = json.load(f)
        except json.JSONDecodeError:
            # If the file is empty or not a valid JSON, initialize log_lines as an empty dictionary
            log_lines = {}
    new_log_json = {'function_params': function_params, 'timestamp': TIMESTAMP_STR}
    
    if function_params == {} or log_lines == {}:
        log_list = [new_log_json]
    else:
        function_list = log_lines.get(function_name, [])
        if function_list == [] or function_list is None:
            log_list = [new_log_json]
        else:
            # look for the function_params in function_list and update the timestamp
            function_params_found = False
            log_list = function_list
            for log in log_list:
                if log['function_params'] == function_params:
                    function_params_found = True
                    log['timestamp'] = TIMESTAMP_STR
            if not function_params_found:
                log_list = function_list + [new_log_json]
    log_lines[function_name] = log_list
    
    # update SCRIPT_LOG_FILE_PATH with updated log_lines
    with open(SCRIPT_LOG_FILE_PATH, 'w') as f:
        json.dump(log_lines, f)

def get_last_log_from_file(function_name, function_params={}):
    if os.path.exists(SCRIPT_LOG_FILE_PATH):
        with open(SCRIPT_LOG_FILE_PATH, 'r') as f:
            try:
                log_lines = json.load(f)
            except Exception as e: # json.JSONDecodeError:
                # If the file is empty or not a valid JSON, initialize log_lines as an empty dictionary
                logging.error(f"Failed to load log lines from file: '{SCRIPT_LOG_FILE_PATH}' e")
                log_lines = {}
        if function_name in log_lines:
            if function_params == {}:
                return log_lines[function_name][0]
            else:
                log_list = log_lines.get(function_name, [])
                for log in log_list:
                    # pprint(log)
                    if log['function_params'] == function_params:
                        return log
    return {}

def get_last_log_time_from_file(function_name, function_params={}):
    last_log = get_last_log_from_file(function_name, function_params)
    last_log_time = TIMESTAMP - timedelta(minutes=AGING_MINUTES_ENV) # AGING_MINUTES
    if 'timestamp' in last_log:
        last_log_time = dt.datetime.strptime(last_log['timestamp'], '%Y%m%d_%H%M%S')
    return last_log_time

#Defines the entry point into the script
def get_logs_from_admin():
    global USERNAME, PASSWORD, EXCEPTION_MESSAGE, LOGMESSAGES_DF
    # print("This tool is a sample script that queries the ArcGIS Server logs.")
    '''
    # Ask for server name
    serverName = raw_input("Enter Server name: ")
    serverPort = 6080

    # Ask for map service name
    mapService = raw_input("Enter map service name, using a forward slash / to denote a folder: ")
    if mapService.endswith(".MapServer"):
        pass
    else:
        mapService += ".MapServer"
    '''
    
    # Get a token
    token = getToken() # USERNAME, PASSWORD, serverName, serverPort)
    if token == "":
        logging.error("Could not generate a token with the username and password provided.")
        return
    
    # Construct URL to query the logs
    # logQueryURL = "/arcgis/admin/logs/query"
    logQueryURL = "/arcgisserver/admin/logs/query"
    # logFilter = "{'services': ['" + mapService + "']}"
    logFilter = {"server": "*"}
    
    # Supply the log level, filter, token, and return format
    # params = urllib.urlencode({'level': 'FINE', 'filter': logFilter, 'token': token, 'f': 'json'})
    # params = urllib.urlencode({'level': 'FINE', 'token': token, 'f': 'json'})
    last_log_time = get_last_log_time_from_file('get_logs_from_admin')
    logging.info(f"Getting logs from admin since {last_log_time}")
    aging_minutes_epoch = int(last_log_time.timestamp()) * 1000
    current_epoch = int(TIMESTAMP.timestamp()) * 1000
    params = urlencode({'endtime': aging_minutes_epoch,
                        'level': 'WARNING', 
                        'filterType': 'json',
                        'filter': logFilter,
                        'token': token, 
                        'f': 'json'})
    
    headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
    
    '''
    # Connect to URL and post parameters    
    # httpConn = httplib.HTTPConnection(serverName, serverPort)
    httpConn = httplib.HTTPConnection("gis.example.com")
    httpConn.request("GET", logQueryURL, params, headers)
    response = httpConn.getresponse()
    response_status = response.status
    '''
    
    logQueryURL = "https://gis.example.com" + logQueryURL
    response = requests.get(logQueryURL, headers=headers, params=params)
    response_status = response.status_code
    
    # Read response
    if (response_status != 200):
        # httpConn.close()
        logging.error("Error while querying logs.", response_status)
        EXCEPTION_MESSAGE += f"\nError while querying logs. {response_status}"
        return
    else:
        # data = response.read()
        data = response.text

        # Check that data returned is not an error object
        if not assertJsonSuccess(data):          
            EXCEPTION_MESSAGE += "\nError returned by operation. " + data
            logging.error(EXCEPTION_MESSAGE)
            return
        # else:
            # logging.info("Operation completed successfully!")
            
        record_last_log_to_file('get_logs_from_admin')

        # Deserialize response into Python object
        dataObj = json.loads(data)
        # httpConn.close()
        
        if dataObj:
            if dataObj.get('logMessages', []) != []:
                admin_logmessages_df = pd.DataFrame(dataObj['logMessages'])
                # add a column called 'logSource' and set it to 'admin' for all rows
                admin_logmessages_df['logSource'] = 'admin'
                LOGMESSAGES_DF = pd.concat([LOGMESSAGES_DF, admin_logmessages_df], ignore_index=True)
        
        '''
        # Need these variables to calculate average draw time for an ExportMapImage call
        mapDraws = 0
        totalDrawTime = 0 
        
        # Iterate over messages        
        for item in dataObj["logMessages"]:
                       
            if item["message"] == "End ExportMapImage":
                print "Server drew map in " + item["elapsed"] + " seconds."
                mapDraws +=1
                totalDrawTime += float(item["elapsed"])

        print "Total number of draws found in logs: " + str(mapDraws)

        if mapDraws == 0:
            return
        
        print "Average draw time: " + str(1.0*(totalDrawTime / mapDraws)) + " seconds."      
        '''
        return

def get_logs_from_portal():
    global LOGMESSAGES_DF, EXCEPTION_MESSAGE
    # Fetch the Portal logs
    try:
        last_log_time = get_last_log_time_from_file('get_logs_from_portal')
        logging.info(f"Getting logs from portal since {last_log_time}")
        logs = gis.admin.logs.query(start_time=last_log_time, level=ARCGIS_LOG_LEVEL)
        record_last_log_to_file('get_logs_from_portal')
        # pprint(logs)
        if logs:
            if logs.get('logMessages', []) != []:
                portal_logmessages_df = pd.DataFrame(logs['logMessages'])
                # add a column called 'logSource' and set it to 'portal' for all rows
                portal_logmessages_df['logSource'] = 'portal'
                logging.info(f"Found {len(portal_logmessages_df)} logs from portal")
                # append portal logs to LOGMESSAGES_DF
                LOGMESSAGES_DF = pd.concat([LOGMESSAGES_DF, portal_logmessages_df], ignore_index=True)
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to query admin logs: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)

def queryLogManager(
    log_manager_url,
    gis_con,
    start_time = None,
    end_time = None,
    since_server_start = False,
    level = "WARNING",
    services = "*",
    machines = "*",
    server = "*",
    codes = None,
    process_IDs = None,
    export = False,
    export_type = "CSV",
    out_path = None,
    max_records_return = 5000):
    # Altered from arcgis\gis\server\admin\_logs.py
    """
    The query operation on the logs resource provides a way to
    aggregate, filter, and page through logs across the entire site.

    ==================     ====================================================================
    **Parameter**           **Description**
    ------------------     --------------------------------------------------------------------
    start_time             Optional Integer or datetime. The most recent time to query.  Default is now.
                            Time can be specified in milliseconds since UNIX epoch.


                            Example for integer:
                            start_time = 1312237040123

    ------------------     --------------------------------------------------------------------
    end_time               Optional String or datetime. The oldest time to include in the result set. You
                            can use this to limit the query to the last n minutes or hours as
                            needed.

                            If ```sinceLastStart``` is true, the default is all logs since the
                            server was started.
    ------------------     --------------------------------------------------------------------
    since_server_start     Optional Bool. Gets only the records written since the server
                            started (True).  The default is False.
    ------------------     --------------------------------------------------------------------
    level                  Optional String. Gets only the records with a log level at or more
                            severe than the level declared here. Can be one of (in severity
                            order): DEBUG, VERBOSE, FINE, INFO, WARNING, SEVERE. The
                            default is WARNING.
    ------------------     --------------------------------------------------------------------
    services               Optional String. Query records related to a specific service.
                            The default is all.
    ------------------     --------------------------------------------------------------------
    machines               Optional String. Query records related to a specific machine.
                            The default is all.
    ------------------     --------------------------------------------------------------------
    server                 Optional String. Query records related to a specific server.
                            The default is all.
    ------------------     --------------------------------------------------------------------
    codes                  Optional String. Gets only the records with the specified code.
                            The default is all.  See http://server.arcgis.com/en/server/latest/administer/windows/log-codes-overview.htm
    ------------------     --------------------------------------------------------------------
    process_IDs            Optional String. Query by the machine process ID that logged the event.
    ------------------     --------------------------------------------------------------------
    export                 Optional String. Boolean indicating whether to export the query
                            results.  The default is False (don't export).
    ------------------     --------------------------------------------------------------------
    export_type            Optional String. The export file type. CSV or TAB are the choices,
                            CSV is the default.
    ------------------     --------------------------------------------------------------------
    out_path               Optional String. The path to download the log file to.
    ------------------     --------------------------------------------------------------------
    max_records_return     Optional Int. The maximum amount of records to return. Default is 5000
    ==================     ====================================================================

    :return:
        A JSON of the log items that match the query. If export option is set to True, the
        output log file path is returned.


    """
    global EXCEPTION_MESSAGE
    logs = {}
    
    try:
        if codes is None:
            codes = []
        if process_IDs is None:
            process_IDs = []
        allowed_levels = ("SEVERE", "WARNING", "INFO", "FINE", "VERBOSE", "DEBUG")
        qFilter = {"services": "*", "machines": "*", "server": "*"}
        if len(process_IDs) > 0:
            qFilter["processIds"] = process_IDs
        if len(codes) > 0:
            qFilter["codes"] = codes
        params = {
            "f": "json",
            "sinceServerStart": since_server_start,
        }
        # set page size
        params["pageSize"] = max_records_return if max_records_return < 5000 else 5000
        # if greater than 5000 then will enter hasMore loop else, correct number returned
        max_records_return -= 5000
        url = "{url}/query".format(url=log_manager_url)
        logging.info(f'LogManager query url: {url}')
        if start_time is not None and isinstance(start_time, dt.datetime):
            params["startTime"] = int(start_time.timestamp() * 1000)
        elif start_time:
            params["startTime"] = start_time
        else:
            params["startTime"] = int(dt.datetime.now().timestamp() * 1000)
        if end_time is not None and isinstance(end_time, dt.datetime):
            params["endTime"] = int(end_time.timestamp() * 1000)
        elif end_time and isinstance(end_time, int):
            params["endTime"] = end_time
        if level.upper() in allowed_levels:
            params["level"] = level
        if server != "*":
            qFilter["server"] = server.split(",")
        if services != "*":
            qFilter["services"] = services.split(",")
        if machines != "*":
            qFilter["machines"] = machines.split(",")
        params["filter"] = qFilter
        # Token param Added by Julie Tripp
        params["token"] = gis_con.token

        logs = gis_con.post(path=url, postdata=params)
        logging.info(f'log key: {logs.keys()}')
        # error log key: dict_keys(['status', 'messages', 'code'])
        # normal log key: dict_keys(['hasMore', 'startTime', 'endTime', 'logMessages'])
        
        # export logs
        if export is True and out_path is not None:
            with open(file=out_path, mode="w") as f:
                if export_type == 'JSON':
                    json.dump(logs, f, indent=4)
                else:
                    hasKeys = False
                    if export_type == "TAB":
                        csvwriter = csv.writer(f, delimiter="\t")
                    else:
                        csvwriter = csv.writer(f)
                    log_messages = logs.get("logMessages", logs.get("messages", []))
                    for message in log_messages:
                        if hasKeys == False:
                            csvwriter.writerow(list(message.keys()))
                            hasKeys = True
                        csvwriter.writerow(list(message.values()))
                        del message
            del logs
            return out_path
        
        log_status = logs.get('status', '')
        if log_status == 'error':
            EXCEPTION_MESSAGE += f'\nError returned by operation: {logs.get("messages", "")}'
            logging.error(EXCEPTION_MESSAGE)
            return logs
        
        # check if logs is empty or not
        if logs is None or logs == {}:
            logging.info("No logs returned.")
            return logs
        
        # determine if more logs are available to query
        # has_more = logs["hasMore"]
        has_more = logs.get("hasMore", False)

        # If the hasMore member of the response object is true,
        # pass the end time as the startTime parameter
        # for the next request to get the next set of records
        loop = 0
        new_logs = {}
        while max_records_return > 1 and has_more:
            if has_more:
                # get new start time from logs endTime in first loop then from new_logs endTime after
                params["startTime"] = (
                    logs["endTime"] if loop == 0 else new_logs["endTime"]
                )
                loop = 1
                # page size is 5000 or less
                params["pageSize"] = (
                    max_records_return if max_records_return < 5000 else 5000
                )
                # decides if more records needed or not
                max_records_return -= 5000
                # new logs to query
                new_logs = gis_con.post(path=url, postdata=params)
                # has_more = new_logs["hasMore"]
                has_more = new_logs.get("hasMore", False)
                # append new log messages to logs to return
                for log_message in new_logs["logMessages"]:
                    logs["logMessages"].append(log_message)
                else:
                    break
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to query logs from LogManager: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)
    
    return logs


def get_logs_from_server():
    global LOGMESSAGES_DF, EXCEPTION_MESSAGE
    # Fetch the Server Logs
    try:
        # Access the ArcGIS Server
        servers = gis.admin.servers
        server = servers.list()[0]
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to access ArcGIS Server: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)
        
    try:
        log_manager_url = server._url + '/logs'
        logging.info(f'LogManager url: {log_manager_url}')
        # gis_con = server._con
        # logging.info(f'gis_con: {gis_con}')
        # server_logs = server._logs
        # log_manager = server.LogManager(url=log_manager_url, gis=gis_con, initialize=False)
        # arcgis_server_manager_url += '/logs'
        # logging.info(arcgis_server_manager_url)
        # log_manager = LogManager(url=arcgis_server_manager_url, gis=gis, initialize=False)
        # log_manager = server.log_manager
        # log_manager = server.logs
        # logging.info('GOT log_manager')
        # log_manager_url = log_manager._url
    
        last_log_time = get_last_log_time_from_file('get_logs_from_server')
        
        thru_datetime = TIMESTAMP
        from_datetime = last_log_time
        retry = True
        retryCount = 0
        while retry:
            logging.info(f"Getting logs from server since {from_datetime} to {thru_datetime}")
            if from_datetime >= TIMESTAMP or retryCount > 90:
                logging.error(f"Breaking out of loop due {str(from_datetime)} >= {str(TIMESTAMP)} or {retryCount} > 90")
                break
            try:
                logs = queryLogManager(
                    log_manager_url=log_manager_url, 
                    gis_con=server._con,
                    start_time=from_datetime, 
                    end_time=thru_datetime, 
                    level=ARCGIS_LOG_LEVEL)
                # logs = log_manager.query(level=ARCGIS_LOG_LEVEL, start_time=thru_datetime, end_time=from_datetime)
                
                # pprint(logs)
                if logs and isinstance(logs, dict):
                    record_last_log_to_file('get_logs_from_server')
                    if logs.get('logMessages', []) != []:
                        serverlogmessages_df = pd.DataFrame(logs['logMessages'])
                        serverlogmessages_df['logSource'] = 'server'
                        # print count of serverlogmessages_df rows
                        logging.info(f"Found {len(serverlogmessages_df)} logs from server since {from_datetime} to {thru_datetime}")
                        # add server logs to LOGMESSAGES_DF
                        LOGMESSAGES_DF = pd.concat([LOGMESSAGES_DF, serverlogmessages_df], ignore_index=True)
                if retryCount == 0:
                    retry = False
                from_datetime += timedelta(days=1)
                thru_datetime = from_datetime + timedelta(days=1)
                retryCount += 1
            except Exception as e:
                # check if error has text 'hasMore' in it
                if 'hasMore' in str(e) and retryCount == 0:
                    retry = True
                    logging.info("Retrying to get logs from server due to error: " + str(e))
                    thru_datetime = from_datetime + timedelta(days=1)
                    retryCount += 1
                else:
                    retry = False
                    EXCEPTION_MESSAGE += f'\nFailed to query server logs: {e}'
                    EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
                    logging.error(EXCEPTION_MESSAGE)
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to connect to server logs: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)

def get_logs_from_log_file(log_folder, log_file_type):
    global LOGMESSAGES_DF, EXCEPTION_MESSAGE
    try:
        # server_log_folder = r'\\org-app2\c$\arcgisserver\logs\ORG-APP2.ORG.CIO\server'
        # check if folder exists
        if os.path.exists(log_folder):
            log_params = {'log_folder': log_folder, 'log_file_type': log_file_type}
            last_log_time = get_last_log_time_from_file('get_logs_from_log_file', log_params)
            record_last_log_to_file('get_logs_from_log_file', log_params)
            logging.info(f"Getting logs from {log_file_type} log folder '{log_folder}' since {last_log_time}")
            # get the latest .log file in the folder
            # log_files = [f for f in os.listdir(log_folder) if f.endswith('.log')]
            log_files = [os.path.join(log_folder, f) for f in os.listdir(log_folder) if f.endswith('.log')]
            if log_files:
                # log_file = os.path.join(log_folder, log_files[0])
                log_file = max(log_files, key=os.path.getmtime)
                # print(f'Getting logs from {log_file}')
                file_mod_time = os.path.getmtime(log_file)
                file_mod_time = dt.datetime.fromtimestamp(file_mod_time)
                logging.info(f'Last {log_file_type} log file: {log_file}, modified time: {file_mod_time}')
                
                # if TIMESTAMP - file_mod_time <= timedelta(minutes=AGING_MINUTES_ENV + 1):
                if file_mod_time >= last_log_time:
                    logging.info(f'Processing log file')
                    file_logmessages_df = pd.DataFrame(columns=['time', 'type', 'code', 'source', 'process', 'thread', 'methodName', 'machine', 'user', 'elapsed', 'requestID', 'message'])
                    
                    with open(log_file, 'r') as f:
                        log_messages = f.readlines()
                    # print(log_messages)
                    message = ''
                    for log_row in reversed(log_messages):
                        log_row = log_row.strip()
                        # print('|' + log_row + '|')
                        start_tag_row = log_row.startswith('<Msg')
                        end_tag_row = log_row.endswith('</Msg>')
                        if start_tag_row: # end_tag_row:
                            # print('Found start tag')
                            message = log_row + ' ' + message
                        else:
                            if end_tag_row: # start_tag_row:
                                message = log_row
                            else:
                                message = log_row + ' ' + message
                            continue
                        message = message.strip()
                        try:
                            msg_xml = ET.fromstring(message)
                            message = ''
                        except ET.ParseError:
                            EXCEPTION_MESSAGE += f'\nFailed to parse message: {message}'
                            logging.error(EXCEPTION_MESSAGE)
                            message = ''
                            continue
                        msg_time = msg_xml.get('time')
                        if msg_time is None:
                            continue
                        msg_time = parse(msg_time)
                        msg_type = msg_xml.get('type', '')
                        # pprint(msg_type)
                        # pprint(msg_time)
                        # pprint(TIMESTAMP)
                        # pprint(TIMESTAMP - msg_time)
                        # pprint(timedelta(minutes=AGING_MINUTES_ENV))
                        # pprint(msg_type)
                        # pprint(msg_type in ['WARNING', 'SEVERE'])
                        # if TIMESTAMP - msg_time <= timedelta(minutes=AGING_MINUTES_ENV):
                        if msg_time >= last_log_time:
                            if msg_type in ['WARNING', 'SEVERE']:
                                # print('Found a log message')
                                # pprint(msg_xml.text)
                                msg_time_str = msg_time.strftime('%Y-%m-%d %H:%M:%S.%f')
                                msg_dict = {
                                    'time': msg_time_str,
                                    'type': msg_type,
                                    'code': msg_xml.get('code'),
                                    'source': msg_xml.get('source'),
                                    'process': msg_xml.get('process'),
                                    'thread': msg_xml.get('thread'),
                                    'methodName': msg_xml.get('methodName'),
                                    'machine': msg_xml.get('machine'),
                                    'user': msg_xml.get('user'),
                                    'elapsed': msg_xml.get('elapsed'),
                                    'requestID': msg_xml.get('requestID'),
                                    'message': msg_xml.text }
                                # pprint(msg_dict)
                                file_logmessages_df = pd.concat([file_logmessages_df, pd.DataFrame(msg_dict, index=[0])], ignore_index=True)
                                file_logmessages_df['logSource'] = f'{log_file_type}_log_file'
                        else:
                            break
                            
                    if file_logmessages_df is not None and not file_logmessages_df.empty:
                        LOGMESSAGES_DF = pd.concat([LOGMESSAGES_DF, file_logmessages_df], ignore_index=True)
    except Exception as e:
        EXCEPTION_MESSAGE += f'\nFailed to get logs from {log_file_type} log file: {e}'
        EXCEPTION_MESSAGE += f'\nTraceback: {traceback.format_exc()}'
        logging.error(EXCEPTION_MESSAGE)

if EXCEPTION_MESSAGE == '':
    if LOGS_FROM_PORTAL:
        logging.info('Fetching logs from Portal...')
        get_logs_from_portal()
    if LOGS_FROM_SERVER:
        logging.info('Fetching logs from Server...')
        get_logs_from_server()
    if LOGS_FROM_ADMIN:
        logging.info('Fetching logs from Admin...')
        get_logs_from_admin()
    logging.info('Fetching logs from log files...')
    get_logs_from_log_file(r'\\org-app2\c$\arcgisserver\logs\ORG-APP2.ORG.CIO\server', 'server')
    get_logs_from_log_file(r'\\org-app2\c$\arcgisdatastore\logs\ORG-APP2.ORG.CIO\server', 'datastore')
    get_logs_from_log_file(r'\\org-app3\c$\arcgisportal\logs\ORG-APP3.ORG.CIO\portal', 'portal')

# pprint(LOGMESSAGES_DF)
try:
    # if time exists in LOGMESSAGES_DF
    if 'time' in LOGMESSAGES_DF.columns:
        # # sort by time descending
        # LOGMESSAGES_DF['time'] = pd.to_datetime(LOGMESSAGES_DF['time'], unit='ms')
        # LOGMESSAGES_DF = LOGMESSAGES_DF.sort_values(by='time', ascending=False)
        
        # change time to a string format '%Y-%m-%d %H:%M:%S.%f'
        LOGMESSAGES_DF['time'] = pd.to_datetime(LOGMESSAGES_DF['time'], unit='ms').dt.strftime('%Y-%m-%d %H:%M:%S.%f')
except Exception as e:
    logging.warning(f'Failed to convert time to datetime: {e}')

if EXCEPTION_MESSAGE != '':
    # add EXCEPTION_MESSAGE to LOGMESSAGES_DF as a new row with type = 'ERROR' and message = EXCEPTION_MESSAGE
    new_row = pd.DataFrame({'type': ['ERROR'], 'message': [EXCEPTION_MESSAGE], 'logSource': ['MonitorArcGISEnterpriseLogs.py']})
    LOGMESSAGES_DF = pd.concat([LOGMESSAGES_DF, new_row], ignore_index=True)

if 'code' in LOGMESSAGES_DF.columns:
    # Replace NaN values in 'code' column with empty string
    LOGMESSAGES_DF['code'] = LOGMESSAGES_DF['code'].fillna('0')
    # remove excluded codes from LOGMESSAGES_DF
    LOGMESSAGES_DF = LOGMESSAGES_DF[~LOGMESSAGES_DF['code'].astype(int).isin(EXCLUDED_CODES)]

# remove records with SpecificToolName.GPServer in the message
LOGMESSAGES_DF = LOGMESSAGES_DF[~LOGMESSAGES_DF['message'].str.contains('SpecificToolName.GPServer')]

if LOGMESSAGES_DF is not None and not LOGMESSAGES_DF.empty:
    # add a newline to the beginning of each message so it will display on a new line
    LOGMESSAGES_DF['message'] = '\n' + LOGMESSAGES_DF['message']
    # remove two newlines in a row from message
    LOGMESSAGES_DF['message'] = LOGMESSAGES_DF['message'].str.replace('\n\n', '\n')
    
    # Convert DataFrame to CSV string
    csv_content = LOGMESSAGES_DF.to_csv(index=False)
    
    # Send log messages via email
    subject = f"ArcGIS Enterprise Log Monitor - {ARCGIS_LOG_LEVEL} Logs"
    logging.info(f"Sending {len(LOGMESSAGES_DF)} log messages via email")
    try:
        send_email_using_powerautomate.send_email(
            content=csv_content,
            subject=subject,
            filename=FILE_NAME
        )
        logging.info('Log messages sent via email successfully')
    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")
        
    with open(FILE_PATH, 'w', encoding='utf-8-sig') as f:
        LOGMESSAGES_DF.to_csv(f, index=False)
    logging.info('Log messages exported to ' + FILE_PATH)
    if EXCEPTION_MESSAGE != '':
        logging.error('Exception Error: ' + EXCEPTION_MESSAGE)
else:
    logging.info('No log messages found.')

logging.info('ArcGIS Enterprise Log Monitor completed')
logging.info('=' * 80)
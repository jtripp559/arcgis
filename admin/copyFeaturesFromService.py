#-------------------------------------------------------------------------------
# Name:        Copy Features from Map/Feature Service Module
# Purpose:
# Adapted by Julie Tripp from the ArcGIS Online Feature Service Extract Tool
# Author:      Jake Skinner, Esri; Patrick McKinney, Cumberland County GIS
#
# Description: Script based upon map service extract tool developed by Jake
#              Skinner from Esri.  Module contains a function for copying data
#              from map/feature services to a feature class.
#              This script is based upon the tool availabled at
#              https://community.esri.com/docs/DOC-6496-download-arcgis-online-feature-service-or-arcgis-server-featuremap-service
#
# Created:     6/14/2017
# Updated:     04/08/2025
#-------------------------------------------------------------------------------

# import modules
import arcpy
import os
import math
import sys
import logging
from datetime import datetime
import requests
import json
# import traceback
# import urllib
# import urllib2

# init logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = os.path.dirname(os.path.realpath(__file__))
log_dir = os.path.join(log_dir, "output")
if not os.path.exists(log_dir):
    os.mkdir(log_dir)
log_file = os.path.join(log_dir, f"CopyFeaturesFromService_{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.DEBUG, format='%(message)s')

def log_message(msg, level='info', print_msg=True):
    if level == 'info':
        logging.info(msg)
    elif level == 'error':
        print_msg = True
        msg = f"ERROR: {msg}"
        logging.error(msg)
    elif level == 'warning':
        msg = f"WARNING: {msg}"
        logging.warning(msg)
    else:
        logging.debug(msg)
    if print_msg:
        print(msg)

def get_json(url, params=None, trans_type='post'):
    '''
    req = urllib2.Request(baseURL, urllib.urlencode(params))
    response = urllib2.urlopen(req)
    data = json.load(response)
    '''
    try:
        log_message(f"Fetching JSON from {url} with params {params}")
        if trans_type == 'post':
            if params:
                response = requests.post(url, params=params)
            else:
                response = requests.post(url)
        else:
            if params:
                response = requests.get(url, params=params)
            else:
                response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Log the error message
        log_message(f"Error fetching JSON from {url} with params {params}: {e}", level='error')
        return None

def get_token(agsServer=False, agolServer=False, baseURL='', tokenUrlPart='', username='', password='', token=''):
    """
        agsServer = set to True if the service is hosted on ArcGIS for Server.
        agolServer = set to True if the service is hostedon ArcGIS Online.
        tokenURLPart = the component of an ArcGIS Server URL for generating tokens. Do not include the preceding '/'.
        You should only need to put in a tokenURLPart variable if using a secured service
        username = the username for a secured service.  Leave blank for unsecured services.
        password = the password for a secured service.  Leave blank for unsecured services.
    """
    if token != '':
        return token

    # if tokenUrlPart == '', use empty string for token
    if tokenUrlPart == '':
        token = ''
    # if tokenUrlPart != '', generate token from token URL
    else:
        # Generate token for service
        log_message('Generating token for service')
        # Generate token for ArcGIS Online hosted service
        if agolServer == True:
            # base token URL
            tokenURL = 'https://www.arcgis.com/sharing/rest/generateToken'
            # parameters for generating token
            params = {'f': 'pjson', 'username': username, 'password': password, 'referer': 'https://www.arcgis.com'}
        # Generate token for ArcGIS Server hosted service
        if agsServer == True:
            server = baseURL.split("//")[1].split("/")[0]
            # URL part for token generation
            tokenURL = 'https://{}/{}'.format(server, tokenUrlPart)
            # parameters for token request
            params = {'username': username, 'password': password, 'client': 'requestip', 'f': 'pjson'}
            
        json_data = get_json(tokenURL, params)
        if json_data:
            token = json_data.get('token', '')
        else:
            token = ''
    return token

def _token_error_code(url):
    """If a /query URL returns an ArcGIS error JSON, return its numeric code (498 = invalid token,
    499 = token required, etc.); otherwise None. Used to decide whether a FeatureSet.load() failure is a
    stale-token case worth refreshing + retrying, rather than a genuine (fatal) error."""
    try:
        data = requests.get(url).json()
    except Exception:
        return None
    err = data.get('error') if isinstance(data, dict) else None
    return err.get('code') if isinstance(err, dict) else None

def _load_featureset(baseURL, where, fields, token, token_provider=None):
    """Build the /query URL for one OID window, load it into a FeatureSet, and return (FeatureSet, token).

    If the load fails because the token is invalid/expired (ArcGIS error 498/499) AND a token_provider
    callable was supplied, mint a fresh token, rebuild the URL, and retry the load ONCE; the (possibly
    refreshed) token is returned so the caller reuses it for the rest of the copy. Any other failure --
    or a failed retry -- raises RuntimeError: the same error recurs for every remaining window, so the
    caller must stop rather than grind through the rest of the OIDs and silently truncate the output."""
    def _build(tok):
        return baseURL + "?where={}&outFields={}&returnGeometry=true&f=json&token={}".format(where, fields, tok)

    fsURL = _build(token)
    log_message('Query URL: {}'.format(fsURL))
    fs = arcpy.FeatureSet()
    try:
        fs.load(fsURL)
        return fs, token
    except Exception as e:
        code = _token_error_code(fsURL)
        # Stale/invalid token -> refresh once and retry THIS window before giving up.
        if code in (498, 499) and token_provider is not None:
            log_message('Token rejected (ArcGIS error {}) -- refreshing token and retrying this window '
                        'once.'.format(code), level='warning')
            new_token = None
            try:
                new_token = token_provider()
            except Exception as te:
                log_message('Token refresh failed: {}'.format(te), level='error')
            if new_token:
                fsURL = _build(new_token)
                log_message('Retry Query URL: {}'.format(fsURL))
                fs = arcpy.FeatureSet()
                try:
                    fs.load(fsURL)
                    log_message('Token refreshed -- window loaded on retry.')
                    return fs, new_token
                except Exception as e2:
                    log_message('Retry after token refresh still failed: {}'.format(e2), level='error')
        # Not a token error, no provider, refresh yielded nothing, or the retry failed -> fatal.
        log_message('Error loading features: {}.'.format(str(e)), level='error')
        raise RuntimeError('Aborting copy -- could not load window ({}) from {}: {}'.format(where, baseURL, e))

# Function to copy features from a map or feature service to a feature class
def copyData(service, featureClass, token, maxRecordCount=1000, OIDFieldName=None, recordCount=None, maxOID=None, minOID=None, token_provider=None):
    """ Function to copy features from a map or feature service to a feature class.
        service = the URL for the map/feature service. You must include the number at the end (/0).
        featureClass = the output location and name of the layer you are copying data to.
        token_provider = optional zero-arg callable returning a FRESH token string. On a long paged copy
            the token can expire mid-run; if a window load is rejected with ArcGIS error 498/499 this is
            called to mint a new token and the window is retried once (see _load_featureset).
    """
    # Adapted by Julie Tripp from the ArcGIS Online Feature Service Extract Tool
    # https://community.esri.com/docs/DOC-6496-download-arcgis-online-feature-service-or-arcgis-server-featuremap-service
    try:
        log_message('Attempting to copy data from {} to {}'.format(service, featureClass))

        from arcpy import env
        # overwite output
        env.overwriteOutput = True
        # scratch workspace
        # http://pro.arcgis.com/en/pro-app/tool-reference/environment-settings/scratch-gdb.htm
        env.workspace = env.scratchGDB
        env.maintainAttachments = True
        env.transferDomains = True
        
        # service url with '/query' appended
        baseURL = r'{}/query'.format(service)

        # Return largest ObjectID
        params = {'where': '1=1', 'returnIdsOnly': 'true', 'token': token, 'f': 'json'}
        data = get_json(baseURL, params)
        if data is None:
            log_message('Failed to retrieve data from service', level='error')
            return
        
        if OIDFieldName is None:
            # Get the ObjectIDs from the service
            objectIDs = data.get('objectIds', [])
            try:
                objectIDs.sort()
            except EnvironmentError as e:
                tbE = sys.exc_info()[2]
                # Write the line number the error occured to the log file
                logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
                logMsg += '\nError: {}'.format(str(e))
                log_message(logMsg, level='error')
            except Exception as e:
                tbE = sys.exc_info()[2]
                # Write the line number the error occured to the log file
                logMsg = '\nFailed at Line %i \n' % tbE.tb_lineno
                logMsg += 'Error: {}'.format(str(e))
                log_message(logMsg, level='error')

            recordCount = len(objectIDs)
            maxOID = int(objectIDs[-1])
            minOID = int(objectIDs[0]) - 1
            OIDFieldName = data['objectIdFieldName']
        log_message('ObjectID field name: {}'.format(OIDFieldName))
        log_message('Number of features: {}'.format(recordCount))
        log_message('Max ObjectID: {}'.format(maxOID))
        log_message('Min ObjectID: {}'.format(minOID + 1))
        
        try:
            # Determine type of workspace for feature class
            log_message('Determining workspace type for {}'.format(os.path.dirname(featureClass)))
            desc = arcpy.Describe(os.path.dirname(featureClass))
            workspaceType = desc.workspaceFactoryProgID
            log_message(f'Workspace type: {workspaceType}')
        except Exception as e:
            log_message(f'Unable to determine workspace type. Error: {e}', level='error')
            workspaceType = None

        # Copy features from service
        if recordCount < maxRecordCount:
            x = maxOID
            y = minOID
            where = OIDFieldName + '>' + str(y) + ' AND ' + OIDFieldName + '<=' + str(x)
            fields ='*'

            # Load the single window (refresh the token + retry once on a 498/499; otherwise fatal).
            fs, token = _load_featureset(baseURL, where, fields, token, token_provider)

            # Copy features
            log_message('Copying features with ObjectIDs from {} to {} of {}'.format(str(y), str(x), str(recordCount)))
            if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                # If the workspace is an SDE workspace, use the feature class name without the path
                featureClass2 = featureClass.split(".")[-1]
            else:
                featureClass2 = os.path.basename(featureClass)
            try:
                arcpy.FeatureClassToFeatureClass_conversion(fs, os.path.dirname(featureClass), featureClass2)
            except EnvironmentError as e:
                tbE = sys.exc_info()[2]
                # Write the line number the error occured to the log file
                logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
                logMsg += '\nError: {}'.format(str(e))
                log_message(logMsg, level='error')
            except Exception as e:
                tbE = sys.exc_info()[2]
                # Write the line number the error occured to the log file
                logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
                logMsg += '\nError: {}'.format(str(e))
                log_message(logMsg, level='error')

        else:
            newIteration = (math.ceil(maxOID/maxRecordCount) * maxRecordCount)
            log_message('Number of features exceeds maxRecordCount. Splitting into {} iterations.'.format(newIteration))
            x = minOID + maxRecordCount
            y = minOID
            firstTime = 'True'

            while y < maxOID:  # stop at the last real OID; avoids an empty trailing window (OID>maxOID)
                where = OIDFieldName + '>' + str(y) + ' AND ' + OIDFieldName + '<=' + str(x)
                fields ='*'

                # Load this OID window. On an expired/invalid token (ArcGIS error 498/499) the token is
                # refreshed via token_provider and the window is retried ONCE; the refreshed token is reused
                # for the rest of the loop. Any other load failure -- or a failed retry -- is FATAL (it
                # recurs for every remaining window): _load_featureset raises, which propagates out of
                # copyData -> the calling step exits non-zero -> the pipeline stops, instead of grinding
                # through the rest of the OIDs and silently truncating the output.
                fs, token = _load_featureset(baseURL, where, fields, token, token_provider)

                # A copy failure on ANY window is FATAL. Inner per-operation handlers used to swallow
                # these, which is how a first-page failure (the target FC never got created) led to
                # "Target Dataset ... does not exist" repeating on every later Append while the loop ran
                # on. Letting the failure reach the single per-window handler below aborts immediately
                # and propagates out of copyData -> the calling step exits non-zero -> the pipeline stops.
                try:
                    log_message('Copying features with ObjectIDs from {} to {} of {}'.format(str(y), str(x), str(recordCount)))
                    if firstTime == 'True':
                        if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                            # If the workspace is an SDE workspace, use the feature class name without the path
                            featureClass2 = featureClass.split(".")[-1]
                        else:
                            featureClass2 = os.path.basename(featureClass)
                        log_message(f'Destination feature class: {featureClass2}')
                        arcpy.FeatureClassToFeatureClass_conversion(fs, os.path.dirname(featureClass), featureClass2)
                        firstTime = 'False'
                    else:
                        if workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory.1' or workspaceType == 'esriDataSourcesGDB.SdeWorkspaceFactory':
                            insertRows = arcpy.da.InsertCursor(featureClass, ["*","SHAPE@"])
                            searchRows = arcpy.da.SearchCursor(fs, ["*","SHAPE@"])
                            for searchRow in searchRows:
                                fieldList = list(searchRow)
                                insertRows.insertRow(fieldList)
                        elif workspaceType == '':
                            arcpy.Append_management(fs, featureClass, "NO_TEST")
                        else:
                            arcpy.Append_management(fs, featureClass)

                except Exception as e:
                    tbE = sys.exc_info()[2]
                    # Write the line number the error occured to the log file
                    logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
                    logMsg += '\nError: {}'.format(str(e))
                    log_message(logMsg, level='error')
                    raise RuntimeError('Aborting copy -- failed copying OID window ({} > {} AND {} <= {}) '
                                       'to {}: {}'.format(OIDFieldName, y, OIDFieldName, x, featureClass, e))
                    

                x += maxRecordCount
                y += maxRecordCount

        try:
            # clean up
            del searchRow, searchRows, insertRows

        except:
            pass

    except EnvironmentError as e:
        tbE = sys.exc_info()[2]
        # Write the line number the error occured to the log file
        logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
        logMsg += '\nError: {}'.format(str(e))
        log_message(logMsg, level='error')
        # Propagate: a copy that died must NOT look like success. Re-raising lets the calling step
        # exit non-zero so run_migration_pipeline stops instead of advancing a half-copied item.
        raise

    except Exception as e:
        tbE = sys.exc_info()[2]
        # Write the line number the error occured to the log file
        logMsg = 'Failed at Line %i \n' % tbE.tb_lineno
        logMsg += '\nError: {}'.format(str(e))
        log_message(logMsg, level='error')
        # Propagate: a copy that died must NOT look like success. Re-raising lets the calling step
        # exit non-zero so run_migration_pipeline stops instead of advancing a half-copied item.
        raise

# copyFeaturesFromService
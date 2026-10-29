# WindowsServicesMonitor.py
#
# Developer:    Julie Tripp
#               julie.tripp@rrgnbs.com
# Date: 06/11/2024
#
# Description:  This script monitors if Windows services are running on remote (and local) servers.
#               Log files are created for any errors encountered.
#               PowerAutomate looks for the error log file and sends an email with the log as an attachment.
#               The script is intended to be run as a scheduled task to monitor the services for errors.
#
# Sample env file:
#   MS_SERVICES_TO_MONITOR={"<server1>": ["<service1>", "<service2>"], "<server2>": ["<service3>", "<service4>"]} # if local server use 'localhost'
#
import subprocess
import os
import sys
import importlib
import datetime
import logging
import time
from dotenv import load_dotenv
import json
# from pprint import pprint

# Import send_email_using_powerautomate module with reload capability
mods = [r'T:\ArcGISDataset\Data Science Scripts\Source Controlled\gis_general\Scripts\ArcGIS Admin\send_email_using_powerautomate']
for path in mods:
    sys.path.append(path)
module_name = "send_email_using_powerautomate"
if module_name in sys.modules:
    del sys.modules[module_name]
send_email_using_powerautomate = importlib.import_module(module_name)

# Load environment variables from .env file
load_dotenv()
services_to_monitor_env = os.getenv('MS_SERVICES_TO_MONITOR', '{}')
auto_restart_services = os.getenv('MS_SERVICES_AUTO_RESTART', 'True').lower() == 'true'

timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
month_str = datetime.datetime.now().strftime('%Y%m')

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, 'Output')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
file_dir = r'C:\MS\OneDrive - RRG Nature Based Solutions, Inc\SharePoint - NBS - GIS and IT\Programming\Monitoring\WindowsServicesMonitor'
if not os.path.exists(file_dir):
    file_dir = output_dir

# Configure logging
log_file = os.path.join(output_dir, f'WindowsServicesMonitor_{month_str}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

def get_local_ips():
    """Get all IP addresses of the local machine."""
    local_ips = set(['localhost', '127.0.0.1', '::1'])
    try:
        # Get hostname and its IPs
        import socket
        hostname = socket.gethostname()
        local_ips.add(hostname.lower())
        
        # Get all IPs associated with hostname
        try:
            host_ips = socket.gethostbyname_ex(hostname)[2]
            local_ips.update(host_ips)
        except socket.gaierror:
            pass
        
        # Also try getaddrinfo for more comprehensive results
        try:
            for info in socket.getaddrinfo(hostname, None):
                ip = info[4][0]
                local_ips.add(ip)
        except socket.gaierror:
            pass
            
        logging.debug(f"Local IPs detected: {local_ips}")
    except Exception as e:
        logging.debug(f"Error getting local IPs: {e}")
    return local_ips

# Cache local IPs at startup
LOCAL_IPS = get_local_ips()

def is_local_server(server_name):
    """Check if the server_name refers to the local machine."""
    if server_name == '':
        return True
    return server_name.lower() in LOCAL_IPS or server_name in LOCAL_IPS

def normalize_server_name(server_name):
    """Convert server_name to '' if it refers to the local machine."""
    if is_local_server(server_name):
        if server_name != '':
            logging.debug(f"Server '{server_name}' is local machine, treating as local")
        return ''
    return server_name

def is_system_shutting_down(server_name=''):
    """Check if the system is shutting down or restarting."""
    try:
        if server_name == '':
            # Local check - look for shutdown.exe process or pending shutdown
            result = subprocess.run(
                ['powershell', '-Command', '(Get-CimInstance -ClassName Win32_OperatingSystem).Status'],
                capture_output=True, text=True, timeout=10
            )
            # Also check for pending reboot
            reboot_check = subprocess.run(
                ['powershell', '-Command', 'Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending"'],
                capture_output=True, text=True, timeout=10
            )
            if 'True' in reboot_check.stdout:
                logging.info("System has a pending reboot.")
                return True
        else:
            # Remote check
            result = subprocess.run(
                ['powershell', '-Command', f'(Get-CimInstance -ComputerName {server_name} -ClassName Win32_OperatingSystem).Status'],
                capture_output=True, text=True, timeout=10
            )
        return False
    except Exception as e:
        logging.debug(f"Could not determine shutdown status: {e}")
        return False

def get_service_state(service_name, server_name=''):
    """
    Get the current state of a service.
    Returns: 'Running', 'Stopped', 'StartPending', 'StopPending', 'ContinuePending', 'PausePending', 'Paused', or 'Unknown'
    """
    try:
        if server_name == '':
            result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True, timeout=10)
            stdout = result.stdout
        else:
            result = subprocess.run(
                ['powershell', '-Command', f'(Get-Service -ComputerName {server_name} -Name "{service_name}").Status'],
                capture_output=True, text=True, timeout=10
            )
            stdout = result.stdout
        
        # Check for transitional states
        if 'START_PENDING' in stdout or 'StartPending' in stdout:
            return 'StartPending'
        elif 'STOP_PENDING' in stdout or 'StopPending' in stdout:
            return 'StopPending'
        elif 'CONTINUE_PENDING' in stdout or 'ContinuePending' in stdout:
            return 'ContinuePending'
        elif 'PAUSE_PENDING' in stdout or 'PausePending' in stdout:
            return 'PausePending'
        elif 'PAUSED' in stdout or 'Paused' in stdout:
            return 'Paused'
        elif 'RUNNING' in stdout or 'Running' in stdout:
            return 'Running'
        elif 'STOPPED' in stdout or 'Stopped' in stdout:
            return 'Stopped'
        else:
            return 'Unknown'
    except Exception as e:
        logging.debug(f"Could not get service state: {e}")
        return 'Unknown'

def can_ping_server(server_name):
    if server_name == '':
        return True
    try:
        # Use the ping command to check if the server is reachable
        result = subprocess.run(['ping', '-n', '1', server_name], stdout=subprocess.DEVNULL)
        # If the return code is 0, the ping was successful
        if result.returncode == 0:
            logging.info(f"Ping to server '{server_name}' successful.")
        else:
            logging.warning(f"Ping to server '{server_name}' failed.")
        return result.returncode == 0
    except Exception as e:
        logging.error(f"An error occurred while trying to ping the server '{server_name}': {e}")
        return False

def get_remote_service_name(display_name, server_name):
    message = ''
    service_name = ''
    try:
        # Get the service name from the display name using wmic on the remote server
        result = subprocess.run(['powershell', f'Get-WmiObject -ComputerName {server_name} -Query "SELECT Name FROM Win32_Service WHERE DisplayName=\'{display_name}\'" | Select-Object -ExpandProperty Name'], capture_output=True, text=True)
        if result.returncode == 0:
            service_name = result.stdout.strip()
            logging.info(f"Remote service name for '{display_name}' on '{server_name}': '{service_name}'")
        if (not service_name) or service_name == '':
            message = f"No Windows service found with display name '{display_name}' on remote server '{server_name}'."
            if result.stderr != '':
                message += f"\n  {result.stderr}"
            if result.stdout:
                message += f"\n  {result.stdout}"
            logging.warning(message)
    except Exception as e:
        message = f"An error occurred while getting the Windows service name for '{display_name}' on remote server '{server_name}': {e}"
        logging.error(message)
    return service_name, message

def get_local_service_name(display_name):
    message = ''
    service_name = ''
    try:
        # Get the service name from the display name using wmic
        result = subprocess.run(['wmic', 'service', 'where', f'DisplayName="{display_name}"', 'get', 'Name'], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                service_name = result.stdout.split('\n\n')[1].strip()
            except Exception:
                service_name = ''
            logging.info(f"Local service name for '{display_name}': '{service_name}'")
        if (not service_name) or service_name == '':
            message = f"No service found with display name '{display_name}'."
            if result.stderr != '':
                message += f"\n  {result.stderr}"
            if result.stdout:
                message += f"\n  {result.stdout}"
            logging.warning(message)
    except Exception as e:
        message = f"An error occurred while getting the Windows service name for '{display_name}': {e}"
        logging.error(message)
    return service_name, message

def get_service_name(display_name, server_name=''):
    if server_name == '':
        return get_local_service_name(display_name)
    else:
        return get_remote_service_name(display_name, server_name)

def is_remote_service_running(service_name, server_name):
    is_running = False
    error_message = ''
    logging.info(f"Checking service '{service_name}' on server '{server_name}'")
    if service_name != '':
        try:
            # Check the status of the service using sc query on the remote server
            result = subprocess.run(['powershell', f'Get-Service -ComputerName {server_name} -Name "{service_name}"'], 
                                    capture_output=True, 
                                    text=True)
            logging.debug(f"result: {result}")
            logging.debug(f"result arguments: {result.args}")
            logging.debug(f"result stdout: {result.stdout}")
            logging.debug(f"result stderr: {result.stderr}")
            logging.debug(f"result returncode: {result.returncode}")
            # Check if the service is running
            if "Running" in result.stdout:
                is_running = True
                logging.info(f"Service '{service_name}' is running on remote server '{server_name}'.")
            else:
                error_message = f"Windows service '{service_name}' is not running on remote server '{server_name}'."
                if result.stdout:
                    error_message += f"\n  {result.stdout}"
                if result.stderr:
                    error_message += f"\n  {result.stderr}"
                logging.warning(error_message)
        except Exception as e:
            error_message += f"\nAn error occurred while checking the status of Windows service '{service_name}' on remote server '{server_name}': {e}"
            logging.error(error_message)
    return is_running, error_message

def is_local_service_running(service_name):
    is_running  = False
    error_message = ''
    if service_name != '':
        try:
            # Check the status of the service using sc query
            result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True)
            # Check if the service is running
            if "RUNNING" in result.stdout:
                is_running = True
                logging.info(f"Service '{service_name}' is running locally.")
            else:
                error_message = f"Windows service '{service_name}' is not running."
                if result.stdout:
                    error_message += f"\n  {result.stdout}"
                if result.stderr:
                    error_message += f"\n  {result.stderr}"
                logging.warning(error_message)
        except Exception as e:
            error_message += f"\nAn error occurred while checking the status of Windows service '{service_name}': {e}"
            logging.error(error_message)
    return is_running, error_message

def restart_remote_service(service_name, server_name):
    """Attempt to restart a service on a remote server."""
    success = False
    message = ''
    try:
        logging.info(f"Attempting to restart service '{service_name}' on remote server '{server_name}'...")
        # Use PowerShell to restart the service remotely
        result = subprocess.run(
            ['powershell', '-Command', f'Restart-Service -InputObject (Get-Service -ComputerName {server_name} -Name "{service_name}") -Force'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        if result.returncode == 0:
            # Verify the service is now running
            time.sleep(15)  # Wait for service to fully start
            is_running, _ = is_remote_service_running(service_name, server_name)
            if is_running:
                success = True
                message = f"Successfully restarted service '{service_name}' on remote server '{server_name}'."
                logging.info(message)
            else:
                message = f"Restart command completed but service '{service_name}' is still not running on '{server_name}'."
                logging.warning(message)
        else:
            message = f"Failed to restart service '{service_name}' on remote server '{server_name}'."
            if result.stderr:
                message += f"\n  {result.stderr}"
            if result.stdout:
                message += f"\n  {result.stdout}"
            logging.error(message)
    except subprocess.TimeoutExpired:
        message = f"Timeout while trying to restart service '{service_name}' on remote server '{server_name}'."
        logging.error(message)
    except Exception as e:
        message = f"An error occurred while restarting service '{service_name}' on remote server '{server_name}': {e}"
        logging.error(message)
    return success, message

def restart_local_service(service_name):
    """Attempt to restart a local service."""
    success = False
    message = ''
    try:
        logging.info(f"Attempting to restart local service '{service_name}'...")
        result = subprocess.run(['sc', 'start', service_name], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 or "RUNNING" in result.stdout:
            time.sleep(15)  # Wait for service to fully start
            is_running, _ = is_local_service_running(service_name)
            if is_running:
                success = True
                message = f"Successfully restarted local service '{service_name}'."
                logging.info(message)
            else:
                message = f"Start command completed but service '{service_name}' is still not running."
                logging.warning(message)
        else:
            message = f"Failed to restart local service '{service_name}'."
            if result.stderr:
                message += f"\n  {result.stderr}"
            if result.stdout:
                message += f"\n  {result.stdout}"
            logging.error(message)
    except subprocess.TimeoutExpired:
        message = f"Timeout while trying to restart local service '{service_name}'."
        logging.error(message)
    except Exception as e:
        message = f"An error occurred while restarting local service '{service_name}': {e}"
        logging.error(message)
    return success, message

def restart_service(service_name, server_name=''):
    """Attempt to restart a service (local or remote)."""
    if server_name == '':
        return restart_local_service(service_name)
    else:
        return restart_remote_service(service_name, server_name)

def is_service_running(service_name, server_name=''):
    if server_name == '':
        return is_local_service_running(service_name)
    else:
        return is_remote_service_running(service_name, server_name)

if services_to_monitor_env != '{}':
    services_to_monitor = json.loads(services_to_monitor_env)
    logging.info(f"Starting Windows Services Monitor for: {services_to_monitor}")
    logging.info(f"Auto-restart enabled: {auto_restart_services}")
    logging.info(f"Local machine IPs: {LOCAL_IPS}")
    
    for server, services in services_to_monitor.items():
        for service in services:
            service = service.strip()
            server_name_raw = server.strip()
            
            # Normalize server name - treat localhost/local IPs as local (empty string)
            if server_name_raw == 'localhost':
                server = ''
            else:
                server = normalize_server_name(server_name_raw)
            
            # Log if we're treating a remote IP as local
            if server == '' and server_name_raw != '' and server_name_raw != 'localhost':
                logging.info(f"Server '{server_name_raw}' is local machine - using local commands")
            
            if can_ping_server(server):
                service_name, error_message = get_service_name(service, server)
                if service_name != '':
                    is_running, error_message = is_service_running(service_name, server)
                
                if error_message != '':
                    # Service is not running - check if we should attempt restart
                    restart_attempted = False
                    restart_success = False
                    restart_message = ''
                    
                    if auto_restart_services:
                        # Check service state - don't restart if in transitional state
                        service_state = get_service_state(service_name, server)
                        logging.info(f"Service '{service_name}' state: {service_state}")
                        
                        if service_state in ('StartPending', 'StopPending', 'ContinuePending', 'PausePending'):
                            restart_message = f"Service is in transitional state ({service_state}). Skipping restart - may be starting up or shutting down intentionally."
                            logging.info(restart_message)
                        elif is_system_shutting_down(server):
                            restart_message = "System appears to be shutting down or has pending reboot. Skipping restart."
                            logging.info(restart_message)
                        else:
                            # Safe to attempt restart
                            restart_attempted = True
                            restart_success, restart_message = restart_service(service_name, server)
                    else:
                        restart_message = "Auto-restart is disabled (MS_SERVICES_AUTO_RESTART=False)."
                        logging.info(restart_message)
                    
                    # Build notification message
                    if restart_attempted and restart_success:
                        subject = f"Windows Service Monitor: {service} - RESTARTED"
                        full_message = f"{error_message}\n\n--- RESTART ATTEMPT ---\n{restart_message}"
                    elif restart_attempted and not restart_success:
                        subject = f"Windows Service Monitor Alert: {service} - RESTART FAILED"
                        full_message = f"{error_message}\n\n--- RESTART ATTEMPT FAILED ---\n{restart_message}"
                    else:
                        subject = f"Windows Service Monitor Alert: {service} - NOT RUNNING"
                        full_message = f"{error_message}\n\n--- RESTART NOT ATTEMPTED ---\n{restart_message}"
                    
                    logging.warning(f"Sending notification for service '{service}' on server '{server}': {full_message}")
                    try:
                        send_email_using_powerautomate.send_email(
                            content=full_message,
                            subject=subject,
                            filename=f"MSService_ERROR_{service.lower()}_{timestamp_str}.txt"
                        )
                        logging.info(f"Email notification sent for service '{service}' on server '{server}'.")
                    except Exception as e:
                        logging.error(f"Failed to send email notification: {e}")
                    error_file_name = f"MSService_ERROR_{service.lower()}_{timestamp_str}.err"
                    with open(os.path.join(file_dir, error_file_name), 'w') as f:
                        f.write(full_message)
                    logging.info(f"Error file written: {os.path.join(file_dir, error_file_name)}")
    logging.info("Windows Services Monitor script completed.")
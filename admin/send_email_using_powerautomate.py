'''
Name: send_email_using_powerautomate.py
Developed by: Julie Tripp
Date: 12/01/2025

Overview: 
    This script sends text or file content to a PowerAutomate REST endpoint 
    to send an email with the content as an attachment.

Workflow:
    1. Retrieves credentials from Windows Credential Manager using the 'keyring' library.
    2. Constructs the PowerAutomate endpoint URL using the retrieved credentials.
    3. Accepts either a text string or a file path (text or CSV) as input.
    4. Reads the content from the file if a file path is provided.
    5. Sends the content to the PowerAutomate endpoint as an email attachment using the 'requests' library.
    6. Prints success or error messages based on the response from the PowerAutomate endpoint.
'''
import os
import sys
import json
import requests
import keyring
import argparse
from pathlib import Path

def get_credentials(credential_name="nbs_powerautomate_gisemail"):
    """
    Retrieve credentials from Windows Credential Manager.
    
    Args:
        credential_name: Name of the credential in Windows Credential Manager
        
    Returns:
        tuple: (username, password)
    """
    try:
        # Get the username - keyring stores it as the 'username' for the service
        username = keyring.get_credential(credential_name, None)
        if username is None:
            raise Exception(f"Credential '{credential_name}' not found in Windows Credential Manager")
        
        # Get the password
        password = keyring.get_password(credential_name, username.username)
        
        return username.username, password
    except Exception as e:
        print(f"Error retrieving credentials: {e}")
        sys.exit(1)

def build_endpoint_url(username, password):
    """
    Build the PowerAutomate endpoint URL with credentials.
    
    Args:
        username: Credential username
        password: Credential password
        
    Returns:
        str: Complete endpoint URL
    """
    base_url = "https://default80c72868a48a4761ad27961aface6e.ef.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows"
    return f"{base_url}/{username}/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig={password}"

def read_file_content(file_path):
    """
    Read content from a file (text or CSV).
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: File content as string
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        sys.exit(1)

def send_to_powerautomate(content, subject=None, filename=None, endpoint_url=None):
    """
    Send content to PowerAutomate REST endpoint.
    
    Args:
        content: String content or file content to send
        subject: Email subject line
        filename: Name for the attachment file
        endpoint_url: PowerAutomate endpoint URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure subject and filename have values (PowerAutomate flow has inverted condition logic)
    if not subject or subject.strip() == '':
        subject = "GIS Notice"
    if not filename or filename.strip() == '':
        filename = "attachment.txt"
    
    payload = {
        "subject": subject,
        "filename": filename,
        "fileContent": content
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print(f"Sending to PowerAutomate endpoint...")
        print(f"Subject: {subject}")
        print(f"Filename: {filename}")
        print(f"Content length: {len(content)} characters")
        
        response = requests.post(endpoint_url, headers=headers, json=payload)
        response.raise_for_status()
        
        print(f"Success! Status code: {response.status_code}")
        if response.text:
            print(f"Response: {response.text}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error sending to PowerAutomate: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response text: {e.response.text}")
        return False

def send_email(content, subject=None, filename=None, credential_name="nbs_powerautomate_gisemail"):
    # Get credentials from Windows Credential Manager
    print(f"Retrieving credentials from Windows Credential Manager: '{credential_name}'")
    username, password = get_credentials(credential_name)
    print(f"Credentials retrieved for user: {username}")
    
    # Build endpoint URL
    endpoint_url = build_endpoint_url(username, password)
    
    # Determine if input is a file or string
    input_path = Path(content)
    if input_path.is_file():
        print(f"Reading from file: {input_path}")
        content = read_file_content(input_path)
        filename = filename or input_path.name
    else:
        print("Using input as text string")
        content = content
        filename = filename or "attachment.txt"
    
    # Send to PowerAutomate
    success = send_to_powerautomate(
        content=content,
        subject=subject,
        filename=filename,
        endpoint_url=endpoint_url
    )
    
    if success:
        print("Operation completed successfully!")
    else:
        print("Operation failed!")

def main():
    '''
    parser = argparse.ArgumentParser(
        description="Send text or file content to PowerAutomate REST endpoint as email attachment"
    )
    parser.add_argument(
        "input",
        help="Either a text string or path to a text/CSV file"
    )
    parser.add_argument(
        "--subject",
        "-s",
        default="File from Python Script",
        help="Email subject line (default: 'File from Python Script')"
    )
    parser.add_argument(
        "--filename",
        "-f",
        help="Name for the attachment file (default: derived from input file or 'attachment.txt')"
    )
    parser.add_argument(
        "--credential",
        "-c",
        default="nbs_powerautomate_gisemail",
        help="Windows Credential Manager credential name (default: 'nbs_powerautomate_gisemail')"
    )
    
    args = parser.parse_args()
    
    send_email(
        content=args.input,
        subject=args.subject,
        filename=args.filename,
        credential_name=args.credential
    )
    '''

if __name__ == "__main__":
    main()
# test_send_email_using_powerautomate.py

import sys
import importlib
import os

# Remove the module from sys.modules if already loaded, then re-import
mods = [r'T:\ArcGISDataset\Data Science Scripts\Source Controlled\gis_general\Scripts\ArcGIS Admin\send_email_using_powerautomate']
for path in mods:
    sys.path.append(path)
module_name = "send_email_using_powerautomate"
if module_name in sys.modules:
    del sys.modules[module_name]
send_email_using_powerautomate = importlib.import_module(module_name)

def test_send_text():
    print("Test: Send simple text string")
    send_email_using_powerautomate.send_email(
        content="This is a test message from the test script.",
        subject="Test Subject - Text",
        filename="test_message.txt"
    )

def test_send_file():
    print("Test: Send file content")
    
    # create sample.csv if it doesn't exist
    sample_file_path = "sample.csv"
    try:
        with open(sample_file_path, 'x') as f:
            f.write("Name,Value\n")
            f.write("Item1,100\n")
            f.write("Item2,200\n")
    except FileExistsError:
        pass  # file already exists, no need to create
    
    send_email_using_powerautomate.send_email(
        content="sample.csv",
        subject="Test Subject - CSV File",
        filename="sample.csv"
    )
    
    # remove the sample file after sending
    os.remove(sample_file_path)

if __name__ == "__main__":
    test_send_text()
    test_send_file()
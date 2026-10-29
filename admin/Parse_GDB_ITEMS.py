import json
import xmltodict

def parse_xml_field(field_value):
    if field_value is None:
        return None
    try:
        return xmltodict.parse(field_value)
    except Exception as e:
        print('')
        print(f"Error parsing XML field")
        print(f"Error {e}")
        print(f"{field_value[:300]}")
        return field_value

# Load the JSON file
with open('Output\RRG_TestEnterprise_GDB_ITEMS.json') as f:
    data = json.load(f)
    
xml_fields = ['Definition', 'Documentation', 'ItemInfo', 'ChildRelationships', 'ParentRelationships']

# Create a new list to store the updated dictionaries
updated_data = []

# Iterate over the list of dictionaries
for item in data:
    for field in xml_fields:
        item[field] = parse_xml_field(item[field])

    # Add the updated dictionary to the new list
    updated_data.append(item)

# Write the updated data back to a JSON file
with open('Output\RRG_TestEnterprise_GDB_ITEMS_parsed.json', 'w') as f:
    json.dump(updated_data, f, indent=4)

print('Done!')
from arcgis.gis import GIS
import logging

gis = GIS("pro")


# Set up logging
logging.basicConfig(level=logging.INFO)

def log_message(message, level='info'):
    print(message)
    if level == 'info':
        logging.info(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)

item_ids = {
    "269bdf5dc50942d89f29686ea07326df": "0154fb5fbb7747f5aaa9d80c5ab52469",
    "26227f880a264557a2396dfd8fb02274": "0181832df4c64b6db4d4b26808975cb0",
    "2d3b2d22486040178a502be0d1fb2d38": "0233333f8486482ebce5f2a135b6250a"}

user_folders = {}

def get_user_folder_title(user, folder_id):
    """
    Get the folder title for a user and folder ID.
    """
    global user_folders
    # print(user)
    # print(folder_id)
    try:
        if user not in user_folders:
            user_folders[user] = {}
            gis_user = gis.users.get(username=user)
            # print(gis_user)
            # print(gis_user.folders)
            for folder in gis_user.folders:
                # print(folder)
                # print(folder['id'])
                # print(folder['title'])
                user_folders[user][folder['id']] = folder['title']
    except Exception as e:
        print (e)
    return user_folders[user].get(folder_id, '')


def change_owner(old_item_id, new_item_id): # item_title, new_owner):
    """
    Change the owner of an ArcGIS Portal/Online item.
    """
    try:
        # get item of old using old_item_id
        old_item = gis.content.get(old_item_id)
        new_item = gis.content.get(new_item_id)
        
        # get the old item's owner
        old_owner = old_item.owner
        old_folder_id = old_item.ownerFolder
        old_folder_name = get_user_folder_title(old_owner, old_folder_id)
        
        # print(f"old_owner: {old_owner}")
        # print(f"old_folder: {old_folder}")
        # print(f"old_folder_name: {old_folder_name}")
        
        # set the new item's owner to the old item's owner
        if new_item.reassign_to(old_owner, target_folder=old_folder_name):
            log_message(f"Ownership of item '{new_item.title}' changed to '{old_owner}' in folder '{old_folder_name}' (old_item_id {old_item_id}; new_item_id {new_item_id})")
        else:
            log_message(f"Failed to change item owner (old_item_id {old_item_id}; new_item_id {new_item_id})", level='error')
        
    except Exception as e:
        log_message(f"Failed to change item owner (old_item_id {old_item_id}; new_item_id {new_item_id}): {e}", level='error')


for old_item_id, new_item_id in item_ids.items():
    change_owner(old_item_id, new_item_id)
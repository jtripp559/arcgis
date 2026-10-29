from arcgis.gis import GIS
import logging
import getpass
import sys

def get_user_input(prompt, default_value='', value_to_check=''):
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    
    try:
        user_input = input(f"{input_prompt}: ")
        user_input = user_input.strip()
        if user_input == '' or user_input is None:
            user_input = default_value
    except EOFError:
        # Handle EOF error by using default value
        print(f"No input detected, using default value: {default_value}")
        user_input = default_value
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
        exit(0)
    
    # log_message(f"{prompt}: {user_input}")
    return user_input


arcgis_url = get_user_input("ArcGIS URL", default_value='https://rrg.maps.arcgis.com')
arcgis_username = get_user_input(f"ArcGIS Username (not SSO) for {arcgis_url}", default_value='rrgadmin')
arcgis_password = getpass.getpass(f"**  ArcGIS Password for {arcgis_username}: ")
try:
    gis = GIS(arcgis_url, arcgis_username, arcgis_password)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)





# --------------------------------------------------------------------
# Set up logging
# --------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)

def log_message(message, level='info'):
    if level == 'info':
        logging.info(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)
        
# --------------------------------------------------------------------
# 2) old->new dictionary with item IDs 
# --------------------------------------------------------------------
# old_new_id_dictionary = {"0f3c283b973f4ba393c8bffd2eb7be84": "b378734dcd6a4521800b53476f4fac4e"}

old_new_id_dictionary = {
    "1abde08c877e4cb8b969d13dcf826392": "b9e4ca7529f44009a219d1315f521cde",
    "53ab43f11cad4f89bd03789651b25dda": "03a8f7259dbe42c490f32f3391b007dd",
    "9e53905bbdfc43dbb63bc98f5e2db7fe": "065354c5f2f6457b99196b046f3a5842",
    "e7432279716640dfb6d9d233f95df3d0": "09d552f7cfd546e4b866d960ef09c8f2",
    "d45a1cd389f44ee99a056ace382d5a32": "11ba59b79c574213a710b21d288d0346",
    "ad11db48ff7d44feaa086261c0cba7f1": "14de341346cc4d00b84517850b2f86d5",
    "9131d715134445d6b58338ff726600d3": "1d1c00dff8a5498f85d18472fc6e11d5",
    "10f28f9ab7c4472dbd60fe0962adf532": "2621e6f4370040629557eba8672a7309",
    "8763cc2d8698431e9e4f86750f2c4270": "2cc6c48ff79a42d3abf94ce6983f215e",
    "240bc71af871484091a98f1344b8b54d": "2d80b788e2844691b5932d93156b8649",
    "77267e1ef80543b78a60fd4e3cc331ee": "2e37e10b4c8c4e54b635f64be41abeec",
    "121e2f825c964e958578e373195a413f": "32d8c2e9ee38490d8714b6823ae16f8d",
    "02f2a20d0f2f4c50bcb73f937ea151e3": "3639f5f0cfa842858a567ba32422c8ea",
    "067040058b3248938c58106589eadf2f": "38228b32db8a457597284a8b69ffa5cc",
    "44c9228f4f9743e89fc4a647b03ae11e": "3cc1e5f344954cdc8ce98c336189227f",
    "7d06f0daadfd4e85ae3fe81214237fb2": "3d08f569218c488a890c90cb9477ae79",
    "9a2c769dcb7446ce9288b54a566b3491": "3fdc0eadefd2456fa67d0684b8b77b2c",
    "063316708080441d9d97f5e30e347d28": "4236490ec00542aebf7bd394d7d5311a",
    "a33e074a2cba4b4a970fe4b2e115bd6a": "43e324fef6ca49c7a897d0535b1d9dce",
    "dbefe02574124da09899fb46438f7c49": "48e70300c4054d98b1a0d328ff83ecb4",
    "246e15ee80234354bf7d077d171a6721": "4bf3b42dd41a43a890264895766cfc5c",
    "3cdcd5d4dd4c4259b9c3ed79ae45b48e": "4d4b442c5fba4d47b4ab94902924f7a7",
    "cfc9d2930ef942cf8e8dcce45b07743a": "50add69672564356bf772e391b0a09d2",
    "9289eb7d5a1b4acaadf94edde8353b70": "5f14f5838e25411c873fabd6300e7e7a",
    "f0d824e1b44c47dcb21bee11edb03532": "64bfb60df074467282896297d1c1b099",
    "d984c8f4583d43f38c14cd83e250efcf": "672905e92f994fa3b806829a93e83ba5",
    "f2fa3ec5c4e8469f98ff162342e7fbc1": "67ccee333bd34ba5bf73667be96b007d",
    "136a4ad5978f4467b3c36bcdc0c01304": "68f5eeafe13a433abb031885441655e8",
    "4e4ff81ba3e84038b7e3d91acebf31b7": "6d523c274cb14d939541e34056754c3b",
    "2965938dd984412ab54ec4d2330a0272": "7008b36f201a471180190b2b8764e1a5",
    "efe2f3ea62ac4aed8c9cdc2df7f7c553": "7013405e8a10453cbc1a4afae6950e9b",
    "dcccf20ef5964c15aebd466fa13dbd41": "7221927075274a158cdc08639f6ec58d",
    "d15a4929e75f4ee59d190e6494c94505": "82c3786c977843d495c73905a99db8bf",
    "87cf0d5e84434b0584c71895d8c79beb": "86938050046342158456fdd580c4fc5d",
    "a00b447e4cbe4ec5bf8b5d1c70bd269d": "991d675c564d46c4beaaf2f855e3a196",
    "a13f2bba79ea41579512d11208d48d0f": "9b1afc5e3159404ea1edd7c9dcdeb252",
    "71fb42c3f6c54d13b70c1eea8c349476": "a85687ebaab6412698a7ab9a5805a04c",
    "c60780e7a17d4f75bc3d7e47330afcef": "ae908269131c4098a4306729ef0d6705",
    "cafe3403bbbf4668911200bdadeb585b": "b4695391932442d992a1cc34ca8b0380",
    "0f567235bfe741c386ad685dfcbdbd84": "b5d849d6af6142d1a15cc840112ab4ce",
    "be3cf1ee1937450f8fd557878368a608": "b7509e905f8a4300b4a0c2ebfbdb2e9b",
    "6c506d8a982f438c9ec12326804756c5": "b77ca60eeaa449118196a8208a92bbe5",
    "a73f66c6e714465db84dd10ae25a4ca5": "b9f4aef344a14208bb5f15a7cded868f",
    "b3e5b2741d1d4bc589d0a96437b087cb": "c3bd00c67c5e49959e57b231cc4b5ef7",
    "c3d49afc25f1410da3af22d550463844": "c50d093e7f1f48129c8686f01cea9ccb",
    "2e43bc1e432045f8a20f7279e523a7aa": "c510130c94014605895941f3fa1a587f",
    "e30739b0dad8454c97b4cbc1b4379852": "c53fd423a04c4130b53e2cfd4141f291",
    "43d728a0cdf54433852eb0e5df19aadf": "c6544a53d3b441be815dddc7e004a2a7",
    "385dc40a976a4a4ca1eb31c2c3f9f247": "c97f21cceba948e49648b5f026c69690",
    "000190c55dfc44d3b7a525c0f4082529": "cf389916b25545898a9c6713eb9cf94e",
    "066b0dbd720947d5ae8120cfbf4211ba": "d04755ef63d2461fb76b6b65022a1d27",
    "64ac33868ca544d2931c6ac6e82d93ed": "d11b4b0bfde44e5f9e94908b6f449976",
    "22bc472f31aa470fab1de806aa23cd74": "d5e62cc5e4bd48f2a1aeb352752bb742",
    "830e6d12dd5645708954245f8fb0052c": "d6e1e89243cc4aa091e3dfa47f94c707",
    "80e2c99e53a74585b69dde8e45c3990c": "daf1076914fa4fb4aa23d1d47ec75c26",
    "57d5bfd89716495f90947490b429e25b": "dba5002e1e7c4aba8abf50096ab9900b",
    "31ec53fca96248c2b891945d77b9994d": "df0c4e0d67d84d85978ac2735613986a",
    "700d5825031144f7acbe14132e366e29": "e2b7b20e115341e5ab5d253e2ac24536",
    "e5deed963c074e78bdbcf10a64ba6998": "e714dee0f65245d6b703206a3791c367",
    "bfc7ea4820fc4d87ab17268ea8a4505a": "ea4a07e763b5474687ea83851078c8fa",
    "eed7723377ac41ffb9c96c21002d28d2": "eecc353cbe284beebb0a92c4bcd73af4",
    "b0752d550d084da8b72d9a3fa0690471": "f080e97c891f461e972ca6f555a77754",
    "f9a28c89a78f4e5cbc69e9622e609fa8": "f1bf025eb6044ac1a0f00497e4df7001",
    "885216734bfc4a1e83bc73ee3e0a1e33": "f52c5cbe075d44dcb71909fdff2148a8",
    "d415d3b4f257430c97102ed706723153": "f8738a0b219a4c5cb17b198b3fade6f5",
    "13e75da4c3c04b8bad30c11aca366df7": "f9916239c8cb41aa8060c1a0b19c3069",
    "481f9ddbeddb4d479712ba43f7548037": "fa05a7a96dac4ceba0420481fa117b94",
    "b6461445e52c4605b069c6e199d40699": "fbef880b68db4b2f9d6724db4de10a5b",
    "c012016c10d8466f8f60d0f3f09ed9d8": "ffc478014e1c4b599c045a14ac25c84e",
    "d8d040db37834d8eb4fe8f6196c4b18f": "66187e7dc4a94f45a33f652247e570ed"}

NBS_Org_Group_ID = 0
GIS_Dev_Group_ID = 0


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

def copy_details(old_item_id, new_item_id):
    # Get details of old item and get a pointer to the new item
    # Copy title, description, tags, keywords, and snippet from old item to new item
    try:
        old_item = gis.content.get(old_item_id)
        new_item = gis.content.get(new_item_id)
        update_dict = {
            "title": f'{old_item.title} - NBS', 
            "snippet": old_item.snippet, 
            "description": old_item.description,
            "tags": old_item.tags
        }
        
        # add tags "by reference" and "stored credentials"
        update_dict["tags"].append("by reference")
        update_dict["tags"].append("stored credentials")
        
        new_item.update(item_properties=update_dict)
        log_message(f"Details copied from old item '{old_item.title}' to new item '{new_item.title}' (new_item_id {new_item_id})")
        
        # update tags of old item to match new item
        old_item.update(item_properties={"tags": new_item.tags})
        log_message(f"Tags updated for old item '{old_item.title}' (old_item_id {old_item_id})")
    except Exception as e:
        log_message(f"Failed to copy details from old item '{old_item_id}' to new item '{new_item_id}': {e}", level='error')

def change_owner(new_item_id, new_owner, new_folder_id): # item_title, new_owner):
    """
    Change the owner of an ArcGIS Portal/Online item.
    """
    try:
        # get item of old using old_item_id
        # old_item = gis.content.get(old_item_id)
        new_item = gis.content.get(new_item_id)
        
        # get the old item's owner
        # old_owner = old_item.owner
        # old_folder_id = old_item.ownerFolder
        new_folder_name = get_user_folder_title(new_owner, new_folder_id)
        
        # print(f"old_owner: {old_owner}")
        # print(f"old_folder: {old_folder}")
        # print(f"old_folder_name: {old_folder_name}")
        
        # set the new item's owner to the old item's owner
        if new_item.reassign_to(new_owner, target_folder=new_folder_name):
            log_message(f"Ownership of item '{new_item.title}' changed to '{new_owner}' in folder '{new_folder_name}' (new_item_id {new_item_id})")
        else:
            log_message(f"Failed to change item owner (new_item_id {new_item_id})", level='error')
        
    except Exception as e:
        log_message(f"Failed to change item owner (new_item_id {new_item_id}): {e}", level='error')




def get_group_id_from_title(group_title):
    """
    Get the group ID from the group title.
    """
    group_id = None
    try:
        group = gis.groups.search(group_title) # query=f'title:"{group_title}"', max_items=1)
        if group:
            group_id = group[0].id
    except Exception as e:
        log_message(f"Failed to get group ID for '{group_title}': {e}", level='error')
    return group_id

# --------------------------------------------------------------------
# 1)  uses new_item_id as the actual item ID
# --------------------------------------------------------------------
def change_item_groups(new_item_id, group_ids, owner, owner_folder_id): # portal_group_names):
    """
    Share an ArcGIS Portal/Online item with specified groups (found by group title).
    
    1) Fetch the *new item* by ID (not by searching title).
    2) For each group *title*, search for that group by title, get its ID,
       then share the *new item* with those group IDs.
    """
    try:
        # 1) Fetch the new item by ID
        new_item = gis.content.get(new_item_id)
        if not new_item:
            log_message(f"No item found with ID '{new_item_id}'.", level='warning')
            return
        
        new_item.unshare(groups=[NBS_Org_Group_ID])
        
        # set the new item's owner to the old item's owner
        folder_name = get_user_folder_title(owner, owner_folder_id)
        if new_item.reassign_to(owner, target_folder=folder_name):
            log_message(f"Ownership of item '{new_item.title}' changed to '{owner}' in folder '{folder_name}' (new_item_id {new_item_id})")
        else:
            log_message(f"Failed to change item owner (new_item_id {new_item_id})", level='error')
        
        # 3) If we have valid group IDs, share the new item with them
        if group_ids:
            new_item.share(groups=group_ids)
            # log_message(f"Item '{new_item.title}' (ID: {new_item.id}) shared with groups: {portal_group_names}.")
            log_message(f"Item '{new_item.title}' (ID: {new_item.id}) shared with groups: {group_ids}.")
        else:
            log_message(f"No valid groups to share for item ID '{new_item_id}'.", level='info')

    except Exception as e:
        log_message(f"Failed to update item groups: {e}", level='error')

# --------------------------------------------------------------------
# 3) A helper function to:
#    - Auth once
#    - For each old->new ID pair:
#        (a) get old item by ID
#        (b) get old group's IDs
#        (c) convert group IDs -> group titles
#        (d) build a comma-separated string
#        (e) call change_item_groups (above) for the new item
# --------------------------------------------------------------------
def copy_old_groups_to_new():
    """
    Loops over old->new dictionary, copying the old items group memberships
    to the new item.
    """
    for old_id, new_id in old_new_id_dictionary.items():
        try:
            # 1) Get the old item by ID
            old_item = gis.content.get(old_id)
            if not old_item:
                log_message(f"Could not find OLD item '{old_id}'.", level='warning')
                continue
            
            # 2) Pull the old item’s group IDs
            shared_info = old_item.shared_with  # e.g. {'groups': [...], 'org': False, 'everyone': False}
            old_group_ids = shared_info.get("groups", [])
            if not old_group_ids:
                log_message(f"Old item '{old_item.title}' (ID: {old_id}) is not shared with any groups.", level='info')
                continue
            
            # old_item.unshare(groups=old_group_ids)
                
            # if NBS_Org_Group_ID not in old_group_ids: add it
            if NBS_Org_Group_ID not in old_group_ids:
                old_group_ids.append(NBS_Org_Group_ID)
            
            old_owner = old_item.owner
            old_folder_id = old_item.ownerFolder
                
            change_item_groups(new_id, old_group_ids, old_owner, old_folder_id)
        except Exception as e:
            log_message(f"Failed copying groups from OLD '{old_id}' to NEW '{new_id}': {e}", level='error')
        break

# --------------------------------------------------------------------
# 4) Finally, run the function to process all items
# --------------------------------------------------------------------
'''
NBS_Org_Group_ID = get_group_id_from_title("RRG Nature Based Solutions Organization (Internal)")
print(f"NBS_Org_Group_ID: {NBS_Org_Group_ID}")

GIS_Dev_Group_ID = get_group_id_from_title("GIS Development")

copy_old_groups_to_new()
'''

for old_id, new_id in old_new_id_dictionary.items():
    copy_details(old_id, new_id)

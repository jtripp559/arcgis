import getpass
import json
import requests
import logging

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


# gis = None

token = None
arcgis_url = get_user_input("ArcGIS URL", default_value='https://rrg.maps.arcgis.com')
arcgis_username = get_user_input(f"ArcGIS Username (not SSO) for {arcgis_url}", default_value='rrgadmin')
arcgis_password = None

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

def get_user_input(prompt, default_value='', value_to_check=''):
    if value_to_check != '' and not value_to_check is None:
        return value_to_check
    input_prompt = prompt
    # if input_prompt does not begin with a tab
    if not input_prompt.startswith('\t'):
        input_prompt = '**  ' + input_prompt
    if default_value != '':
        input_prompt += f" (Press enter to default to '{default_value}')"
    user_input = input(f"{input_prompt}: ")
    user_input = user_input.strip()
    if user_input == '' or user_input is None:
        user_input = default_value
    print(f"{prompt}: {user_input}")
    return user_input

def get_arcgis_token():
    global token, arcgis_url, arcgis_username, arcgis_password
    if token != '' and token is not None:
        return token
    # username = input("Portal Username: ")
    arcgis_username = get_user_input("ArcGIS Username", default_value='rrgadmin', value_to_check=arcgis_username)
    if arcgis_username == '':
        print("Username is required")
        return token
    if arcgis_password is None or arcgis_password == '':
        arcgis_password = getpass.getpass(f"Password for {arcgis_username}: ")
    if arcgis_password == '':
        print("Password is required")
        return token
    url = f"{arcgis_url}/sharing/rest/generateToken"
    data = {
        'username': arcgis_username,
        'password': arcgis_password,
        'referer': arcgis_url,
        'f': 'json'
    }
    try:
        response = requests.post(url, data=data)
        print('response.text:')
        print(response.text)
        if response.status_code == 200:
            token = json.loads(response.text)['token']
        else:
            print(f"Failed to get token: {response.status_code}")
    except Exception as e:
        print(f"Failed to get token: {e}")
    print(token)
    return token

def get_headers():
    token = get_arcgis_token()
    if token == '':
        return {}
    return {"Authorization": f"Bearer {token}"}

def get_json(url):
    # print(url)
    headers = get_headers()
    if headers == {}:
        return None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if response.content.strip():
                return response.json()
            else:
                print(f"Failed to get JSON from {url}: Empty content")
                return None
        else:
            print(f"Failed to get JSON from {url}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Failed to get JSON from {url}: {e}")
        return None

def set_deprecated(item_id):
    headers = get_headers()
    if headers == {}:
        return None
    try:
        url = f"{arcgis_url}/sharing/rest/content/items/{item_id}/setContentStatus"
        
        json_data = {
            "status": "deprecated",
            "f": "json",
            "token": token }
        
        # response = requests.post(url, headers=headers, json=json_data)
        response = requests.post(url, data=json_data)
        if response.status_code == 200:
            # print(response)
            # print(response.text)
            log_message(response.text)
            ''' if response.get('success'):
                print(f"Item '{item_id}' has been successfully updated to deprecated.")
            else:
                print(f"Failed to update the item status: {response}")
            '''
            return response # response.json()
        
        else:
            log_message(f"Failed to post item '{item_id}' JSON to {url}: {response.status_code} - {response.text}", level='error')
            return None
    except Exception as e:
        log_message(f"Failed to post item '{item_id}' JSON to {url}: {e}", level='error')
        return None
    
old_item_id = [
    "269bdf5dc50942d89f29686ea07326df",
    "26227f880a264557a2396dfd8fb02274",
    "2d3b2d22486040178a502be0d1fb2d38",
    "1e4ca7639eb842ccbba3df7458e7ba8b",
    "afb284c43c4a4d4bb59973c3d7b3a4e1",
    "53ab43f11cad4f89bd03789651b25dda",
    "9e53905bbdfc43dbb63bc98f5e2db7fe",
    "a224f035d729492797b21ff284ab29ec",
    "a6cf0052fcca43ff9a0fbaf728d1332f",
    "3f7a656ddf1144b59f5ccedc9ec5372c",
    "e7432279716640dfb6d9d233f95df3d0",
    "e6e784c4ae7a4136b1a3a655d8d4bd34",
    "686345141c6f49e9a47977f19908fe81",
    "1633c800f4e5448bb0142d2488497f05",
    "597325871010444ab939a1900628aa49",
    "f0996005789b41f9aadb580d522f21d5",
    "c1b4ee2629f146979727d50174b19f12",
    "d45a1cd389f44ee99a056ace382d5a32",
    "121fcb484a5543f8bfbb98fb6e3bae85",
    "e10c046063064a4db0fed9e9a79d29c1",
    "2f9a861dd3594c7ca6dd2fa787956e1c",
    "7d4e62a1ae9a4b948f8727911a656edf",
    "ad11db48ff7d44feaa086261c0cba7f1",
    "732ced9700384d58b2db9c10972265ec",
    "078cff3d33a44f63bc196206bccee59e",
    "13935b6b1f8044e3897ac75364ac6cdd",
    "3e6f6600cb3f46bb9ab8cd3619fa45c7",
    "0e9be61e5ce94f35bf21b3f8ee23cf0e",
    "55bc2d75f1b84b38a41810fe0daaf674",
    "9131d715134445d6b58338ff726600d3",
    "c423608ce10848ac97380f6161f3e1fa",
    "68601fcf8c6f42f88bc8fed8cf0ff0a9",
    "e1b0b598d02f4d64aeeeb3d6b3c2b07b",
    "b8a8f439c89248fdb79af6224d3137d4",
    "6a7ecd5bf54f4029960e7c22ed559f7c",
    "85d14d43a27b4150950872e5c370d106",
    "b396da736f5f441688c9e8949e16d97d",
    "983239e69d7444de92eda772b465bd5a",
    "e1d97f3eefb844dfbabfebb95344c391",
    "525772c7cec24da4af06e64a6aa5e030",
    "87d5a00e704948b38b83d58a4ba92e9f",
    "05c889760c1544d7a39fd1691810da86",
    "427e3b0ff5144214a25c9d41d56bc463",
    "993193fb1ba14406a517d7abdcaab23e",
    "10f28f9ab7c4472dbd60fe0962adf532",
    "1e66a558693d44628c98ae7f9d25d498",
    "2e73e2956a8444cfa5d290090fd40271",
    "d71418c5f1e448dcab37efa296cff51a",
    "439528baf058406fb48ebfaacb0f1254",
    "a89bddb64f6549c1a0e1e8e80082f4ca",
    "8763cc2d8698431e9e4f86750f2c4270",
    "36806e3ad8354506875873b02244c0b8",
    "240bc71af871484091a98f1344b8b54d",
    "77267e1ef80543b78a60fd4e3cc331ee",
    "0eca1adacda143348da213e88f1f4d94",
    "09d0280213d34162b7ac02e3714c3dbf",
    "5444a85afac74800a7cd830266340b8c",
    "6e770b7c78b2430b93b1c97738005967",
    "242f36e56e64422d9cb2c4124e61240a",
    "155e8ec34370424e8735cbd70e2e5748",
    "47e7d82f9a1446f28719d479ee3ebfee",
    "121e2f825c964e958578e373195a413f",
    "c4023b3490ad4f0b8e269dba3b3ec5ea",
    "21144d3c7d38419485f07f575709442f",
    "bf65babb85174ede850cf74f8bab78f3",
    "f4881f57a44642ff83a83fd3ea528e6a",
    "2622d0346e264f469d02d3b59212845e",
    "2622d0346e264f469d02d3b59212845e",
    "02f2a20d0f2f4c50bcb73f937ea151e3",
    "1250cb9ba40c4ac8bdb84528ac6f77f7",
    "2c4cd396a3354aa9bdba116f4c2b5ae8",
    "ef8b60a30f6542acb12e5038ba50df70",
    "067040058b3248938c58106589eadf2f",
    "90ca050a9dff4f7bafd9764d1a5d0935",
    "d835f1daecb94b418df0550e758aa86a",
    "68accfe0642642bfbec6c8ff0ab365bd",
    "68874f1033714a37b7749597cd50f7fa",
    "aeb7af29763f4168a58b188b9341e67d",
    "5c98460d06f74ab590e748c0745b523b",
    "44c9228f4f9743e89fc4a647b03ae11e",
    "7d06f0daadfd4e85ae3fe81214237fb2",
    "4a33a4d41a6d435e82d55c4b4b25a7e0",
    "f8b60397a03645378a516c0131069516",
    "dc6b13a9a50d4c2089be6a11599099c8",
    "9a2c769dcb7446ce9288b54a566b3491",
    "db4aba24d1e94f0c8a2d19bddd15a485",
    "315a734f160a4e37bac892037c3f79bf",
    "24ce1051286f46918d99e9ad02d2e417",
    "c725c049be8b493cb73e4ced9c15dd54",
    "063316708080441d9d97f5e30e347d28",
    "29d980364b6b4902bbfb02cb14c917ed",
    "a33e074a2cba4b4a970fe4b2e115bd6a",
    "e16951efc0994d1390561c71b85966cf",
    "69f164798f024c51a4e745062fcbfe99",
    "8e248198e33c41508e4ac191deaed847",
    "c8cf4aa5292c4b07897c9bd883c03316",
    "a6bcb62120a34eb38bdaeb41381659bd",
    "1ba9b49a534e4ca5874c61d3d6e6c325",
    "4191c0a7136b4add8ba5d6e5289a905e",
    "dbefe02574124da09899fb46438f7c49",
    "c0b9e61f40b94789895a36bea6b6f9ce",
    "2fee8e4d6dcd434e8f9e6cca2e0db69b",
    "af8a81ac8fff48c4a5cba8f21745ea0c",
    "aacf384c357e41b990a8db51e3594252",
    "246e15ee80234354bf7d077d171a6721",
    "3cdcd5d4dd4c4259b9c3ed79ae45b48e",
    "d4a9b6288a7944eb840d1739ce837798",
    "16e9beb969b543b782e22427b62d2c45",
    "99fb466c12d14e7985d67be92e8f7726",
    "d0aad3c6e8cf4508a331c3bd692ec7ca",
    "47a9658c71134622a2bb36b5d22de32a",
    "cfc9d2930ef942cf8e8dcce45b07743a",
    "aeb61c414ad049fab27046b4ad161c16",
    "9ac3e0bac3b54b28b13bed76343eb08a",
    "aafb2c81463c4f33b3b2495fe736caf3",
    "9b4cec8670e54a2f915e1ce5352b91cb",
    "946377dc26ca4f499d2389137d381772",
    "2fc2fdd36d954f418d25755833a6875f",
    "e2e6879d75184ca9b114c1425f0f603f",
    "eabb3b18a6ec4994950cd37ad23b2796",
    "ef2391242035473a91a41491877135cb",
    "0152391b86514c39ad8e41c555497edd",
    "4ae1693c78f04f86b98a3ef807b38f42",
    "1c9101694b3242789bfa92a442b6beae",
    "3a9beaa24950469c9a01c25e325a46ff",
    "9289eb7d5a1b4acaadf94edde8353b70",
    "030ae303edf64dc6be8cdb6c4853009e",
    "85f30bfe2b8b4b1b91c1cfdd7abf9335",
    "bbc29a73dd344b75b4611d65df62fd1a",
    "72259c5fde464136818c4fc04730a16d",
    "f0d824e1b44c47dcb21bee11edb03532",
    "d8d040db37834d8eb4fe8f6196c4b18f",
    "0c79439cb1bd4308b2697919a006f3ca",
    "6f3c8839dc604074b98db81893c1738d",
    "d984c8f4583d43f38c14cd83e250efcf",
    "f2fa3ec5c4e8469f98ff162342e7fbc1",
    "136a4ad5978f4467b3c36bcdc0c01304",
    "058563b37f1140c19fad2593f7a20a1c",
    "ab691c914ca34afebe7be554521d17c9",
    "3a80642aba5843caa05538f048ebc2c6",
    "a25047a85df7408db701a0e94291d633",
    "4e4ff81ba3e84038b7e3d91acebf31b7",
    "af01178fa2f24a31a20ec955e505ed16",
    "729b0ef30d7843d9b121c827cdf13194",
    "f2965574ae1e422ea96988b704a1acbe",
    "2965938dd984412ab54ec4d2330a0272",
    "efe2f3ea62ac4aed8c9cdc2df7f7c553",
    "88367b35ee724acca90255c2d986bfe0",
    "21dff93629c2489ab17a7ad2d83ca353",
    "3f7c5453b8474095b73677df9ccc6adb",
    "dcccf20ef5964c15aebd466fa13dbd41",
    "221e73e244ed4c4eb6dedaccb50b268c",
    "50322aaaee464b4b8185bceea266cec4",
    "b838671f73474e0aa8f44b757c846741",
    "fa1d250a69f142d3b2e1ea0d5213b86f",
    "73be9eacfb0347baaf169e040f7e4384",
    "6716610c53b0439796d78ffad5837f59",
    "e21059c937f54c7b929f72e0517dbe30",
    "8c857b067b0a4c1fae772e1732a26bec",
    "7e2096c1316c4654a1ba1d7a9aed8321",
    "2a8e71b51b844708bda3d6489429d48c",
    "9d8cb474eb9b47fea115b3d9ea31b802",
    "262067792db940debf54d5fd3329feff",
    "a505841edb004ba5a834f6de30e909e2",
    "07cc59c1255a4ccaa24992feae166584",
    "6620a332f852483ebac3170460c5bbdb",
    "ceb35cf821504358b179fc89dcf2d6e2",
    "0d7b598dd4874d828cff0912dc5882bc",
    "a2b129d48d594378a8e880128f47dbf5",
    "6b88bc71b8fe4e12acbb8352c459cbcf",
    "08fa8c02c0b841adb028c9db5d770a21",
    "892a591fa943455f851ed1b32dbd6699",
    "d15a4929e75f4ee59d190e6494c94505",
    "b5846681a9134475acca0a25b7ef49b2",
    "0589bacb5ab54333b301331eeb472df7",
    "bb7e906c957a4ce9a3e3ccd62c3d684d",
    "a260d196bd324767bbbb1b0fa5b93c4a",
    "a4722c2681ea4db2816a35833bcf50f4",
    "165326d64ed84afda5b31094a66e9d32",
    "bd67a032162e412da98ae47a17a52e0f",
    "79c1c1ee292e4a7bb9607235fa0b5059",
    "87cf0d5e84434b0584c71895d8c79beb",
    "e11a40802dcc4e5fb4234016876d73b1",
    "69efba93079c482fb36c81f240e8fe97",
    "8ccf1dd7ba0f43f9889db40c584b653a",
    "cc1e97791e4d43be9cf9cc7a31361fbf",
    "f546748615e14b57987ccc6537cbf5be",
    "e0624f5f038847ec981956888a072215",
    "68a1f09a24c64104a40c59fa14b51065",
    "06c0361eebcd4d22963f570b30a8fef7",
    "6ca59a07c08e4d7783f1dfd0b6950cc0",
    "ab574527fb3b4160b7b895d34f4a37ec",
    "99daf36b3520497abaefca35e60ef5a6",
    "074d29ea159e40cbac027b07ede094ba",
    "29afb1c808ab4c9f8671efd43232c690",
    "9eb50f82c1104f1f9d7f2a7519bd18da",
    "02120bef1afb4367a01d559dd185a7d6",
    "ff8750c6e10645b1bdb0f2c526dbf12b",
    "b82b5be4d2754bdd83210a880bf29ffd",
    "4433aca5e8394e6689c35c957e7af57d",
    "a00b447e4cbe4ec5bf8b5d1c70bd269d",
    "73cefb60e3b8410daabaa2d980f3c1be",
    "a13f2bba79ea41579512d11208d48d0f",
    "816dfb099cff4706bb55a4d5bb1f4778",
    "7d2072af5676438eb0bcb144ac4d345d",
    "83540fba444249f4a3028cab8ab10fcd",
    "ce8c12ce97b64cf4bac6617b4dbc6e99",
    "c64f88a0e8b74b9788bb5312aebc2c2a",
    "55e4636f9355458bac50dba0affcb98d",
    "91d6b6e5910f4da883a78c8dd3ed0944",
    "71df0063edce4b25a86d176283d052af",
    "60d6066a9b5942aaa4976a28d439f13d",
    "ccdbf748bd2946cc94bf0fd9b8c77722",
    "ac04737c8a134c359327d0983eaf7d9a",
    "c60780e7a17d4f75bc3d7e47330afcef",
    "68321ff420704a96a65f9c0f66f6aa39",
    "621f5ac826114521a37a52863bd5f45c",
    "0304f444486e4db6b93b550cfc01141b",
    "c8f5cc7ebce646cc99dad00e5de4edb1",
    "ce2a4200e9e0482eb2edf351fc2d4563",
    "0103291b98d14045b43820248b6c1105",
    "e416c5bcd386417c8f90609f32e4ba70",
    "d52dbf29d1d44a86a68776109f45fab5",
    "0f3c283b973f4ba393c8bffd2eb7be84",
    "cafe3403bbbf4668911200bdadeb585b",
    "2d6461339eef4996b820b038f5cd56c8",
    "810eb5ec66fd4c2aacb46e149221dda7",
    "2d9489eb42ad4228a7d88a78f4e0c2e6",
    "0f567235bfe741c386ad685dfcbdbd84",
    "a89767b846e84ece85ab0dd605101ad0",
    "be3cf1ee1937450f8fd557878368a608",
    "6c506d8a982f438c9ec12326804756c5",
    "3488fd6a2c9449aea4b9ed7bcdff6aa2",
    "c32939518d7241d28988fcd7908a51aa",
    "61bba41ef81d46018faa0c4bf163cdd9",
    "1abde08c877e4cb8b969d13dcf826392",
    "a73f66c6e714465db84dd10ae25a4ca5",
    "d066021654134017aafee5814bf02dc6",
    "61d2b09959a548b3abd221e96b4fde51",
    "d6ac75e059bd414ebbfe22bdd96440b2",
    "d53e0de121c643f983c47a9c37658046",
    "5b278e35eb304318a1bbcb6472fcd168",
    "0e381a77be394e3db93cde446743a411",
    "2614e28e5c9542dcbda066e87a1e129b",
    "fcf3f27f757544479b6cdc413877f138",
    "b3e5b2741d1d4bc589d0a96437b087cb",
    "c3d49afc25f1410da3af22d550463844",
    "2e43bc1e432045f8a20f7279e523a7aa",
    "5164a737738b47a0978c86ef4f6d4f3c",
    "e30739b0dad8454c97b4cbc1b4379852",
    "43d728a0cdf54433852eb0e5df19aadf",
    "afb3793180ef454bb278bb11436a3efc",
    "2d4aaeeca3724e629452af7034479b6a",
    "ad1f85ce024d4dab895f825d8a69a426",
    "385dc40a976a4a4ca1eb31c2c3f9f247",
    "b4ceb33f94e942de912195de3102f83b",
    "b81dfa9bfcce484694510532f70587d4",
    "31fd98b9dfb947df8bc9a12c1aef8440",
    "56bfbe9377d641209b9aeb3eb2c14dd5",
    "000190c55dfc44d3b7a525c0f4082529",
    "066b0dbd720947d5ae8120cfbf4211ba",
    "0abfac627df748b28d3b780c44040764",
    "22f5faf63ba142528aab37b41326a990",
    "fc63e7579182471a84baafc5354dec42",
    "64ac33868ca544d2931c6ac6e82d93ed",
    "c94bb69b6ff843d4aeec4d4548864df2",
    "b64d7b246ad041789548af6f1d65c5b1",
    "8e0b236a51364ebdba1ca393e0be53a8",
    "9b279e1e540748afbe7955148d265103",
    "22bc472f31aa470fab1de806aa23cd74",
    "d8068fa6063043f4944a3efa52ebab53",
    "830e6d12dd5645708954245f8fb0052c",
    "b95919018ad34807a41c365c0e6ed1e5",
    "80e2c99e53a74585b69dde8e45c3990c",
    "c75e8ebb8aa6476abc0531ca0652c0fd",
    "57d5bfd89716495f90947490b429e25b",
    "aa4cb28d9d324acc92c27e49c1ab1065",
    "e7fbbc7296164ba9802bd91e43e988ae",
    "f6a1175933a4488abad8b95acf00c79b",
    "31ec53fca96248c2b891945d77b9994d",
    "2523c8a26fab43068181bb8b1b8ad663",
    "6bc94adc0d8a4af4b646b63cfddc438b",
    "700d5825031144f7acbe14132e366e29",
    "53480be695c244c5b3dc4e367becfb31",
    "facf8d4dc96a4e369107499c660b8ef6",
    "20ea9e5ff9c24b649178bb9f734b30c5",
    "ae9280a90bc843f3ba3f99da73fa10a4",
    "11aeb0edcca34ca4a4d39e52ea72196e",
    "4f8516f33bd04171b0533f9373ea2e87",
    "387cf7867ce54fffb5a2646711f71a24",
    "e6f4e3acf8aa4696aabb45e2ba1e371d",
    "e5deed963c074e78bdbcf10a64ba6998",
    "bf03dfc53dd443fe93d3fbf109605f70",
    "302bb600a0df402b824698870acafe32",
    "bfc7ea4820fc4d87ab17268ea8a4505a",
    "0d5488efbd0b4f549d0e99e2f7172daa",
    "da3730e6fa6f4f5abe368c53a195aef2",
    "d2ad20e34cff4058af83e43e6ea5657d",
    "7b257a134a6149edaf2eb4cbb388355a",
    "43537651f347490da0e6b623c7cf7e05",
    "ed8b895a9e55479ba1472450889f8571",
    "7eb005eb47314e90a1fa727c10e4274d",
    "6f8ec78537e748698ca040f2ab50dfd6",
    "eed7723377ac41ffb9c96c21002d28d2",
    "4e43662067e14e43b6b96e76b5445660",
    "e7a5e3defd804fee949a718c53ab3fc2",
    "b0752d550d084da8b72d9a3fa0690471",
    "f9a28c89a78f4e5cbc69e9622e609fa8",
    "dd1c65057e8e4a6a97f84d75026f5907",
    "da200a56433141bc818764104fa072e6",
    "93a20dceea4e4ccfa7cba5c740dd8817",
    "a04597ef1e274981a6b97ada306359b4",
    "885216734bfc4a1e83bc73ee3e0a1e33",
    "d0c01248ef2d485192ab112f6f832144",
    "b6fbb1ee7e4242c1a6be833e0d37e5c3",
    "9db6ca398851402c8a04fac605e2ec65",
    "e4f7f2dadf4c4fbea3ca3cf75e208e15",
    "9dd0311e49b4447aae46b6a86bb4c4cc",
    "d661328987b146b68334767f7d4ebe66",
    "d415d3b4f257430c97102ed706723153",
    "9339a98a3d7b4f6da06b06750b881196",
    "7eb8ab9fc29a450c951dc032b6706eae",
    "13e75da4c3c04b8bad30c11aca366df7",
    "481f9ddbeddb4d479712ba43f7548037",
    "a840025de93e4ce1a899621f3518ba29",
    "c36abda4a84a45b0a0c9be366dc79140",
    "95f291600793461aad72758f44ad6900",
    "c012016c10d8466f8f60d0f3f09ed9d8"
]


for item_id in old_item_id:
    set_deprecated(item_id)
import arcpy
import os
import json
from datetime import datetime
import shutil

toolbox_dir = r"C:\Develop\GIS\geoprocessing_tools"
if not os.path.exists(toolbox_dir):
    # use the script's path as the toolbox directory
    toolbox_dir = os.path.dirname(os.path.abspath(__file__))

def get_dir(obj):
    try:
        all_attrs = dir(obj)
        print(all_attrs)
    except Exception as e:
        print(f"[Error accessing attributes: {str(e)}]")
        return None
        

def list_attributes(obj, name="Object", max_depth=2, current_depth=0, visited=None, collect_attrs=False):
    """
    List all attributes of an object with detailed information.
    Attempts to call methods safely to show their values rather than just <method>.
    
    Parameters:
    ----------
    obj : any
        The object to inspect
    name : str, optional
        Name to display for the object
    max_depth : int, optional
        Maximum recursion depth for nested objects
    current_depth : int, optional
        Current recursion depth (used internally)
    visited : set, optional
        Set of object ids already visited (to prevent infinite recursion)
    collect_attrs : bool, optional
        Whether to collect and return attributes dictionary along with formatted string
        
    Returns:
    -------
    str or tuple
        If collect_attrs=False: Formatted string containing object attributes
        If collect_attrs=True: Tuple of (formatted_string, attributes_dict)
    """
    if visited is None:
        visited = set()
    
    # Dictionary to collect attributes if requested
    attr_dict = {} if collect_attrs else None
    
    try:
        # Check if we've seen this object before to prevent infinite recursion
        obj_id = id(obj)
        if obj_id in visited:
            return (f"{' ' * (current_depth * 2)}[Circular reference to {type(obj).__name__}]", 
                   {"error": "Circular reference"}) if collect_attrs else f"{' ' * (current_depth * 2)}[Circular reference to {type(obj).__name__}]"
        
        visited.add(obj_id)
        
        # Start with object type information
        result = [f"{' ' * (current_depth * 2)}{name} ({type(obj).__name__})"]
        
        # Set basic object type info in attr_dict
        if collect_attrs:
            attr_dict["__type__"] = type(obj).__name__
            attr_dict["__attributes__"] = {}
        
        # If we've reached max depth, don't go deeper
        if current_depth >= max_depth:
            return ("\n".join(result), attr_dict) if collect_attrs else "\n".join(result)
        
        # Get all attributes
        try:
            all_attrs = dir(obj)
            # print(all_attrs)
        except Exception as e:
            result.append(f"{' ' * ((current_depth+1) * 2)}[Error accessing attributes: {str(e)}]")
            if collect_attrs:
                attr_dict["error"] = str(e)
                return "\n".join(result), attr_dict
            return "\n".join(result)
        
        # Filter attributes
        regular_attrs = [attr for attr in all_attrs if not attr.startswith('__')]
        special_attrs = [attr for attr in all_attrs if attr.startswith('__') and attr.endswith('__')]
        
        # List of common zero-argument methods that are safe to call
        safe_methods = [
            # String methods
            'capitalize', 'casefold', 'lower', 'upper', 'strip', 'lstrip', 'rstrip', 
            'swapcase', 'title', 'isupper', 'islower', 'isalpha', 'isdigit', 'isalnum',
            'isspace', 'istitle', 'isprintable', 'isascii', 'isidentifier',
            
            # Collection methods
            'keys', 'values', 'items',
            
            # Display-related methods (likely to contain label information)
            'getLabel', 'getDisplayName', 'getName', 'getTitle', 'getCaption',
            'displayName', 'label', 'name', 'title', 'caption',
            
            # Common object methods
            'get_name', 'get_label', 'get_title', 'get_caption', 'get_display_name',
            'get_description', 'description',
            
            # Methods to avoid calling (may have side effects)
            # 'close', 'delete', 'remove', 'clear', 'update', 'save', 'write', 'commit'
        ]
        
        # Process regular attributes
        if regular_attrs:
            result.append(f"{' ' * ((current_depth+1) * 2)}Regular Attributes:")
            for attr in sorted(regular_attrs):
                try:
                    attr_value = getattr(obj, attr)
                    
                    # Handle different types of attributes
                    if callable(attr_value):
                        # Try to determine if the method can be called safely
                        try:
                            import inspect
                            
                            # Check if the method is in our safe list or has no parameters
                            is_safe_method = attr.lower() in [m.lower() for m in safe_methods]
                            
                            if is_safe_method:
                                try:
                                    # Try to call the method with no args
                                    sig = inspect.signature(attr_value)
                                    
                                    # Only call if all parameters have defaults or no parameters
                                    all_params_have_defaults = all(
                                        p.default != inspect.Parameter.empty 
                                        for p in sig.parameters.values()
                                    )
                                    
                                    if not sig.parameters or all_params_have_defaults:
                                        # Call the method
                                        method_result = attr_value()
                                        
                                        # Format the result
                                        if isinstance(method_result, (str, int, float, bool, type(None))):
                                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}(): {method_result}")
                                        elif hasattr(method_result, '__len__'):
                                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}(): {type(method_result).__name__} with {len(method_result)} items")
                                        else:
                                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}(): {type(method_result).__name__}")
                                    else:
                                        # Provide information about required parameters
                                        required_params = [
                                            p.name for p in sig.parameters.values() 
                                            if p.default == inspect.Parameter.empty
                                        ]
                                        if required_params:
                                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method requiring: {', '.join(required_params)}>")
                                        else:
                                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method with optional parameters>")
                                except Exception as e:
                                    # If any error occurs during inspection or calling
                                    result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method> (error: {str(e)})")
                            else:
                                # Show method signature for methods we don't try to call
                                try:
                                    sig = inspect.signature(attr_value)
                                    result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method {sig}>")
                                except:
                                    result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method>")
                        except:
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method>")
                    else:
                        # For non-callable attributes
                        if isinstance(attr_value, (str, int, float, bool, type(None))):
                            # Basic types - show directly
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {attr_value}")
                        elif hasattr(attr_value, '__len__'):
                            # Collections - show type and length
                            try:
                                result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {type(attr_value).__name__} with {len(attr_value)} items")
                            except:
                                result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {type(attr_value).__name__}")
                        else:
                            # Other objects - show type
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {type(attr_value).__name__}")
                        
                        # Store in attr_dict if collecting
                        if collect_attrs:
                            attr_dict["__attributes__"][attr] = attr_value if isinstance(attr_value, (str, int, float, bool, type(None))) else str(type(attr_value))
                            
                        # Check for name-related attributes that might be display names
                        if any(name_part in attr.lower() for name_part in ['name', 'display', 'label', 'title', 'caption']):
                            result.append(f"{' ' * ((current_depth+2) * 2)}  [Potential display name attribute]")
                            
                            # If it's an object with name-related attributes, recurse
                            if (current_depth + 1 < max_depth and 
                                not isinstance(attr_value, (str, int, float, bool, type(None))) and
                                not attr.startswith('_')):
                                child_call = list_attributes(
                                    attr_value, 
                                    f"{attr}", 
                                    max_depth, 
                                    current_depth + 2,
                                    visited.copy(),
                                    collect_attrs
                                )
                                
                                if collect_attrs:
                                    child_result, child_attrs = child_call
                                    if child_result:
                                        result.append(child_result)
                                    attr_dict["__attributes__"][attr] = child_attrs
                                else:
                                    child_result = child_call
                                    if child_result:
                                        result.append(child_result)
                except Exception as e:
                    error_msg = f"{' ' * ((current_depth+2) * 2)}{attr}: <error: {str(e)}>"
                    result.append(error_msg)
                    if collect_attrs:
                        attr_dict["__attributes__"][attr] = {"error": str(e)}
        
        # Process special attributes
        if special_attrs:
            result.append(f"{' ' * ((current_depth+1) * 2)}Special Attributes:")
            for attr in sorted(special_attrs):
                try:
                    attr_value = getattr(obj, attr)
                    
                    # Special handling for important attributes
                    if attr == '__doc__' and attr_value:
                        doc_lines = attr_value.strip().split('\n')
                        result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {doc_lines[0]}")
                        for line in doc_lines[1:]:
                            result.append(f"{' ' * ((current_depth+3) * 2)}{line}")
                    elif attr == '__class__':
                        result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {attr_value.__name__}")
                    elif attr == '__dict__':
                        if attr_value:
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: Dictionary with {len(attr_value)} items")
                            
                            # Look for display name related entries in __dict__
                            name_related_keys = [
                                key for key in attr_value.keys() 
                                if isinstance(key, str) and any(
                                    name_part in key.lower() 
                                    for name_part in ['name', 'display', 'label', 'title', 'caption', 'esri']
                                )
                            ]
                            
                            for key in sorted(name_related_keys):
                                result.append(f"{' ' * ((current_depth+3) * 2)}{key}: {attr_value[key]}")
                        else:
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: Empty dictionary")
                    elif callable(attr_value):
                        # For callable special attributes
                        if attr in ['__str__', '__repr__']:
                            try:
                                value = attr_value()
                                result.append(f"{' ' * ((current_depth+2) * 2)}{attr}(): {value}")
                            except:
                                result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method>")
                        else:
                            result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: <method>")
                    else:
                        # For other special attributes
                        result.append(f"{' ' * ((current_depth+2) * 2)}{attr}: {attr_value}")
                        if collect_attrs:
                            attr_dict["__special__"] = attr_dict.get("__special__", {})
                            attr_dict["__special__"][attr] = str(attr_value)
                except Exception as e:
                    error_msg = f"{' ' * ((current_depth+2) * 2)}{attr}: <error: {str(e)}>"
                    result.append(error_msg)
                    if collect_attrs:
                        attr_dict["__special__"] = attr_dict.get("__special__", {})
                        attr_dict["__special__"][attr] = {"error": str(e)}
        
        # Return the combined result
        if collect_attrs:
            return "\n".join(result), attr_dict
        return "\n".join(result)
        
    except Exception as e:
        if collect_attrs:
            return f"{' ' * (current_depth * 2)}[Error in list_attributes: {str(e)}]", {"error": str(e)}
        return f"{' ' * (current_depth * 2)}[Error in list_attributes: {str(e)}]"

def get_attributes(tbx_path):
    """
    Get the attributes of a toolbox file and return them as a dictionary.
    
    Parameters:
    -----------
    tbx_path : str
        The path to the toolbox file (.tbx or .atbx)
    
    Returns:
    --------
    dict
        A dictionary containing toolbox information
    """
    # Dictionary to store toolbox information
    toolbox_info = {'path': tbx_path, 'tools': []}

    try:
        # set alias to the toolbox filename less the extension
        # alias = arcpy.Describe(tbx_path).baseName
        filename = os.path.basename(tbx_path)
        # extension = os.path.splitext(filename)[1]
        alias = os.path.splitext(filename)[0]
        print(f"Processing toolbox: {filename}")
        toolbox_info['alias'] = alias
    except Exception as e:
        print(f"Error getting toolbox alias: {str(e)}")
        return toolbox_info
    
    try:
        temp_path = os.path.join(toolbox_dir, f"temp_{filename}")
        shutil.copy2(tbx_path, temp_path)
        tbx_path = temp_path
    except Exception as e:
        temp_path = None
        print(f"Error copying toolbox file: {str(e)}")

    toolbox = arcpy.ImportToolbox(tbx_path, alias)    # load custom toolbox
    # print(list_attributes(toolbox, name=f"toolbox", max_depth=5))

    try:
        # Get a reference to the toolbox module
        tbx_module = getattr(arcpy, alias)
        formatted_module_attrs, module_attrs = list_attributes(tbx_module, name=f"tbx_module", max_depth=5, collect_attrs=True)
        # print(formatted_module_attrs)
        toolbox_info['module_attrs'] = module_attrs
    except Exception as e:
        print(f"Error getting reference to toolbox module: {str(e)}")
        toolbox_info['error'] = f"Error getting reference to toolbox module: {str(e)}"

    # Get toolbox information
    try:
        tbx_info = arcpy.Describe(tbx_path)
        formatted_tbx_describe_attrs, tbx_describe_attrs = list_attributes(tbx_info, name=f"tbx_describe", max_depth=5, collect_attrs=True)
        # print(formatted_tbx_describe_attrs)
        toolbox_info['describe_attrs'] = tbx_describe_attrs
        '''
        print(list_attributes(tbx_info, name=f"tbx_info", max_depth=5))
        print(f"\n##### TOOLBOX INFORMATION #####")
        print(f"Toolbox Name: {tbx_info.name}")
        print(f"Toolbox Type: {tbx_info.dataType}")
        if hasattr(tbx_info, 'modified'):
            print(f"Last Modified: {tbx_info.modified}")
        if hasattr(tbx_info, 'modifiedBy'):
            print(f"Modified By: {tbx_info.modifiedBy}")
        # print(f"Path: {tbx_info.catalogPath}")
        if hasattr(tbx_module, '__pathname__'):
            print(f"Toolbox Path: {tbx_module.__pathname__}")
        '''
        try:
            # print('CHILDREN')
            children_info = []
            for child in tbx_info.children:  # each child is a tool Describe
                formatted_child_attrs, child_attrs = list_attributes(child, name=f"child", max_depth=5, collect_attrs=True)
                # print(formatted_child_attrs)
                
                subchildren_info = []
                for subchild in child.children:  # each child is a tool Describe
                    formatted_subchild_attrs, subchild_attrs = list_attributes(subchild, name=f"subchild", max_depth=5, collect_attrs=True)
                    # print(formatted_subchild_attrs)
                    subchildren_info.append(subchild_attrs)
                
                child_attrs['children'] = subchildren_info
                children_info.append(child_attrs)
            
            toolbox_info['children'] = children_info
        except Exception as e:
            print(f"Error getting toolbox children: {str(e)}")
    except Exception as e:
        print(f"Error getting toolbox info: {str(e)}")
        
        
    # list all tools in that toolbox
    tools = arcpy.ListTools(f"*_{alias}")
    print(f"Script count: {len(tools)}")
    # print(dir(tools))
    # print(list_attributes(tools, name=f"All Tools", max_depth=5))

    for t in tools:
        # Extract the base name without the alias
        base_name = t.split('_')[0]
        formatted_attrs, tool_attrs = list_attributes(t, name=f"Tool '{base_name}'", max_depth=5, collect_attrs=True)
        # print(formatted_attrs)
            
        print(f"\n===== TOOL: {base_name} =====")
        # print(f"Full Tool Name: {t}")
        print(f"Tool Name: {base_name}")
        tool_usage = arcpy.Usage(t)
        tool_usage = tool_usage.replace(f"_{alias}", "")
        print(f"Usage: {tool_usage}")
        # print(f"Label: {t.label}")
        
        # Try to get additional tool info
        tool_info = {'name': base_name, 'full_name': t, 'usage': tool_usage}
        
        try:
            # tool_info = arcpy.GetToolInfo(t)
            # print(f"  Tool Info Type: {type(tool_info)}")
            tool_object = getattr(tbx_module, base_name)
            # print(f"  Tool Object Type: {type(tool_object)}")
            
            formatted_obj_attrs, obj_attrs = list_attributes(tool_object, name=f"Tool getattr '{base_name}'", max_depth=5, collect_attrs=True)
            # print(formatted_obj_attrs)
            
            # Add detailed object attributes to tool_info
            tool_info['detailed_attrs'] = obj_attrs
            
            # tool_info = arcpy.Describe(t)
            # Try to access the tool's documentation string
            if hasattr(tool_object, '__doc__') and tool_object.__doc__:
                doc_string = tool_object.__doc__.strip()
                # print(f"Doc String: {doc_string}")
                tool_info['documentation'] = doc_string
                
            if hasattr(tool_object, '__code__'):
                formatted_code_attrs, code_attrs = list_attributes(getattr(tool_object, '__code__'), name=f"tool_object code: '{base_name}'", max_depth=5, collect_attrs=True)
                # print(formatted_code_attrs)
                tool_info['code_attrs'] = code_attrs
                
            if hasattr(tool_object, '__dir__'):
                formatted_dir_attrs, dir_attrs = list_attributes(getattr(tool_object, '__dir__'), name=f"tool_object dir: '{base_name}'", max_depth=5, collect_attrs=True)
                # print(formatted_dir_attrs)
                tool_info['dir_attrs'] = dir_attrs
                
            if hasattr(tool_object, '__init__'):
                formatted_init_attrs, init_attrs = list_attributes(getattr(tool_object, '__init__'), name=f"tool_object init: '{base_name}'", max_depth=5, collect_attrs=True)
                # print(formatted_init_attrs)
                tool_info['init_attrs'] = init_attrs
                
            '''
            tool_info = arcpy.Describe(tool_object)
            if hasattr(tool_info, 'displayName') and tool_info.displayName:
                print(f"Display Name: {tool_info.displayName}")
            if hasattr(tool_info, 'description') and tool_info.description:
                print(f"Description: {tool_info.description}")
            '''
        except Exception as e:
            print(f"Error getting tool info: {str(e)}")
        
        param_list = []
        try:
            # Get parameter information
            params = arcpy.GetParameterInfo(t)
            print(f"Parameter count: {len(params)}")
            
            for i, param in enumerate(params):
                # print(f"Parameter {i+1}: {param.name}")
                param_info = {'name': param.name}
                
                # Use hasattr to safely check for attributes
                if hasattr(param, 'displayName'):
                    # print(f"  Display Name: {param.displayName}")
                    param_info['displayName'] = param.displayName
                if hasattr(param, 'direction'):
                    # print(f"  Direction: {param.direction}")
                    param_info['direction'] = param.direction
                if hasattr(param, 'parameterType'):
                    # print(f"  Parameter Type: {param.parameterType}")
                    param_info['parameterType'] = param.parameterType
                if hasattr(param, 'type'):
                    # print(f"  Data Type: {param.type}")
                    param_info['type'] = param.type
                # if hasattr(param, 'filter') and param.filter:
                #     print(f"  Filter: {param.filter}")
                if hasattr(param, 'value') and param.value:
                    # print(f"  Default Value: {param.value}")
                    param_info['defaultValue'] = param.value
                    
                param_list.append(param_info)
        except Exception as e:
            print(f"Error getting parameter info: {str(e)}")

        tool_info['parameters'] = param_list
        toolbox_info['tools'].append(tool_info)
    
    if temp_path is not None and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception as e:
            print(f"Error removing temporary toolbox file: '{temp_path}'. ERROR: {str(e)}")

    return toolbox_info

def clean_json_data(data):
    """
    Clean up the JSON data by removing toolbox_dir from paths and sensitive information
    
    Parameters:
    ----------
    data : dict or list
        The data structure to clean
        
    Returns:
    -------
    dict or list
        The cleaned data structure
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            keys_to_skip = ["__code__", "co_filename", "__globals__"]
            if key in keys_to_skip:
                continue

            keys_to_replace_dir = ["path", "__pathname__"]

            # Remove toolbox_dir from path
            if key in keys_to_replace_dir and isinstance(value, str): # and value.startswith(toolbox_dir):
                relative_path = os.path.relpath(value, toolbox_dir)
                result[key] = relative_path
            elif isinstance(value, (dict, list)):
                result[key] = clean_json_data(value)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [clean_json_data(item) for item in data]
    else:
        return data

def write_attributes(tbx_files):
    """Write the toolbox information to a output file"""
    output_path = os.path.join(toolbox_dir, "toolbox_attributes.txt")
    
    # Clean and write the full attribute dictionary to a JSON file for further processing
    try:
        cleaned_data = clean_json_data(tbx_files)
        with open(os.path.join(os.path.dirname(output_path), "toolbox_attributes.json"), 'w') as json_file:
            json.dump(cleaned_data, json_file, indent=2, default=str)
    except Exception as e:
        print(f"Error writing JSON file: {e}")
        
    with open(output_path, 'w') as f:
        f.write("# ArcGIS Toolbox Documentation\n")
        # f.write(f"Path: {toolbox_dir}\n")
        # f.write(f"Generated on: {arcpy.GetDateTime()}\n\n")
        f.write(f"Generated on: {datetime.now().isoformat()}\n\n")

        
        for tbx in tbx_files:
            f.write("######################################################\n")
            toolbox_name = os.path.basename(tbx['path'])
            f.write(f"## {toolbox_name}\n")
            # f.write(f"Path: {tbx['path']}\n")
            
            if 'error' in tbx:
                f.write(f"Error: {tbx['error']}\n\n")
                continue
                
            # f.write(f"Alias: {tbx.get('alias', 'N/A')}\n")
            f.write(f"Number of tools: {len(tbx.get('tools', []))}\n\n")
            
            for tool in tbx.get('tools', []):
                f.write("\n### -----------------------------------------------\n")
                f.write(f"### Toolbox: {toolbox_name}\n")
                f.write(f"### Tool: {tool['name']}\n")
                # f.write(f"Alias: {tool['full_name']}\n")
                f.write(f"Usage: {tool.get('usage', 'N/A')}\n")
                
                # if 'documentation' in tool:
                #     f.write(f"Documentation: {tool['documentation']}\n")
                params = tool.get('parameters', [])
                params_count = len(params)
                f.write(f"#### Parameters Count: {params_count}\n")
                param_no = 0
                for param in params:
                    param_no += 1
                    f.write(f"{param_no}) {param.get('displayName', param['name'])}\n")
                    # f.write(f"  - Name: {param['name']}\n")
                    if 'type' in param:
                        f.write(f"  - Data Type: {param['type']}\n")
                    if 'direction' in param:
                        f.write(f"  - Direction: {param['direction']}\n")
                    if 'parameterType' in param:
                        f.write(f"  - Parameter Type: {param['parameterType']}\n")
                    if 'defaultValue' in param:
                        f.write(f"  - Default Value: {param['defaultValue']}\n")
                
                f.write("\n")
            
            f.write("\n")
    
    print(f"Documentation written to {output_path}")

tbx_files = []
for root, dirs, files in os.walk(toolbox_dir):
    for filename in files:
        if filename.endswith(".tbx") or filename.endswith(".atbx"):
            tbx_path = os.path.join(root, filename)
            toolbox_info = get_attributes(tbx_path)
            tbx_files.append(toolbox_info)

# Write the documentation to the output file
write_attributes(tbx_files)
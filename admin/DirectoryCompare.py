# DirectoryCompare.py
#
# Created by: Julie Tripp
#               julie.tripp@rrgnbs.com
#               03/13/2024
# Description: This script compares two directories and writes the differences to a file.
#
# Usage: python DirectoryCompare.py <dir1> <dir2>
# Example: python DirectoryCompare.py C:\Users\user1\Documents\dir1 C:\Users\user1\Documents\dir2
#
import os
import filecmp
import datetime
import sys
import difflib

def get_base_name(full_path):
    if os.path.isfile(full_path):
        return os.path.basename(full_path)
    else:
        return os.path.basename(os.path.normpath(full_path))

if len(sys.argv) >= 3:
    dir1 = sys.argv[1]
    dir2 = sys.argv[2]
else:
    dir1 = input("Enter the path to the first directory: ")
    dir2 = input("Enter the path to the second directory: ")

if not os.path.exists(dir1):
    print(f"Directory '{dir1}' does not exist")
    exit()
if not os.path.exists(dir2):
    print(f"Directory '{dir2}' does not exist")
    exit()
dir1_short = get_base_name(dir1)
dir2_short = get_base_name(dir2)

# Get the current timestamp
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# Set output_dir to the same directory that the script is located in
output_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(output_dir, 'Output')
output_dir = os.path.join(output_dir, f'diffcompare_{timestamp}')
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Specify the path to the output file
output_file = os.path.join(output_dir, f'compare___{dir1_short}___to___{dir2_short}.txt')

def replace_dir_name(str, replace_value='.'):
    return_str = str
    if replace_value == '.':
        replace_value1 = replace_value
        replace_value2 = replace_value
    else:
        replace_value1 = dir1_short
        replace_value2 = dir2_short
    return_str = return_str.replace(dir1, replace_value1)
    return_str = return_str.replace(dir2, replace_value2)
    return return_str

# Create a function to write to both stdout and the file
def print_to_file(*args, file_path=output_file, **kwargs):
    # Redirect print statements to the output file
    for arg in args:
        # print(arg, **kwargs)
        #with open(file_path, 'a') as f:
        with open(file_path, 'a', encoding='utf-8') as f:
            print(arg, **kwargs, file=f)

def print_file_diff(file1, file2):
    return
    '''
    try:
        # with open(file1, 'r') as f1, open(file2, 'r') as f2:
        with open(file1, 'r', encoding='utf-8') as f1, open(file2, 'r', encoding='utf-8') as f2:
            diff = difflib.unified_diff(
                f1.readlines(),
                f2.readlines(),
                fromfile=file1,
                tofile=file2,
            )
        if diff:
            # get the file name from file1 without the directory
            file_name = get_base_name(file1)
            file_dir = os.path.dirname(file1)
            file_dir = replace_dir_name(file_dir, replace_value='short_dir').upper()
            file_dir = file_dir.replace('\\', '--')
            # append _diff to the file name
            file_name = f'diff___{file_dir}___{file_name}'
            file_path = os.path.join(output_dir, file_name)
            for line in diff:
                if line and line[0] in ('+', '-', '@'):
                    if line[0] == '@':
                        # Parse the hunk header to get the line ranges
                        old_range, new_range = line[2:-3].strip().split(' ')[0:2]
                        old_start, *old_len = map(int, old_range[1:].split(','))
                        new_start, *new_len = map(int, new_range[1:].split(','))
                        old_len = old_len[0] if old_len else 1
                        new_len = new_len[0] if new_len else 1
                        # Print a more descriptive message
                        print_to_file(f"/* ******** Original Line Range: {old_start}-{old_start+old_len-1} ******** */", file_path=file_path)
                        print_to_file(f"/* ******** New Line Range: {new_start}-{new_start+new_len-1} ******** */", file_path=file_path)
                    else:
                        print_to_file(line.strip(), file_path=file_path)
    except Exception as e:
        print(f'Error comparing files {file1} and {file2}:', e)
    '''

def print_list(list_values, header='', prepend='\t', replace_value='.', src_dir=None, dest_dir=None):
    if header:
        if isinstance(header, str):
            header = replace_dir_name(header, replace_value)
        print_to_file(header)
    for item in list_values:
        # print('item:',item)
        if(src_dir and dest_dir):
            print_file_diff(os.path.join(src_dir, item), os.path.join(dest_dir, item))
        if prepend:
            item = prepend + item
        print_to_file(item)

# Replace the print statements with the new function
def print_diff_files(dcmp):
    if dcmp.diff_files:
        print_list(dcmp.diff_files, f"In the {dcmp.left} directory:", src_dir=dcmp.left, dest_dir=dcmp.right)
    for sub_dcmp in dcmp.subdirs.values():
        print_diff_files(sub_dcmp)

def print_unique_files(dcmp):
    if dcmp.left_only:
        print_list(dcmp.left_only, f"In {dcmp.left} directory only:", replace_value='short_dir')
    if dcmp.right_only:
        print_list(dcmp.right_only, f"In {dcmp.right} directory only:", replace_value='short_dir')
    for sub_dcmp in dcmp.subdirs.values():
        print_unique_files(sub_dcmp)

def compare_dirs(dir1, dir2):
    # Create a dircmp object to compare two directories
    dcmp = filecmp.dircmp(dir1, dir2)

    # Print the files which are different
    print_to_file('******* Different files *******')
    print_diff_files(dcmp)
    print_to_file('')
    
    print_to_file('******* Unique files *******')
    print_unique_files(dcmp)
    
compare_dirs(dir1, dir2)

print('Script completed successfully. Output file:', output_file)
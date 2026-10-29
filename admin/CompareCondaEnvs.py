import subprocess
import os
import json
from difflib import unified_diff

env_packages = {}

envs = [
    r"\\nbs-app2\c$\Program Files\ArcGIS\Server\framework\runtime\ArcGIS\bin\Python\envs\arcgispro-py3",
    r"\\nbs-app2\c$\Program Files\ArcGIS\Server\framework\runtime\ArcGIS\bin\Python\envs\clone20240610",
    r"\\nbs-app2\c$\Program Files\ArcGIS\Server\framework\runtime\ArcGIS\bin\Python\envs\clone20240827"
]

def get_environment_packages(env_path):
    print(f"Getting packages in environment: {env_path}")
    try:
        # Activate the environment and list installed packages in JSON format
        cmd = f'"{os.path.join(env_path, "python.exe")}" -m pip list --format=json'
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Error running pip list: {result.stderr}")
        
        # Load the package list as a dictionary
        packages = json.loads(result.stdout)
        return {pkg['name'].lower(): pkg['version'] for pkg in packages}
    except Exception as e:
        print(f"Error getting packages in environment: {env_path} - {e}")
        return {}

# def compare_environments(env1, env2, env1_packages, env2_packages):
def compare_environments(env1, env2):
    env1_packages = env_packages[env1]
    env2_packages = env_packages[env2]
    
    diff = None
    try:
        print(f"Comparing environments:\n1. {env1}\n2. {env2}\n")
        # Generate a unified diff
        diff = list(unified_diff(
            sorted([f"{name}=={version}" for name, version in env1_packages.items()]),
            sorted([f"{name}=={version}" for name, version in env2_packages.items()]),
            fromfile=f'env1 ({env1})',
            tofile=f'env2 ({env2})',
            lineterm=''
        ))
    except RuntimeError as e:
        print(f"An error occurred: {e}")
    if diff:
        added_or_missing = []
        version_changes = []
        
        print("\nDifferences between the two environments:\n")

        for line in diff:
            if line.startswith('-') or line.startswith('+'):
                package_info = line[1:].strip()
                if '==' in package_info:
                    name, version = package_info.split('==')
                    if name in env1_packages and name in env2_packages:
                        version_changes.append(line)
                    else:
                        added_or_missing.append(line)
                else:
                    added_or_missing.append(line)

        if added_or_missing:
            print("\nAdded or Missing Packages:\n")
            for line in added_or_missing:
                print(line)

        if version_changes:
            print("\nVersion Changes:\n")
            for line in version_changes:
                print(line)
    else:
        print("The two environments have identical installed packages.")

    return diff

env_packages = {env: get_environment_packages(env) for env in envs}

print("Comparing all environments...\n")
for i in range(len(envs)):
    for j in range(i+1, len(envs)):
        env1 = envs[i]
        env2 = envs[j]
        differences = compare_environments(env1, env2)

print("\nComparison complete.")
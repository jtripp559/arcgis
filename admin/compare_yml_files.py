import yaml
import os
import pandas as pd

def parse_yaml_libs(yaml_path):
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    deps = data.get('dependencies', [])
    libs = {}
    for dep in deps:
        if isinstance(dep, str):
            if '=' in dep:
                name, *version = dep.split('=')
                libs[name.lower()] = '='.join(version)
            else:
                libs[dep.lower()] = None
        elif isinstance(dep, dict) and 'pip' in dep:
            for pip_dep in dep['pip']:
                if '==' in pip_dep:
                    name, version = pip_dep.split('==', 1)
                    libs[name.lower()] = version
                else:
                    libs[pip_dep.lower()] = None
    return libs

def compare_yaml_files(file1, file2):
    libs1 = parse_yaml_libs(file1)
    libs2 = parse_yaml_libs(file2)

    filename1 = os.path.splitext(os.path.basename(file1))[0]
    filename2 = os.path.splitext(os.path.basename(file2))[0]
    base_out = f"compare_{filename1}_vs_{filename2}"

    libs_set1 = set(libs1.keys())
    libs_set2 = set(libs2.keys())

    matching_libs = libs_set1 & libs_set2
    libs_only_in_1 = libs_set1 - libs_set2
    libs_only_in_2 = libs_set2 - libs_set1

    identical_versions = []
    differing_versions = []

    for lib in matching_libs:
        v1 = libs1[lib]
        v2 = libs2[lib]
        if v1 == v2:
            identical_versions.append((lib, v1))
        else:
            differing_versions.append((lib, v1, v2))
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    base_out = os.path.join(output_dir, base_out)
    base_out = f"{base_out}/"
    if not os.path.exists(base_out):
        os.makedirs(base_out)
    
    # Matching libraries (ignoring versions)
    pd.DataFrame(sorted(matching_libs), columns=["library"]).to_csv(f"{base_out}matching_libs.csv", index=False)

    # Libraries only in file 1
    pd.DataFrame(sorted(libs_only_in_1), columns=["library"]).to_csv(f"{base_out}libs_only_in_{filename1}.csv", index=False)

    # Libraries only in file 2
    pd.DataFrame(sorted(libs_only_in_2), columns=["library"]).to_csv(f"{base_out}libs_only_in_{filename2}.csv", index=False)

    # Matching libraries with identical versions
    pd.DataFrame(identical_versions, columns=["library", "version"]).to_csv(f"{base_out}identical_versions.csv", index=False)

    # Matching libraries with differing versions
    pd.DataFrame(differing_versions, columns=["library", f"{filename1}_version", f"{filename2}_version"]).to_csv(f"{base_out}differing_versions.csv", index=False)
    
    print(f"CSV outputs written with base name: {base_out}*.csv")

if __name__ == "__main__":
    '''
    if len(sys.argv) != 3:
        print("Usage: python compare_yml.py file1.yml file2.yml")
        sys.exit(1)
    compare_yaml_files(sys.argv[1], sys.argv[2])
    '''
    compare_yaml_files(r"C:\Develop\GIS\gis_general\ArcGIS Python Environments\clone20240827_asof20250805.yml", r"C:\Develop\GIS\gis_general\ArcGIS Python Environments\clone20251118_after.yml")
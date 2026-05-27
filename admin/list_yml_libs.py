
import yaml
import subprocess
import logging
import os
from datetime import datetime

def parse_yml(yml_path):
    with open(yml_path, 'r') as f:
        data = yaml.safe_load(f)
    conda_libs = []
    pip_libs = []
    for dep in data.get('dependencies', []):
        if isinstance(dep, str):
            conda_libs.append(dep)
        elif isinstance(dep, dict) and 'pip' in dep:
            pip_libs.extend(dep['pip'])
    return conda_libs, pip_libs

def parse_lib_version(lib_str, pip_style=False):
    if pip_style:
        if '==' in lib_str:
            name, version = lib_str.split('==', 1)
            return name, version
        else:
            return lib_str, None
    else:
        if '=' in lib_str:
            name, *version = lib_str.split('=')
            return name, '='.join(version) if version else None
        else:
            return lib_str, None

def check_conda_availability(lib_name):
    try:
        result = subprocess.run(
            ['conda', 'search', lib_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.returncode == 0 and lib_name in result.stdout
    except Exception:
        return False

def main(yml_path):
    # Setup logger
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Output')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = os.path.splitext(os.path.basename(yml_path))[0]
    log_file = os.path.join(log_dir, f"list_yml_libs_{base_name}_{timestamp}.log")

    logger = logging.getLogger('yml_logger')
    logger.setLevel(logging.INFO)
    # Remove any existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.INFO)
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # Formatter
    formatter = logging.Formatter('%(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    logger.info(f"Parsing YAML file: {yml_path}\n")

    conda_libs, pip_libs = parse_yml(yml_path)
    logger.info("Conda-installed libraries:")
    for lib in conda_libs:
        name, version = parse_lib_version(lib)
        logger.info(f"  {name}: {version if version else '(no version specified)'}")
    logger.info("")
    logger.info("Pip-installed libraries:")
    for lib in pip_libs:
        name, version = parse_lib_version(lib, pip_style=True)
        logger.info(f"  {name}: {version if version else '(no version specified)'}")
    logger.info("")
    logger.info("Checking if pip-installed libraries are available via conda:")
    for lib in pip_libs:
        name, _ = parse_lib_version(lib, pip_style=True)
        available = check_conda_availability(name)
        logger.info(f"  {name}: {'Available in conda' if available else 'Not found in conda'}")
    logger.info("")
    logger.info(f"Log written to: {log_file}")

if __name__ == "__main__":
    '''
    import sys
    if len(sys.argv) != 2:
        print("Usage: python list_yml_libs.py environment.yml")
    else:
        main(sys.argv[1])
    '''
    main(r"C:\Develop\GIS\gis_general\ArcGIS Python Environments\clone20250804_asof20251118.yml")
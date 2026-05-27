# Python Environment Detector

ArcGIS geoprocessing tool that reports which Python environment ArcGIS is actually using at runtime — Python version, `sys.prefix`, `sys.path`, the full list of installed packages (via `pkg_resources`), and `arcpy.GetInstallInfo()` output. Useful when an ArcGIS Server publish fails and you need to confirm the env the server is loading vs. the env you tested in Pro.

Based on Esri's reference tool — see <https://support.esri.com/en-us/knowledge-base/how-to-confirm-the-active-python-environment-for-an-arc-000026845> — modified by Julie Tripp.

## Contents

- `PythonEnvDetector.py` — the script.

## Usage

Designed to run as an ArcGIS geoprocessing tool with one parameter:

- **Parameter 0** — `FilePath`, a locally accessible directory writable by the account that runs ArcGIS Server. The script writes a timestamped report there.

Can also be run as a plain Python script under any ArcGIS env (it just inspects the current process).

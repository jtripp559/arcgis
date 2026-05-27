# Based on PythonEnvDetector.py created by ESRI
# Modified by: Julie Tripp
# Version: 11/30/2023
# More details can be found here:
# https://support.esri.com/en-us/knowledge-base/how-to-confirm-the-active-python-environment-for-an-arc-000026845
from platform import python_version
import arcpy
import sys
import datetime
from os.path import join
import pkg_resources
##Updated January, 2022
##Parameter 0 Label= Enter locally acccessible file path here (accessible to account running ArcGIS Server)
##Parameter 0 Name= FilePath
##Parameter 0 DataType= String
##Parameter 0 Type= Required
Report=[]
Report.append("PythonVersion= "+str(python_version()+"\n"))
Report.append("ActivePythonEnvironment= "+str(sys.prefix+"\n"))
##collect known system paths and detect if these are for ArcGIS Server, otherwise they are assumed to be in ArcGIS Desktop
Report.append("Known paths: \n")
Server=False
for i in sys.path:
    Report.append("\t"+i+"\n")
    if Server==False:
        for ii in i.split("\\"):
            if ii == "Server":
                Server = True
            else:
                pass
    else:
        pass
Report.append("PythonPackages: \n")
installed_packages = pkg_resources.working_set
installed_packages_list = sorted(["%s==%s" % (i.key, i.version) for i in installed_packages])
for package in installed_packages_list:
    Report.append("\t"+package+"\n")
Report.append("ArcGISInstallInfo: \n")
arcpyInstallInfo = arcpy.GetInstallInfo()
for key, value  in arcpyInstallInfo.items():
    Report.append("\t"+key+"=="+value+"\n")
##createfilename using epoch timestamp
FileName="ArcGIS_PythonEnvDetectorCouldNotReadTimestamp"
try:
    TimeStmp = int(datetime.datetime.now().timestamp())
    if Server==False:
        FileName="ArcGIS_DesktopAtEpoch"+str(TimeStmp)
    else:
        FileName="ArcGIS_ServerAtEpoch"+str(TimeStmp)
except:
    arcpy.AddError("Unable to access 'datetime.now()' from datetime library\nOutput file will be named{}".format(FileName))
    pass
scratch_folder = arcpy.env.scratchFolder
path = join(scratch_folder, FileName+".txt")
# path=arcpy.GetParameterAsText(0)+"\\"+FileName+".txt"
##create .txt file at specified directory
try:
    txt=open(path,"w")
    for iii in Report:
        arcpy.AddMessage(iii)
        txt.write(iii)
    txt.close()
    arcpy.AddMessage("\nFile written to: {}".format(txt.name))
    arcpy.SetParameter(0, path)
except:
    arcpy.AddError("Unable to write txt file to the path: {}\n Please check permissions for accessing the directory".format(path))
    pass

import os
import requests
import rasterio
from rasterio.merge import merge

# url_base = "https://data.worldpop.org/GIS/Population_Density/Global_2000_2020_1km/2020/"
url_base = "https://data.worldpop.org/GIS/"
population_type = "Population_Density"  # "Population" or "Population_Density"
population_type_abbr = "pd" # "ppp" or "pd"
year = "2020"
dataset_span = "Global_2000_2020"
resolution = "1km"
# tif_append = "_pd_2020_1km.tif"
tif_append = f"_{population_type_abbr}_{year}_{resolution}.tif"
url_base = f"{url_base}{population_type}/{dataset_span}_{resolution}/{year}/"

# Directory to save the tiff files
output_dir = r"D:\GenericArcGISDataDir\WorldPop\Population_Density\1km"
# output_dir = r"D:\GenericArcGISDataDir\WorldPop\"
# output_dir = os.path.join(output_dir, population_type, resolution)

# countries = ["ATA"
countries = ["ABW", "AFG", "AGO", "AIA", "ALA", "ALB", "AND", "ARE", "ARG", "ARM", "ASM", "ATF", "ATG", "AUS", "AUT", "AZE", 
            "BDI", "BEL", "BEN", "BES", "BFA", "BGD", "BGR", "BHR", "BHS", "BIH", "BLM", "BLR", "BLZ", "BMU", "BOL", "BRA", "BRB", "BRN", "BTN", "BVT", "BWA", 
            "CAF", "CAN", "CHE", "CHL", "CHN", "CIV", "CMR", "COD", "COG", "COK", "COL", "COM", "CPV", "CRI", "CUB", "CUW", "CYM", "CYP", "CZE", 
            "DEU", "DJI", "DMA", "DNK", "DOM", "DZA", 
            "ECU", "EGY", "ERI", "ESH", "ESP", "EST", "ETH", 
            "FIN", "FJI", "FLK", "FRA", "FRO", "FSM", 
            "GAB", "GBR", "GEO", "GGY", "GHA", "GIB", "GIN", "GLP", "GMB", "GNB", "GNQ", "GRC", "GRD", "GRL", "GTM", "GUF", "GUM", "GUY", 
            "HKG", "HMD", "HND", "HRV", "HTI", "HUN", 
            "IDN", "IMN", "IND", "IOT", "IRL", "IRN", "IRQ", "ISL", "ISR", "ITA", 
            "JAM", "JEY", "JOR", "JPN", 
            "KAZ", "KEN", "KGZ", "KHM", "KIR", "KNA", "KOR", "KOS", "KWT", 
            "LAO", "LBN", "LBR", "LBY", "LCA", "LIE", "LKA", "LSO", "LTU", "LUX", "LVA", 
            "MAC", "MAF", "MAR", "MCO", "MDA", "MDG", "MDV", "MEX", "MHL", "MKD", "MLI", "MLT", "MMR", "MNE", "MNG", "MNP", "MOZ", "MRT", "MSR", "MTQ", "MUS", "MWI", "MYS", "MYT", 
            "NAM", "NCL", "NER", "NFK", "NGA", "NIC", "NIU", "NLD", "NOR", "NPL", "NRU", "NZL", 
            "OMN", 
            "PAK", "PAN", "PCN", "PER", "PHL", "PLW", "PNG", "POL", "PRI", "PRK", "PRT", "PRY", "PSE", "PYF", 
            "QAT", 
            "REU", "ROU", "RUS", "RWA", 
            "SAU", "SDN", "SEN", "SGP", "SGS", "SHN", "SJM", "SLB", "SLE", "SLV", "SMR", "SOM", "SPM", "SPR", "SRB", "SSD", "STP", "SUR", "SVK", "SVN", "SWE", "SWZ", "SXM", "SYC", "SYR", 
            "TCA", "TCD", "TGO", "THA", "TJK", "TKL", "TKM", "TLS", "TON", "TTO", "TUN", "TUR", "TUV", "TWN", "TZA", 
            "UGA", "UKR", "UMI", "URY", "USA", "UZB", 
            "VAT", "VCT", "VEN", "VGB", "VIR", "VNM", "VUT", 
            "WLF", "WSM", 
            "YEM", 
            "ZAF", "ZMB", "ZWE"]

# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

def download_file(url, output_path):
    if os.path.exists(output_path):
        print(f"File already exists: {output_path}")
        return 1
    else:
        try:
            print("Downloading: ", url)
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(output_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                print(f"Downloaded file saved at: {output_path}")
            else:
                print(f"Failed to download: {url}")
            return 1
        except Exception as e:
            print(f"Failed to download: {url}")
            print(e)
            return 0

def merge_tiff_files(tif_files, output_file_path):
    try:
        if os.path.exists(output_file_path):
            print(f"Removing existing file: {output_file_path}")
            os.remove(output_file_path)
        print("Opening the TIFF files...")
        src_files_to_mosaic = []
        nodata_value = None
        dtype = None
        crs = None
        for tif_file in tif_files:
            if os.path.exists(tif_file):
                src = rasterio.open(tif_file)
                src_files_to_mosaic.append(src)
                # Validate identical nodata values, data types, and CRS
                if nodata_value is None:
                    nodata_value = src.nodata
                elif nodata_value != src.nodata:
                    print(f"nodata mismatch: {nodata_value} != {src.nodata}")
                    raise ValueError("Not all input files have the same NoData value.")
                if dtype is None:
                    dtype = src.dtypes[0]
                elif dtype != src.dtypes[0]:
                    print(f"dtype mismatch: {dtype} != {src.dtypes[0]}")
                    raise ValueError("Not all input files have the same data type.")
                if crs is None:
                    crs = src.crs
                elif crs != src.crs:
                    print(f"crs mismatch: {crs} != {src.crs}")
                    raise ValueError("Not all input files have the same CRS.")
        
        print("Merging the TIFF files...")
        mosaic, out_trans = merge(src_files_to_mosaic, nodata=nodata_value)

        print("Updating the metadata...")
        out_meta = src_files_to_mosaic[0].meta.copy()
        out_meta.update({"driver": "GTiff", 
                         "height": mosaic.shape[1], 
                         "width": mosaic.shape[2], 
                         "transform": out_trans,
                         "crs": crs,
                         "nodata": nodata_value,
                         "count": src_files_to_mosaic[0].count,
                         "dtype": dtype})

        print("Saving the merged TIFF file...")
        with rasterio.open(output_file_path, "w", **out_meta) as dest:
            dest.write(mosaic)

        print(f"Merged TIFF file saved at: {output_file_path}")
    except Exception as e:
        print("Failed to merge the TIFF files.")
        print(e)
    finally:
        # Ensure all files are closed
        for src in src_files_to_mosaic:
            src.close()

print("Downloading and merging the data...")

# Download each file
total_downloads = 0
for country in countries:
    url = f"{url_base}{country}/{country.lower()}{tif_append}"
    file_name = os.path.basename(url)
    output_path = os.path.join(output_dir, file_name)
    total_downloads = total_downloads + download_file(url, output_path)

if total_downloads > 0:
    # List all the downloaded TIFF files
    tif_files = [os.path.join(output_dir, f"{country.lower()}{tif_append}") for country in countries]
    
    # Set the output file path
    output_file_name = f"{population_type_abbr}_{year}_{resolution}_Aggregated.tif"
    output_file = os.path.join(output_dir, output_file_name)
    
    merge_tiff_files(tif_files, output_file)

print("Downloads and merging completed.")
'Author: Julie Tripp, julie.tripp@rrgnbs.com
Version: 08/09/2024'

# Scrip to run in the background in Linux:
#     nohup Rscript /home/jtripp/scripts/BasinATLAS_Global_Population.R > /home/jtripp/scripts/output/BasinATLAS_Global_PopDensity_output.log 2>&1 &
#   Test if the script is running:
#     ps aux | grep BasinATLAS_Global_Population.R

# Load libraries ----------------------------------------------------------
library(terra)
library(exactextractr)

# Set file paths
shapefile_path <- "/home/jtripp/rasters/BasinATLAS_v10_lev09.shp"
raster_path <- "/home/jtripp/rasters/pd_2020_1km_Aggregated.tif"
output_csv_path <- "/home/jtripp/scripts/output/WorldPop_Density_1km2020_BasinATLAS.csv"
# shapefile_path <- "//10.13.93.12/t$/ArcGISDataset/Rasters/GlobalProspector/Level9/BasinATLAS_v10_lev09.shp"
# raster_path <- "//10.13.93.12/t$/ArcGISDataset/Rasters/WorldPop/1km/pd_2020_1km_Aggregated.tif"

## Load raster using terra
print("Loading raster...")
rasterData <- rast(raster_path)

## Load basin coverage in shp format using terra
print("Loading basin coverage...")
basin <- vect(shapefile_path)

# Convert the terra object to an sf object
print("Converting basin coverage to sf object...")
basin_sf <- sf::st_as_sf(basin)

# initialize existingOutputTable
existingOutputTable <- NULL

## Create output table
print("Creating output table...")
outputTable <- data.frame(HYBAS_ID = numeric(), Population = numeric())
# outputTable <- data.frame(matrix(ncol= 1, nrow = length(basin_sf$HYBAS_ID)))
# outputTable$HYBAS_ID <- basin_sf$HYBAS_ID

# check if output_csv_path exists
if (file.exists(output_csv_path)) {
    # read the contents of output_csv_path into existingOutputTable
    # this will be compared against to exclude already processed basins

    # read the existing CSV file
    existingOutputTable <- read.csv(output_csv_path, header = TRUE, stringsAsFactors = FALSE)

    # get the HYBAS_IDs of the existing basins
    existingHYBAS_IDs <- existingOutputTable$HYBAS_ID
} else {
    # Initialize the CSV file with headers
    print("Initializing CSV file...")
    write.table(outputTable, output_csv_path, sep = ",", col.names = TRUE, row.names = FALSE, append = FALSE)
}

## Sum
# outputTable$Population <- exact_extract(rasterData, basin_sf, fun='sum', force_df =T, max_cells_in_memory = 6e+08, progress = F) 
basin_record_count <- length(basin_sf$HYBAS_ID)
progress_interval <- basin_record_count / 5
print(paste("Processing ", basin_record_count, " basins...", Sys.time()))

for(i in 1:basin_record_count){
    polygon <- basin_sf[i,]
    hybas_id <- polygon$HYBAS_ID

    # Skip the basin if it has already been processed
    if (exists("existingHYBAS_IDs") && hybas_id %in% existingHYBAS_IDs) {
        next
    }

    # Extract the population data for the current basin
    population <- exact_extract(rasterData, polygon, fun='sum', force_df =T, max_cells_in_memory = 6e+08, progress = F)
    
    # Add the population data to the output table
    # outputTable <- rbind(outputTable, data.frame(HYBAS_ID = hybas_id, Population = population))
    outputTable <- data.frame(HYBAS_ID = hybas_id, Population = population)
    
    # Append the data to the CSV file
    write.table(outputTable, output_csv_path, sep = ",", col.names = FALSE, row.names = FALSE, append = TRUE)

    # Add the population data to the output table
    outputTable <- data.frame(HYBAS_ID = hybas_id, Population = population)

    # Print progress for every progress_interval iterations
    if (i %% progress_interval == 0) {
        print(paste("Progress: ", (i / basin_record_count) * 100, "% completed", Sys.time()))
    }
}

# # Save calculations in a csv file -----------------------------------------
# print("Saving calculations to a csv file...")
# write.csv(outputTable, output_csv_path)

print(paste("Population data has been written to", output_csv_path))
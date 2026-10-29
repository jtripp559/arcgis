# ListAndUpdateServices.py
# By: Julie Tripp
# Date: 05/09/2025
# This script is functional and works correctly as of Enterprise 11.1.0
#
# Adapted from:
#   https://github.com/pheede/ArcGIS-Enterprise-Stuff/blob/master/sharedinstances.py
#   https://github.com/WUSTL-GIS-Programming-spring-2014/classinfo/blob/master/Classes/Class8/ChangeInstances.py
#
import sys
import argparse
import urllib
import logging
import os
from datetime import datetime
import json
import requests

servicesNeedingChange = []
# servicesNeedingChange = ['CHELSA_Pr_CF_01_1979_2019_2011_2040']
'''
servicesNeedingChange = ['090160_RED',
                         '1981_2000_Annual_Average_Precip_tif',
                         '1981_2000_Apr_Average_tif',
                         '1981_2000_Dec_Average_tif',
                         '1981_2000_Feb_Average_tif',
                         '1981_2000_Jan_Average_tif',
                         '1981_2000_Jul_Average_tif',
                         '1981_2000_Jun_Average_tif',
                         '1981_2000_Mar_Average_tif',
                         '1981_2000_May_Average_tif',
                         '1981_2000_Nov_Average_tif',
                         '1981_2000_Oct_Average_tif',
                         '1981_2000_Sep_Average_tif',
                         '1981_2023_Annual_Average_Precip_tif',
                         '1981_2023_Apr_Average_tif',
                         '1981_2023_Aug_Average_tif',
                         '1981_2023_Dec_Average_tif',
                         '1981_2023_Feb_Average_tif',
                         '1981_2023_Jan_Average_tif',
                         '1981_2023_Jul_Average_tif',
                         '1981_2023_Jun_Average_tif',
                         '1981_2023_Mar_Average_tif',
                         '1981_2023_May_Average_tif',
                         '1981_2023_Nov_Average_tif',
                         '1981_2023_Oct_Average_tif',
                         '1981_2023_Sep_Average_tif',
                         '1981_Average_tif',
                         '1982_Average_tif',
                         '1983_tif',
                         '1984_tif',
                         '1985_Average_tif',
                         '1986_Average_tif',
                         '1987_Average_tif',
                         '1988_Average_tif',
                         '1989_Average_tif',
                         '1990_Average_tif',
                         '1991_Average_tif',
                         '1992_Average_tif',
                         '1993_Average_tif',
                         '1994_Average_tif',
                         '1995_Average_tif',
                         '1996_Average_tif',
                         '1997_Average_tif',
                         '1998_Average_tif',
                         '1999_Average_tif',
                         '2000_Average_tif',
                         '2001_2023_Annual_Average_Precip_tif',
                         '2001_2023_Apr_Average_tif',
                         '2001_2023_Aug_Average_tif',
                         '2001_2023_Dec_Average_tif',
                         '2001_2023_Feb_Average_tif',
                         '2001_2023_Jan_Average_tif',
                         '2001_2023_Jul_Average_tif',
                         '2001_2023_Jun_Average_tif',
                         '2001_2023_Mar_Average_tif',
                         '2001_2023_May_Average_tif',
                         '2001_2023_Nov_Average_tif',
                         '2001_2023_Oct_Average_tif',
                         '2001_2023_Sep_Average_tif',
                         '2001_Average_tif',
                         '2002_Average_tif',
                         '2003_Average_tif',
                         '2004_Average_tif',
                         '2005_Average_tif',
                         '2006_Average_tif',
                         '2007_Average_tif',
                         '2008_Average_tif',
                         '2009_Average_tif',
                         '2010_Average_tif',
                         '2011_Average_tif',
                         '2012_Average_tif',
                         '2013_Average_tif',
                         '2014_Average_tif',
                         '2015_Average_tif',
                         '2016_Average_tif',
                         '2017_Average_tif',
                         '2018_Average_tif',
                         '2019_Average_tif',
                         '2020_Average_tif',
                         '2021_Average_tif',
                         '2022_Average_tif',
                         '2023_Average_tif',
                         '2040_April_average_precipitation',
                         '2040_August_average_precipitation',
                         '2040_December_average_precipitation',
                         '2040_February_average_precipitation',
                         '2040_January_average_precipitation',
                         '2040_July_average_precipitation',
                         '2040_June_average_precipitation',
                         '2040_March_average_precipitation',
                         '2040_May_average_precipitation',
                         '2040_November_average_precipitation',
                         '2040_October_average_precipitation',
                         '2040_September_average_precipitation',
                         '2070_April_average_precipitation',
                         '2070_August_average_precipitation',
                         '2070_December_average_precipitation',
                         '2070_February_average_precipitation',
                         '2070_January_average_precipitation',
                         '2070_July_average_precipitation',
                         '2070_June_average_precipitation',
                         '2070_March_average_precipitation',
                         '2070_May_average_precipitation',
                         '2070_November_average_precipitation',
                         '2070_October_average_precipitation',
                         '2070_September_average_precipitation',
                         '22S_Rec_CSM_Hist_2030_tif',
                         '22S_Rec_CSM_Hist_2050_tif',
                         '22S_Rec_CSM_Hist_2070_tif',
                         '22S_Rec_CSM_Hist_tif',
                         'ABHAFOOTHILLS_1981_2010',
                         'AFOURERBENI1_2_1981_2010',
                         'AFOURERBENI3_1981_2010',
                         'AFOURERBENI4_1981_2010',
                         'AFOURERBENI5_1981_2010',
                         'AFOURERBENI6_1981_2010',
                         'AGADIRBIO_1981_2010_TIF',
                         'AGAFAY_2011_2040',
                         'AGAFAY_CURRENT_1981_2010',
                         'AINHAMRA_1981_2010',
                         'AL_AHSA_OASIS_1981_2010',
                         'AL_AIN_ABU_DHABI_1981_2010',
                         'AL_BATINAH_1981_2010',
                         'AL_DHAID_SHARJAH_1981_2010',
                         'AL_JOUF_1981_2010',
                         'AL_QASSIMSAU_1981_2010',
                         'ALLAMIABENIMELLAL_1981_2010',
                         'ALLENDE_PN_AQUIFER_1981_2010',
                         'Annual_Mean_Precip_2030_tif',
                         'Annual_Mean_Precip_2050_tif',
                         'Annual_Mean_Precip_Current_Para_tif',
                         'Annual_mean_precipitation_1981_2024',
                         'April_average_precipitation',
                         'ASIR_1981_2010',
                         'August_average_precipitation',
                         'Banana_Brazil_1981_2010',
                         'Banana_Brazil_2011_2040',
                         'Banana_Brazil_2041_2070',
                         'Banana_Costa_Rica_1981_2010',
                         'Banana_Costa_Rica_2011_2040',
                         'Banana_Costa_Rica_2041_2070',
                         'Banana_Ecuador_1981_2010',
                         'Banana_Ecuador_2011_2040',
                         'Banana_Ecuador_2041_2070',
                         'Banana_India_1981_2010',
                         'Banana_India_2011_2040',
                         'Banana_India_2041_2070',
                         'Banana_Indonesia_1981_2010',
                         'Banana_Indonesia_2011_2040',
                         'Banana_Indonesia_2041_2070',
                         'BasinATLAS_Level_12',
                         'Batea_1_1981_2010',
                         'Batea_1_2011_2040',
                         'Batea_1_2041_2070',
                         'Batea_2_1981_2010',
                         'Batea_2_2011_2040',
                         'Batea_2_2041_2070',
                         'Beisa_NDVICurrent_April2024',
                         'Beisa_NDVIPeak_January2024_IrrigatedWheat',
                         'Beisa_NDVIPeak_July2023_PrimaryCrops',
                         'BELLE_GLADE_FL_1981_2010',
                         'BELLE_GLADE_FL_2011_2040',
                         'BERRYMEX_1981_2010',
                         'BERRYMX_2011_2040',
                         'BHP_Mt_Arthur_1981_2010_tif',
                         'BHP_Mt_Arthur_2011_2040',
                         'BHP_Mt_Arthur_2041_2070',
                         'BHP_Mt_Arthur_2071_2100',
                         'Big_Valley_Texas_1981_2010',
                         'Big_Valley_Texas_2011_2040',
                         'Boa_Sorte_1981_2010',
                         'Boa_Sorte_2011_2040',
                         'Boa_Sorte_2041_2070',
                         'BREWSTER_2011_2040',
                         'BREWSTER_CURRENT_1981_2010',
                         'Cacao_Cocoa_2030_Suitability_Regions_in_Central_America',
                         'CacaoMars',
                         'CALAMA_ANTOFAGASTA_1981_2010',
                         'CarmeloAlegreBranca_1981_2010',
                         'CarmeloAlegreBranca_2011_2040',
                         'CarmeloAlegreBranca_2041_2070',
                         'CBRE_ROCKET_1981_2010',
                         'CBRE_ROCKET_2011_2040',
                         'Chaha_Grupo_Llano_1981_2010',
                         'Chaha_Grupo_Llano_2011_2040',
                         'Chaha_Grupo_Llano_2041_2070',
                         'Chaha_Grupo_Llano_2071_2100',
                         'CHELSA_ET_CF_01_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_02_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_03_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_04_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_05_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_06_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_07_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_08_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_09_2000_2019_2011_2040',
                         'CHELSA_ET_CF_10_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_11_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_ET_CF_12_2000_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_01_1981_2010_V21',
                         'CHELSA_Pr_01_2011_2040_V21',
                         'CHELSA_Pr_02_1981_2010_V21',
                         'CHELSA_Pr_02_2011_2040_V21',
                         'CHELSA_Pr_03_1981_2010_V21',
                         'CHELSA_Pr_03_2011_2040_V21',
                         'CHELSA_Pr_04_1981_2010_V21',
                         'CHELSA_Pr_04_2011_2040_V21',
                         'CHELSA_Pr_05_1981_2010_V21',
                         'CHELSA_Pr_05_2011_2040_V21',
                         'CHELSA_Pr_06_1981_2010_V21',
                         'CHELSA_Pr_06_2011_2040_V21',
                         'CHELSA_Pr_07_1981_2010_V21',
                         'CHELSA_Pr_07_2011_2040_V21',
                         'CHELSA_Pr_08_1981_2010_V21',
                         'CHELSA_Pr_08_2011_2040_V21',
                         'CHELSA_Pr_09_1981_2010_V21',
                         'CHELSA_Pr_09_2011_2040_V21',
                         'CHELSA_Pr_10_1981_2010_V21',
                         'CHELSA_Pr_10_2011_2040_V21',
                         'CHELSA_Pr_11_1981_2010_V21',
                         'CHELSA_Pr_11_2011_2040_V21',
                         'CHELSA_Pr_12_1981_2010_V21',
                         'CHELSA_Pr_12_2011_2040_V21',
                         'CHELSA_pr_2000_2019_V_2_1',
                         'CHELSA_Pr_CF_01_1979_2019_2011_2040',
                         'CHELSA_PR_CF_01_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_01_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_02_1979_2019_2011_2040',
                         'CHELSA_PR_CF_02_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_02_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_03_1979_2019_2011_2040',
                         'CHELSA_PR_CF_03_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_03_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_04_1979_2019_2011_2040',
                         'CHELSA_PR_CF_04_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_04_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_05_1979_2019_2011_2040',
                         'CHELSA_PR_CF_05_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_05_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_06_1979_2019_2011_2040',
                         'CHELSA_PR_CF_06_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_06_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_07_1979_2019_2011_2040',
                         'CHELSA_PR_CF_07_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_07_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_08_1979_2019_2011_2040',
                         'CHELSA_PR_CF_08_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_08_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_09_1979_2019_2011_2040',
                         'CHELSA_PR_CF_09_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_09_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_10_1979_2019_2011_2040',
                         'CHELSA_PR_CF_10_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_10_2000_2019_2041_2070',
                         'CHELSA_PR_CF_11_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_11_2000_2019_2041_2070',
                         'CHELSA_Pr_CF_12_1979_2019_2011_2040',
                         'CHELSA_PR_CF_12_1979_2019_2011_2040_Ethiopia',
                         'CHELSA_Pr_CF_12_2000_2019_2041_2070',
                         'CHELSA_Synthetic_chillHours45_ChangeHistoric2030',
                         'Chita_Valley_Project_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Chita_Valley_Project_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'ClimaticRegions_Chickpeas',
                         'ClimaticRegions_Corn',
                         'ClimaticRegions_FingerMillet',
                         'ClimaticRegions_Peanut',
                         'ClimaticRegions_Rice',
                         'ClimaticRegions_Sesame',
                         'ClimaticRegions_Sorghum',
                         'ClimaticRegions_Soy',
                         'ClimaticRegions_Wheat',
                         'COLDSTREAM_BC_1981_2010',
                         'COLDSTREAM_BC_2011_2040',
                         'Columbia_River_1981_2010',
                         'Columbia_River_2011_2040',
                         'Columbia_River_2041_2070',
                         'Condor_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Condor_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'Condor_Edizione_1981_2010',
                         'Condor_Edizione_2011_2040',
                         'Condor_Edizione_2041_2070',
                         'Condor_Edizione_2071_2100',
                         'Coronel_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Coronel_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'Coronel_Edizione_1981_2010',
                         'Coronel_Edizione_2011_2040',
                         'Coronel_Edizione_2041_2070',
                         'Coronel_Edizione_2071_2100',
                         'Corylus_Hazelnuts_Chile_1981_2010',
                         'Corylus_Hazelnuts_Chile_2011_2040',
                         'Corylus_Hazelnuts_Chile_2041_2070',
                         'Corylus_Hazelnuts_Chile_2071_2100',
                         'Current_Mean_Temperature',
                         'DAKHLA_1981_2010',
                         'DAKHLA_2011_2040',
                         'DARBELAMRIP1_1981_2010',
                         'DARBELAMRIP2_1981_2010',
                         'December_average_precipitation',
                         'Def23_Chaha_Vya_tif',
                         'Deforestation23_GFW_tif',
                         'DEM_Balcarce',
                         'DEM_Condor',
                         'DEM_Cordillera',
                         'DEM_Coronel',
                         'DEM_Edizione',
                         'Depth_to_Groundwater_Fan_2013_WTD_Annual',
                         'Deseret_Woodland_1981_2010',
                         'Deseret_Woodland_2011_2040',
                         'Deseret_Woodland_2041_2070',
                         'Desmatamento_22_tif',
                         'Diffuse_Average_Annual_Recharge_CLM45',
                         'Diffuse_Average_Annual_Recharge_H08',
                         'Diffuse_Average_Annual_Recharge_LPLml',
                         'DOMAINENOURP1_1981_2010',
                         'DOMAINENOURP2_1981_2010',
                         'DONAHELENA_1981_2010',
                         'DONALFONSO_1981_2010',
                         'DOUHOKU_HOKKAIDO_JAPAN_1981_2010',
                         'DOUOU_HOKKAIDO_JAPAN_1981_2010',
                         'DOUTOU_HOKKAIDO_JAPAN_1981_2010',
                         'Elevation_50m_Para_State',
                         'Elevation_Para',
                         'Esmerelda_1981_2010',
                         'Esmerelda_2011_2040',
                         'Esmerelda_2041_2070',
                         'ET_Avg_Annual_Change_2000_2019_2011_2040_Ethiopia',
                         'Ethiopia_bdod_0_5cm_mean',
                         'Ethiopia_bdod_15_30cm_mean',
                         'Ethiopia_bdod_30_60cm_mean',
                         'Ethiopia_bdod_5_15cm_mean',
                         'Ethiopia_bdod_60_100cm_mean',
                         'Ethiopia_cec_0_5cm_mean',
                         'Ethiopia_cec_15_30cm_mean',
                         'Ethiopia_cec_30_60cm_mean',
                         'Ethiopia_cec_5_15cm_mean',
                         'Ethiopia_cec_60_100cm_mean',
                         'Ethiopia_cfvo_0_5cm_mean',
                         'Ethiopia_cfvo_15_30cm_mean',
                         'Ethiopia_cfvo_30_60cm_mean',
                         'Ethiopia_cfvo_5_15cm_mean',
                         'Ethiopia_cfvo_60_100cm_mean',
                         'Ethiopia_CHELSA_AccPr_GrowingSeason_02_07_2002_2019',
                         'Ethiopia_CHELSA_AccPr_GrowingSeason_02_07_2011_2040',
                         'Ethiopia_clay_0_5cm_mean',
                         'Ethiopia_clay_15_30cm_mean',
                         'Ethiopia_clay_30_60cm_mean',
                         'Ethiopia_clay_5_15cm_mean',
                         'Ethiopia_clay_60_100cm',
                         'Ethiopia_EC_0_5cm',
                         'Ethiopia_EC_100_200cm',
                         'Ethiopia_EC_15_30cm',
                         'Ethiopia_EC_30_60cm',
                         'Ethiopia_EC_5_15cm',
                         'Ethiopia_EC_60_100cm',
                         'Ethiopia_Effective_precipitation_Annual_mm',
                         'Ethiopia_Effective_Precipitation_PE_2002_2019',
                         'Ethiopia_nitrogen_0_5cm_mean',
                         'Ethiopia_nitrogen_15_30cm_mean',
                         'Ethiopia_nitrogen_30_60cm_mean',
                         'Ethiopia_nitrogen_5_15cm_mean',
                         'Ethiopia_nitrogen_60_100cm_mean',
                         'Ethiopia_ocd_0_5cm_mean',
                         'Ethiopia_ocd_15_30cm_mean',
                         'Ethiopia_ocd_30_60cm_mean',
                         'Ethiopia_ocd_5_15cm_mean',
                         'Ethiopia_ocd_60_100cm_mean',
                         'Ethiopia_ocs_0_30cm_mean',
                         'Ethiopia_phh2o_0_5cm_mean',
                         'Ethiopia_phh2o_15_30cm_mean',
                         'Ethiopia_phh2o_30_60cm_mean',
                         'Ethiopia_phh2o_5_15cm_mean',
                         'Ethiopia_phh2o_60_100cm_mean',
                         'Ethiopia_sand_0_5cm_mean',
                         'Ethiopia_sand_15_30cm_mean',
                         'Ethiopia_sand_30_60cm_mean',
                         'Ethiopia_sand_5_15cm_mean',
                         'Ethiopia_sand_60_100cm_mean',
                         'Ethiopia_silt_0_5cm_mean',
                         'Ethiopia_silt_15_30cm_mean',
                         'Ethiopia_silt_30_60cm_mean',
                         'Ethiopia_silt_5_15cm_mean',
                         'Ethiopia_silt_60_100cm_mean',
                         'Ethiopia_soc_0_5cm_mean',
                         'Ethiopia_soc_15_30cm_mean',
                         'Ethiopia_soc_30_60cm_mean',
                         'Ethiopia_soc_5_15cm_mean',
                         'Ethiopia_soc_60_100cm_mean',
                         'Ext_Rec_22S_CSM_Hist_2030_tif',
                         'Ext_Rec_22S_CSM_Hist_2050_tif',
                         'Ext_Rec_22S_CSM_Hist_2070_tif',
                         'Ext_Rec_22S_CSM_Hist_tif',
                         'February_average_precipitation',
                         'FRI_Dessert_Farms_1_1981_2010',
                         'FRI_Dessert_Farms_1_2011_2040',
                         'FRI_Dessert_Farms_2_1981_2010',
                         'FRI_Dessert_Farms_2_2011_2040',
                         'FRI_Dessert_Farms_3_1981_2010',
                         'FRI_Dessert_Farms_3_2011_2040',
                         'FRI_Dessert_Farms_4_1981_2010',
                         'FRI_Dessert_Farms_4_2011_2040',
                         'FRI_Dessert_Farms_5_1981_2010',
                         'FRI_Dessert_Farms_5_2011_2040',
                         'Gabiro_Rwanda_Climate_Similarity_Historical_to_Historical',
                         'Gabiro_Rwanda_Climate_Similarity_Model_Historical_to_2030',
                         'Global_runoff_March',
                         'GlobalEstimateRecharge2030_Level9_m3yr_GP',
                         'gpWidgetTest',
                         'HARASROYAL_1981_2010',
                         'Hazelnuts_1981_2010',
                         'Hazelnuts_2011_2040',
                         'i07_WellCompletionReports',
                         'IBRI_AL_DHAHIRAH_1981_2010',
                         'IMPERIAL_1981_2010',
                         'IMPERIAL_2011_2040',
                         'ISELI_NURSERY_1981_2010',
                         'ISELI_NURSERY_2011_2040',
                         'Itauna_1981_2010',
                         'Itauna_2011_2040',
                         'Itauna_2041_2070',
                         'JACKSONCOUNTY_1981_2010',
                         'JALAPA_CURRENT_1981_2010',
                         'January_average_precipitation',
                         'JIZAN_1981_2010',
                         'July_average_precipitation',
                         'June_average_precipitation',
                         'KECKS_CURRENT_1981_2010',
                         'KELAATMAGOUNA1_1981_2010',
                         'KELAATMAGOUNA2_1981_2010',
                         'Kern_Parcels_GT90_Acres',
                         'KHOAUALKA_1981_2010',
                         'LACAMPANA1_1981_2010',
                         'LACAMPANA2_1981_2010',
                         'LAPUNTAV2_1981_2010',
                         'Las_Hormigas_1981_2010',
                         'Las_Hormigas_2011_2040',
                         'Leleque_Argentina_2041_2070',
                         'Leleque_Argentina_2071_2100',
                         'Leleque_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Leleque_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'Les_Domaines',
                         'LIWA_OASIS_1981_2010',
                         'LUXOR_CUORO_1981_2010',
                         'LUXOR_CUORO_2011_2040',
                         'LUXOR_CUORO_2041_2070',
                         'LUXOR_CUORO_2071_2100',
                         'LUXOR_SAO_BENITO_1981_2010',
                         'LUXOR_SAO_BENITO_2011_2040',
                         'LUXOR_SAO_BENITO_2041_2070',
                         'LUXOR_SAO_BENITO_2071_2100',
                         'MAAZIZ_1981_2010',
                         'Maiten_Argentina_2041_2070',
                         'Maiten_Argentina_2071_2100',
                         'Maiten_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Maiten_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'MANULIFE_KERN_COUNTY_LINE_1981_2010',
                         'MANULIFE_KERN_COUNTY_LINE_2011_2040',
                         'MANULIFE_KERN_LERDO_1981_2010',
                         'MANULIFE_KERN_LERDO_2011_2040',
                         'MANULIFE_LTRID_1981_2010',
                         'MANULIFE_LTRID_2011_2040',
                         'MANULIFE_PIXLEYID_1981_2010',
                         'MANULIFE_PIXLEYID_2011_2040',
                         'March_average_precipitation',
                         'MARSALA_ITALY_1981_2010',
                         'MARSALA_ITALY_2011_2040',
                         'MARSING_1981_2010',
                         'May_average_precipitation',
                         'Mean_Temperature_2040',
                         'Mean_Temperature_2070',
                         'Medicilandia_Para_Brazil_1981_2010',
                         'Medicilandia_Para_Brazil_2011_2040',
                         'Medicilandia_Para_Brazil_2041_2070',
                         'Medicilandia_Para_Brazil_2071_2100',
                         'MELDEDRECHARGEPOTENTIAL',
                         'MeldedRechargePotential_3mSoil_Ethiopia',
                         'METTLER_2011_2040',
                         'METTLER_CURRENT_1981_2010',
                         'MONASH_2011_2040',
                         'MONASH_CURRENT_1981_2010',
                         'Montoso_Edizione_1981_2010',
                         'Montoso_Edizione_2011_2040',
                         'Montoso_Edizione_2041_2070',
                         'Montoso_Edizione_2071_2100',
                         'Net_Change_Precipitation_Current_2030_Para_tif',
                         'Net_Change_Precipitation_Current_2050_Para_tif',
                         'NEWSOUTHWALES_1981_2010',
                         'NIZWA_OMAN_1981_2010',
                         'NOD_Tomato_Desert_Farms_1981_2010',
                         'NOD_Tomato_Desert_Farms_2011_2040',
                         'November_average_precipitation',
                         'OBISPO_MAITENCO_1981_2010',
                         'October_average_precipitation',
                         'Omo_Ethiopia_1981_2010',
                         'Omo_Ethiopia_1981_2010_Historical_to_Historical',
                         'Omo_Ethiopia_2011_2040',
                         'Omo_Ethiopia_Climate_Similarity_Model_Historical_to_2030',
                         'ONAGRI_1981_2010',
                         'OSM_Surface_Water_2021',
                         'OTERROIR_CURRENT_1981_2010',
                         'OUEDNJA_1981_2010',
                         'OULEDGANAOU_1981_2010',
                         'Paciencia_Grupo_Llano_1981_2010',
                         'Paciencia_Grupo_Llano_2011_2040',
                         'Paciencia_Grupo_Llano_2041_2070',
                         'Paciencia_Grupo_Llano_2071_2100',
                         'PALMIERDATTIER_1981_2010',
                         'PASTILLO_1981_2010',
                         'PCRGLOBWB2_BasinATLAS_Level9_m3yr_GP',
                         'PercentChangeAvgAnnualETCurrent2030_2005LandUse_EWEMBI',
                         'PHILIPPINESRICE_1981_2010',
                         'Pilcaniyeu_Argentina_2041_2070',
                         'Pilcaniyeu_Argentina_2071_2100',
                         'Pilcaniyeu_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Pilcaniyeu_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'PISTACHIOSSAMPLE_1981_2010',
                         'PORTERVILLE_2011_2040',
                         'PORTERVILLE_CURRENT_1981_2010',
                         'Precipitacion_anual_IDESA_tif',
                         'Precipitation_Annual_2040_tif',
                         'Precipitation_Annual_2070_tif',
                         'Precipitation_Change_Current_2040',
                         'Precipitation_Change_Current_2070',
                         'Project_Beisa_Precipitation_1981_2018',
                         'Project_Beisa_Precipitation_2011_2040',
                         'Project_Beisa_Temperature_1981_2018',
                         'Project_Beisa_Temperature_2011_2040',
                         'Quincy_Columbia_NE_1981_2010',
                         'Quincy_Columbia_NE_2011_2040',
                         'Quincy_Columbia_NE_2041_2070',
                         'Quincy_Columbia_NW_1981_2010',
                         'Quincy_Columbia_NW_2011_2040',
                         'Quincy_Columbia_NW_2041_2070',
                         'Quincy_Columbia_S_1981_2010',
                         'Quincy_Columbia_S_2011_2040',
                         'Quincy_Columbia_S_2041_2070',
                         'Raster_Test',
                         'Redencao_1981_2010',
                         'Redencao_2011_2040',
                         'Redencao_2041_2070',
                         'Relative_Change_Precipitation_Current_2030_tif',
                         'Relative_Change_Precipitation_Current_2050_Para_tif',
                         'Relative_Change_Temperature_Current_2040',
                         'Relative_Change_Temperature_Current_2070',
                         'Reus_1981_2010',
                         'Reus_2011_2040',
                         'Reus_2041_2070',
                         'REXBURG_1981_2010',
                         'RICHVALERICE_1981_2010',
                         'RioOso_complete',
                         'RioOso_Sutter_County',
                         'RioOso_Yuba_County',
                         'ROLDANILLO_1981_2010',
                         'Runoff_april_tif',
                         'Runoff_august_tif',
                         'Runoff_december_tif',
                         'Runoff_february_tif',
                         'Runoff_january_tif',
                         'Runoff_july_tif',
                         'Runoff_june_tif',
                         'Runoff_may_tif',
                         'Runoff_november_tif',
                         'Runoff_october_tif',
                         'Runoff_september_tif',
                         'Runoff_total_tif',
                         'SALALAH_DHOFAR_OMAN_1981_2010',
                         'SALINAS_USA_1981_2010',
                         'SALINAS_USA_2011_2040',
                         'SampleWorldCities',
                         'Santa_Marta_Argentina_2041_2070',
                         'Santa_Marta_Argentina_2071_2100',
                         'Santa_Marta_Argentina_Climate_Similarity_Historical_to_Historical',
                         'Santa_Marta_Argentina_Climate_Similarity_Model_Historical_to_2030',
                         'SantosTexas_1981_2010',
                         'SantosTexas_2011_2040',
                         'SantosTexas_2041_2070',
                         'SAOUDA_1981_2010',
                         'SDE_CHELSA_Pr_CF_11_1979_2019_2011_2040',
                         'SEGUNDA1_2_1981_2010',
                         'SEGUNDA3_4_1981_2010',
                         'September_average_precipitation',
                         'SHBAAM_gw',
                         'SHBAAM_sm',
                         'SHBAAM_sw',
                         'SHBAAM_swe',
                         'SHERRINGTON_QUEBEC_1981_2010',
                         'SHERRINGTON_QUEBEC_2011_2040',
                         'Slope_Balcarce',
                         'Slope_Condor',
                         'Slope_Cordillera',
                         'Slope_Coronel',
                         'Slope_Para',
                         'Slope_Para_Resampled',
                         'Soil_components',
                         'Soil_components_Para',
                         'Soil_moisture_change_cm_month_GRACE',
                         'Soil_moisture_change_m_month_GRACE_SHBAAM',
                         'Soil_texture',
                         'Soil_texture_Para',
                         'Soil_Thickness_3_Meters',
                         'South_Columbia_Basin_1981_2010',
                         'South_Columbia_Basin_2011_2040',
                         'South_Columbia_Basin_2041_2070',
                         'STAHALMADINA_1981_2010',
                         'Statewide_AEM_Survey_Coarse_Fraction_Depth_Slices_and_Average',
                         'Statewide_AEM_Survey_Electrical_Resistivity_Slices_and_Intervals',
                         'Surface_water_storage_change_cm_month_GRACE',
                         'TAFILET_CURRENT_1981_2010',
                         'TARPO_PARANATINGA_1981_2010',
                         'TARPO_PARANATINGA_2011_2040',
                         'TARPON_ALQ_TT_1981_2010',
                         'TARPON_ALQ_TT_2011_2040',
                         'TARPON_ALQ_TT_2041_2070',
                         'TARPON_ALQ_TT_2071_2100',
                         'TARPON_FARMOSA_1981_2010',
                         'TARPON_FARMOSA_2011_2040',
                         'TARPON_FARMOSA_2041_2070',
                         'TARPON_FARMOSA_2071_2100',
                         'TARPON_PARANATINGA_2041_2070',
                         'TARPON_PARANATINGA_2071_2100',
                         'Terra_Santa_1981_2010',
                         'Terra_Santa_2011_2040',
                         'Terra_Santa_2041_2070',
                         'Terrestrial_water_storage_cm_month_GRACE',
                         'Test_CacaoMars_SDEUser_2',
                         'Test_DBO_soilType100_200_RrrggisUser',
                         'Test_DBO_USDA_soilType_100_200_rrggisUser',
                         'Test_ESRI_raster_data',
                         'Test_Kecks_CA_Shared_As_Web_Layer',
                         'Test_Kecks_CA_Shared_From_DB',
                         'Test_Kecks_CA_Shared_From_DB_With_Copy',
                         'Test_Raster_Cacao_Physical',
                         'Test_Raster_from_RRGGIS_Connection',
                         'Test_SDE_soilType100_200_SDEUser',
                         'TIDDAS_1981_2010',
                         'Tome_Acu_Brazil_Nartura_1981_2010',
                         'Tome_Acu_Brazil_Nartura_2011_2040',
                         'Tome_Acu_Brazil_Nartura_2041_2070',
                         'Tome_Acu_Brazil_Nartura_2071_2100',
                         'Total_cumulative_change_in_GWS_m_GRACE_SHBAAM',
                         'Tres_Irmaos_1981_2010',
                         'Tres_Irmaos_2011_2040',
                         'Tres_Irmaos_2041_2070',
                         'TRIFFA_BERKANE_2011_2040',
                         'TRIFFABERKANE_1981_2010',
                         'TWIN_FALLS_1981_2010',
                         'URUGUAYRICE_1981_2010',
                         'USDA_SOILTYPE_0_5_Ethiopia',
                         'USDA_SOILTYPE_100_200_Ethiopia',
                         'USDA_SOILTYPE_15_30_Ethiopia',
                         'USDA_SOILTYPE_30_60_Ethiopia',
                         'USDA_SOILTYPE_5_15_Ethiopia',
                         'USDA_SOILTYPE_60_100_Ethiopia',
                         'VALE_OR_1981_2010',
                         'Valls_1_1981_2010',
                         'Valls_1_2011_2040',
                         'Valls_1_2041_2070',
                         'Valls_2_1981_2010',
                         'Valls_2_2011_2040',
                         'Valls_2_2041_2070',
                         'VITTORIA_ITALY_1981_2010',
                         'VITTORIA_ITALY_2011_2040',
                         'Vya_Grupo_Llano_1981_2010',
                         'Vya_Grupo_Llano_2011_2040',
                         'Vya_Grupo_Llano_2041_2070',
                         'Vya_Grupo_Llano_2071_2100',
                         'Wheat_Change_Current_to_Future',
                         'WHITEHILLSRANCH_1981_2010',
                         'WINDRISK500M',
                         'YUMA_2011_2040',
                         'YUMA_CURRENT_1981_2010']
'''
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filebasename = f'sharedinstances_{timestamp}'
output_directory = os.path.dirname(os.path.abspath(__file__))
output_directory = os.path.join(output_directory, 'Output')
if not os.path.exists(output_directory):
    os.makedirs(output_directory)
log_file_path = os.path.join(output_directory, f'{filebasename}.log')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(log_file_path, mode='w')
])


def parseInputParameters():
    parser = argparse.ArgumentParser(description='List and optionally update map services in an ArcGIS Server site.')
    parser.add_argument('--server', help='The URL of the ArcGIS Server site to work against. Only built-in authentication is supported.', default='https://maps.rrgnbs.com/arcgisserver')
    parser.add_argument('--user', help='Username of the administrative account', default='rrgadmin')
    parser.add_argument('--password', help='Password of the specified user account.') #, required=True)
    parser.add_argument('--update', action='store_true', help='Specify this parameter to change all Pro-based services from dedicated to shared instances.')
    args = parser.parse_args()
    if not args.password:
        from getpass import getpass
        args.password = getpass(f"**  Enter password for {args.user}: ")
    '''
    if not args.update:
        # ask the user if they want to update the services
        update = input("Do you want to update all the services to shared? (y/n): ")
        if update.lower() == 'y':
            args.update = True
        else:
            args.update = False
    '''
    return args

# A function that checks that the input JSON object is not an error object.    
def assertJsonSuccess(data):
    try:
        obj = json.loads(data)
        if 'status' in obj:
            if obj['status'] == "error":
                logging.error("Error: " + str(obj))
                return False
            elif obj['status'] == "success":
                return True
    except Exception as e:
        print("JSON object is not valid. " + str(e))
    try:
        # check if the word error is in the data as a string
        data_str = str(data)
        if 'error' in data_str:
            logging.error("Error: " + data_str)
            return False
        elif 'success' in data_str:
            return True
    except Exception as e:
        print('Not a valid string. ' + str(e))
    
    # check if data has no content
    if data is None or len(data) == 0:
        logging.error("Error: Object is empty.")
        return False
    
    # logging.error("Error: Unable to determine if success or error.")
    return True

def outputToFile(filename, data):
    try:
        try:
            data_to_output = json.dumps(data, indent=4)
            filename += '.json'
        except Exception as e:
            data_to_output = str(data)
            filename += '.txt'
        with open(os.path.join(output_directory, filename), 'w') as f:
            f.write(data_to_output)
    except Exception as e:
        logging.error("Error writing to file: " + str(e))

def listServices(server):
    arcMapSvcs = []
    dedicatedInstanceSvcs = []
    sharedInstanceSvcs = []
    svcsNeedPropertyUpdate = []
        
    for folder in server.services.folders:
        # skip the system folders
        if folder in ['Hosted', 'DataStoreCatalogs', 'System', 'Utilities']: continue
        
        for service in server.services.list(folder=folder):
            if service.properties['serviceName'] in servicesNeedingChange:
                outputToFile(f"{service.properties['serviceName']}_service_properties", service.properties)
                
            # bug reports suggest that some services don't have a type.. this is odd, but we skip them to avoid a crash
            if 'type' not in service.properties: continue
            
            # # skip everything that's not a map service; we don't support anything else in the shared pool at 10.7.x - 10.9.x
            # if service.properties['type'] != 'MapServer': continue
            if service.properties['type'] not in ['MapServer', 'FeatureServer', 'ImageServer']: continue
            # if service.properties['type'] not in ['ImageServer']: continue
            
            if 'properties' in service.properties:
                if 'path' in service.properties['properties']:
                    if service.properties['properties']['path'] == 'undefined':
                        logging.warning('Path is undefined. ServiceName: ' + service.properties['serviceName'])
            
            # the provider value is case-sensitive!
            # See https://developers.arcgis.com/rest/enterprise-administration/enterprise/deployment-default-properties/
            if service.properties['provider'] == 'ArcObjects': # provider='ArcObjects' means the service is running under the ArcMap runtime i.e. published from ArcMap
                arcMapSvcs.append(service)
            elif service.properties['provider'] == 'ArcObjects11': # provider='ArcObjects11' means the service is running under the ArcGIS Pro runtime i.e. published from ArcGIS Pro
                dedicatedInstanceSvcs.append(service)
            elif service.properties['provider'] == 'DMaps': # provider='DMaps' means the service is running in the shared instance pool (and thus running under the ArcGIS Pro provider runtime)
                sharedInstanceSvcs.append(service)
            elif service.properties['provider'] == 'ArcObjectsRasterRendering': # provider='ArcObjectsRasterRendering' means the image service is running in the shared instance pool
                sharedInstanceSvcs.append(service)
            else: pass # whoa nelly! unknown type of provider.. must be a fancy new server released after this script was written
    
    logging.info('*** ArcMap services ***')
    if len(arcMapSvcs) == 0:
        logging.info('There are no services published from ArcMap. Impressive!')
    else:
        logging.info('Services from ArcMap not eligible to run in the shared instance pool:')
        for service in arcMapSvcs:
            logging.info(f"- ServiceName: {service.properties['serviceName']}")
            try:
                output_text = f"Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
                logging.info(e)
            
            # imagine what uncommenting this would do..
            #if args.update:
            #   data = urllib.parse.urlencode({ 'token' : service._con.token, 'provider' : 'ArcObjects11', 'f' : 'json' }).encode('ascii')
            #   with urllib.request.urlopen(service.url + '/changeProvider', data) as f:
            #       print(f.read().decode('utf-8'))

    logging.info('*** ArcGIS Pro Shared instance services ***')
    if len(sharedInstanceSvcs) == 0:
        logging.info('There are no services published from ArcGIS Pro that are running in the shared instance pool.')
    else:
        logging.info('Services from ArcGIS Pro already running in the shared instance pool:')
        for service in sharedInstanceSvcs:
            try:
                output_text = f"- ServiceName: '{service.properties['serviceName']}'; Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
                # logging.info('Service instances per node min, max: ' + str(service.properties['minInstancesPerNode']) + ', ' + str(service.properties['maxInstancesPerNode']))
                if service.properties['minInstancesPerNode'] != 0 or service.properties['maxInstancesPerNode'] != 0:
                    # logging.info('Service instances min, max: ' + str(service.properties['properties'].get('minInstances')) + ', ' + str(service.properties['properties'].get('maxInstances')))
                    # logging.info(service.properties['properties'])
                    logging.warning('Shared service has more than 0 min/max instances. Needs to be updated.')
                    if service.properties['serviceName'] in servicesNeedingChange:
                        if args.update:
                            svcsNeedPropertyUpdate.append(service)
                        else:
                            logging.info('Service not updated because script is not in update mode.')
                    else:
                        logging.info('Service not updated because it is not in the list of services needing change.')
                else:
                    logging.info('Service path: ' + service.properties['properties'].get('path'))
                    if service.properties['properties'].get('path') == 'undefined':
                        logging.warning("Path equals 'undefined' for ServiceName: '" + service.properties['serviceName'])
                        if service.properties['serviceName'] in servicesNeedingChange:
                            if args.update:
                                svcsNeedPropertyUpdate.append(service)
                            else:
                                logging.info('Service not updated because script is not in update mode.')
                        else:
                            logging.info('Service not updated because it is not in the list of services needing change.')
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
                logging.info(e)
            
    logging.info('*** ArcGIS Pro Dedicated instance services ***')
    if len(dedicatedInstanceSvcs) == 0:
        logging.info('There are no services published from ArcGIS Pro that are running with dedicated instances.')
    else:
        logging.info('Services from ArcGIS Pro that may be eligible to run in the shared instance pool:')
        for service in dedicatedInstanceSvcs:
            serviceName = service.properties['serviceName']
            logging.info(f"- ServiceName: {serviceName}")
            
            try:
                output_text = f"Type: '{service.properties['type']}'; Provider: '{service.properties['provider']}'; minInstancesPerNode: '{service.properties['minInstancesPerNode']}'; maxInstancesPerNode: '{service.properties['maxInstancesPerNode']}'; minInstances: '{service.properties['properties'].get('minInstances')}'; maxInstances: '{service.properties['properties'].get('maxInstances')}'"
                logging.info(output_text)
            except Exception as e:
                logging.info('Error getting service properties for ' + service.properties['serviceName'])
            
            try:
                # switch Pro-based service to shared instance pool
                if serviceName in servicesNeedingChange:
                    if args.update:
                        # updating the provider can only be done via the dedicated changeProvider operation, it can't be  done by 
                        # simply editing the service properties directly (backwards compatibility concession to avoid older 
                        # ArcGIS Desktop clients from modifying this property incorrectly)
                        # if service is ImageServer, then provider='ArcObjectsRasterRendering' else, if not ImageServer, then provider='DMaps'
                        if service.properties['type'] == 'ImageServer':
                            provider_type = 'ArcObjectsRasterRendering'
                        else:
                            provider_type = 'DMaps'
                        data = urllib.parse.urlencode({ 'token' : service._con.token, 'provider' : provider_type, 'f' : 'json' }).encode('ascii')
                        logging.info(f"Changing provider for '{serviceName}' to '{provider_type}'")
                        with urllib.request.urlopen(service.url + '/changeProvider', data) as f:
                            results = f.read().decode('utf-8')
                            logging.info(results)
                            if assertJsonSuccess(results):
                                logging.info(f"Service '{serviceName}' changed to '{provider_type}' successfully.")
                                svcsNeedPropertyUpdate.append(service)
                            else:
                                logging.error(f"Service '{serviceName}' failed to change to {provider_type}.")
                    else:
                        logging.info('Service not updated because script is not in update mode.')
                else:
                    logging.info('Service not updated because it is not in the list of services needing change.')
            except Exception as e:
                logging.error(f'Error changing provider for {service.properties["serviceName"]}')
                logging.error(e)

    return svcsNeedPropertyUpdate


def changeProperties(services, minInstances=0, maxInstances=0):
    if not args.update:
        logging.info("Script is not in update mode. No properties will be changed.")
        return
    
    if len(services) == 0:
        logging.info("No services need property updates.")
        return
    
    logging.info("Change the properties for a service.")
    
    try:
        # get token from the first record of the services service._con.token
        token = services[0]._con.token
        if token == "":
            logging.error("Could not generate a token.")
            return
    except Exception as e:
        logging.error("Error getting token from the service.")
        logging.error(str(e))
        return
    
    try:
        # This request only needs the token and the response formatting parameter 
        # params = urllib.parse.urlencode({'token': token, 'f': 'json'})
        params = {'token': token, 'f': 'json'}
        headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
                
        for service in services:
            # Get the service name
            serviceName = service.properties['serviceName']
            logging.info("Checking instances for service: '" + serviceName + "'")
            try:
                serviceMinInstancesPerNode = service.properties['minInstancesPerNode']
                serviceMaxInstancesPerNode = service.properties['maxInstancesPerNode']
                logging.info('Service instances per node min, max:' + str(serviceMinInstancesPerNode) + ', ' + str(serviceMaxInstancesPerNode))
                
                serviceMinInstance = service.properties['properties'].get('minInstances')
                serviceMaxInstance = service.properties['properties'].get('maxInstances')
                logging.info('Service instances min, max:' + str(serviceMinInstance) + ', ' + str(serviceMaxInstance))
                
                servicePath = service.properties['properties'].get('path')
                logging.info('Service path: ' + str(servicePath))
                
                if (serviceMinInstancesPerNode != minInstances or serviceMaxInstancesPerNode != maxInstances or servicePath == 'undefined'):
                    serviceURL = service.url
                    
                    # Connect to service to get its current JSON definition 
                    logging.info("Reading service information...")
                    response = requests.post(serviceURL, data=params, headers=headers, verify=False)
                    if (response.status_code != 200):
                        logging.error("Could not read service information.")
                        logging.error(str(response))
                        continue
                        
                    data = response.text
                    
                    # Check that data returned is not an error object
                    if not assertJsonSuccess(data):          
                        logging.error("Error when reading service information. " + str(data))
                        continue
                    else:
                        logging.info("Service information read successfully. Now changing properties...")

                    # Deserialize response into Python object
                    dataObj = json.loads(data)
                    # logging.info("Service information: ")
                    # logging.info(dataObj)
                    outputToFile(f"{service.properties['serviceName']}_rest_service_information", dataObj)
                    
                    if (serviceMinInstancesPerNode != minInstances or serviceMaxInstancesPerNode != maxInstances):
                        logging.info("Changing service instances...")
                        # Edit desired properties of the service
                        dataObj["minInstancesPerNode"] = minInstances
                        dataObj["maxInstancesPerNode"] = maxInstances
                        
                        dataObj["properties"]["minInstances"] = minInstances
                        dataObj["properties"]["maxInstances"] = maxInstances
                    
                    if servicePath == 'undefined':
                        # remove path property from the service
                        logging.info("Removing undefined path property from the service...")
                        if 'path' in dataObj['properties']:
                            del dataObj['properties']['path']

                    # Serialize back into JSON
                    updatedSvcJson = json.dumps(dataObj)

                    # Call the edit operation on the service. Pass in modified JSON.
                    editSvcURL = serviceURL + "/edit"
                    params_edit = {'token': token, 'f': 'json', 'service': updatedSvcJson}
                    editResponse = requests.post(editSvcURL, data=params_edit, headers=headers, verify=False)
                    if (editResponse.status_code != 200):
                        logging.error("Error while executing edit.")
                        logging.error(str(editResponse))
                        continue
                    
                    # Check that data returned is not an error object
                    editData = editResponse.text
                    if not assertJsonSuccess(editData):
                        logging.error("Error returned while editing service: " + str(editData))
                        continue
                    logging.info(f'Response from edit: {editData}')
                    logging.info("Service edited successfully.")
                else:
                    logging.info("Service already has the desired properties.")
            except Exception as e:
                logging.error("Error while changing properties for service: " + serviceName)
                logging.error(str(e))
            
    except Exception as e:
        logging.error('Error while changing properties for service: ' + serviceName)
        logging.error(str(e))

    return


# Main script execution
logging.info('Starting script to list and optionally update map services in an ArcGIS Server site.')

args = parseInputParameters()

logging.info('Connecting to %s...' % args.server)
import arcgis.gis.server

connected = False
try:
    server = arcgis.gis.server.Server(args.server, username=args.user, password=args.password)
    connected = True
except Exception as e:
    logging.error('Error connecting to server: %s' % e)
    sys.exit(1)

logging.info("Connected, enumerating services...")
svcsNeedPropertyUpdate = listServices(server)

if args.update:
    changeProperties(svcsNeedPropertyUpdate, minInstances=0, maxInstances=0)

print('See log file for details: %s' % log_file_path)
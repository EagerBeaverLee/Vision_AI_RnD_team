import geopandas as gpd
ports_gdf = gpd.read_file('./src/my_battlefield_crew/data/spatial_data/major_ports.shp')
ports_gdf = ports_gdf.set_crs("EPSG:5179", allow_override=True).to_crs("EPSG:4326")
print(ports_gdf[ports_gdf['objnam'] == 'BUSAN HANG'].geometry.centroid)

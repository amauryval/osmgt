OsmGT
====

![CI](https://github.com/wiralyki/osmgt/workflows/CI/badge.svg?branch=master)
[![codecov](https://codecov.io/gh/wiralyki/osmgt/branch/master/graph/badge.svg)](https://codecov.io/gh/wiralyki/osmgt)


OpenStreetMap based on graph-tools

# How to install it 
```
conda install -c amauryval osmgt
```

# A (very) short documentation...

Check example.html example (doc is coming)


```Python
from osmgt import OsmGt

# 3 ways to get data

# GET POIs
poi_from_location = OsmGt.poi_from_location(
	"Lyon"
)

poi_from_bbox = OsmGt.poi_from_bbox(
	(-74.018433, 40.718087, -73.982749, 40.733356)
)

# 2 methods available:
poi_study_area_data_wkt = poi_from_bbox.study_area_geom()  # to get the shapely Polygon of the study data
poi_gdf = poi_from_bbox.get_gdf()  # to get the geodataframe containing all the POIs


# GET ROADS
roads_from_location = OsmGt.roads_from_location(
	"Lyon",
	mode="pedestrian",  # 'pedestrian' or 'vehicle' supported
	additionnal_nodes=None,  # optional, to connect nodes on the roads network (geodataframe or None)
)

roads_from_bbox = OsmGt.roads_from_bbox(
	(4.0237426757812, 46.019674567761, 4.1220188140869, 46.072575637028),
	mode="pedestrian",  # 'pedestrian' or 'vehicle' supported
	additionnal_nodes=None,  # optional, to connect nodes on the roads network (geodataframe or None)
)

# 3 methods available:
roads_study_area_data_wkt = roads_from_location.study_area_geom()  # to get the shapely Polygon of the study data
roads_gdf = roads_from_location.get_gdf()  # to get the geodataframe containing all the roads
roads_graph = roads_from_location.get_graph()  # to get the graph (graph-tool graph) of the osm network 
```

# How to use the graph ? 

Example: compute a shortest path

```Python
from osmgt import OsmGt
from graph_tool.topology import shortest_path

# get data
location_name = "Lyon"
mode = "pedestrian"
poi_from_location_gdf = OsmGt.poi_from_location(location_name).get_gdf()
roads_from_location = OsmGt.roads_from_location(location_name, mode=mode, additionnal_nodes=poi_from_location_gdf)

# get roads geodataframe and generate the graph
roads_from_location_gdf = roads_from_location.get_gdf()
graph = roads_from_location.get_graph()  # the graph-tool graph

# now, we have to define a start point and a end point and get their wkt
start_node_topo_uuid = 47
end_node_topo_uuid = 63

# 'topo_uuid' is generated by osmgt (during the topology processing). 
# Some roads has been split that's whyso this id has been created.
start_node_wkt = poi_from_location_gdf[poi_from_location_gdf['topo_uuid'] == start_node_topo_uuid].iloc[0]["geometry"].wkt
end_node_wkt = poi_from_location_gdf[poi_from_location_gdf['topo_uuid'] == end_node_topo_uuid].iloc[0]["geometry"].wkt

# the graph have some methods (graph-tools method always exists!) to find egdes, vertices... Let's use the .find_vertex_from_name(). the wkt is the vertex name...
source_vertex = graph.find_vertex_from_name(start_node_wkt)
target_vertex = graph.find_vertex_from_name(end_node_wkt)

# shortest path computing...
path_vertices, path_edges = shortest_path(
    graph,
    source=source_vertex,
    target=target_vertex,
    weights=graph.edge_weights  # weigth is based on line length
)

# get path by using edge names
roads_ids = [
    graph.edge_names[edge]
    for edge in path_edges
]
shortest_path_found = roads_from_location_gdf[roads_from_location_gdf['topo_uuid'].isin(roads_ids)]
```


# How to test it 
```
docker build -t osmgt . && docker run -p 8888:8888 osmgt:latest
```
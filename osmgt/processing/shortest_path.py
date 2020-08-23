from osmgt.compoments.roads import OsmGtRoads

from itertools import chain

import geopandas as gpd
import pandas as pd

try:
    from graph_tool.topology import shortest_path
except ModuleNotFoundError:
    pass

from shapely.geometry import Point
from shapely.geometry import LineString

from shapely.ops import linemerge
from shapely.wkt import loads


class OsmGtShortestPath(OsmGtRoads):
    def __init__(self, source_target_points):
        super().__init__()

        self._source_target_points = self._check_nodes(source_target_points)
        self._all_points = chain(*self._source_target_points)

        self._graph = None
        self._gdf = None
        self._additionnal_nodes_gdf = self._prepare_addtionnal_nodes()

    def _check_nodes(self, source_target_points):

        source_target_points_cleaned = set(
            [(source.wkt, target.wkt) for source, target in source_target_points]
        )

        source_target_points_cleaned = [
            (loads(source), loads(target))
            for source, target in source_target_points_cleaned
        ]

        return source_target_points_cleaned

    def _prepare_addtionnal_nodes(self):

        additionnal_nodes = [
            {self._TOPO_FIELD: enum, "geometry": geom}
            for enum, geom in enumerate(self._all_points)
        ]
        df = pd.DataFrame(additionnal_nodes)
        geometry = df["geometry"]
        additionnal_nodes_gdf = gpd.GeoDataFrame(
            df.drop(["geometry"], axis=1), crs=4326, geometry=geometry.to_list(),
        )

        return additionnal_nodes_gdf

    def from_location(self, location_name, additionnal_nodes=None, mode="pedestrian"):
        super().from_location(
            location_name, additionnal_nodes=self._additionnal_nodes_gdf, mode=mode
        )
        self._compute_data_and_graph()

        return self.get_gdf()

    def from_bbox(self, bbox_value, additionnal_nodes=None, mode="pedestrian"):
        super().from_bbox(bbox_value, additionnal_nodes, mode)
        self._compute_data_and_graph()

        return self.get_gdf()

    def _compute_data_and_graph(self):
        self._graph = super().get_graph()
        self._gdf = self.get_gdf()

        self._output_data = []
        # todo multithread it!
        # for nodes in self._source_target_points:
        #     self._compute_shortest_path(nodes)
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(4) as executor:
            executor.map(self._compute_shortest_path, self._source_target_points)

        return self.get_gdf()

    def _compute_shortest_path(self, nodes):
        source_node, target_node = nodes
        source_node_wkt = source_node.wkt
        target_node_wkt = target_node.wkt

        if source_node_wkt != target_node_wkt:
            source_vertex = self._graph.find_vertex_from_name(source_node_wkt)
            target_vertex = self._graph.find_vertex_from_name(target_node_wkt)

            self.logger.info(f"Compute path from {source_vertex} to {target_vertex}")

            # shortest path computing...
            _, path_edges = shortest_path(
                self._graph,
                source=source_vertex,
                target=target_vertex,
                weights=self._graph.edge_weights,  # weights is based on line length
            )

            gdf_copy = self._gdf.copy(deep=True)
            # # get path by using edge names
            path_geoms = gdf_copy[
                gdf_copy[self._TOPO_FIELD].isin(
                    [self._graph.edge_names[edge] for edge in path_edges]
                )
            ]["geometry"].to_list()

            # reorder linestring
            path_found = linemerge(path_geoms)
            if not Point(path_found.coords[0]).wkt == source_node_wkt:
                # we have to revert the coord order of the 1+ elements
                path_found = LineString(path_found.coords[::-1])

            self._output_data.append(
                {
                    "source_node": source_node,
                    "target_node": target_node,
                    "geometry": path_found,
                }
            )

        else:
            self.logger.info(
                f"Path from {source_node_wkt} to {target_node_wkt} are equals: not proceed!"
            )
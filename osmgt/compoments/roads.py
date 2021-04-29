import geopandas as gpd
from typing import Tuple
from typing import List
from typing import Optional
from typing import Dict

from osmgt.helpers.global_values import epsg_4326
from osmgt.helpers.global_values import forward_tag
from osmgt.helpers.global_values import topology_fields

from osmgt.compoments.core import OsmGtCore
from osmgt.compoments.core import EmptyData

from osmgt.geometry.network_topology import NetworkTopology

from osmgt.geometry.geom_helpers import compute_wg84_line_length
from osmgt.geometry.geom_helpers import linestring_points_fom_positions

from shapely.geometry import LineString
from shapely.geometry import Point

# to facilitate debugging
try:
    from osmgt.network.gt_helper import GraphHelpers
except ModuleNotFoundError:
    pass


from osmgt.helpers.global_values import network_queries


class NetWorkGeomIncompatible(Exception):
    pass


class AdditionalNodesOutsideWorkingArea(Exception):
    pass


class OsmGtRoads(OsmGtCore):

    _FEATURE_OSM_TYPE: str = "way"

    _OUTPUT_EXPECTED_GEOM_TYPE = "LineString"

    def __init__(self) -> None:
        super().__init__()

        self._mode = None

    def from_location(
        self,
        location_name: str,
        additional_nodes: Optional[gpd.GeoDataFrame],
        mode: str,
        interpolate_lines: bool = False,
    ) -> None:
        self._check_transport_mode(mode)
        super().from_location(location_name)
        self._mode = mode

        query = self._get_query_from_mode(mode)
        request = self._from_location_name_query_builder(self._location_id, query)
        raw_data = self._query_on_overpass_api(request)
        self._output_data = self.__build_network_topology(
            raw_data, additional_nodes, mode, interpolate_lines
        )

    def from_bbox(
        self,
        bbox_value: Tuple[float, float, float, float],
        additional_nodes: Optional[gpd.GeoDataFrame],
        mode: str,
        interpolate_lines: bool = False,
    ) -> None:
        self._check_transport_mode(mode)
        super().from_bbox(bbox_value)
        self._mode = mode

        query = self._get_query_from_mode(mode)
        request = self._from_bbox_query_builder(self._bbox_value, query)
        raw_data = self._query_on_overpass_api(request)
        self._output_data = self.__build_network_topology(
            raw_data, additional_nodes, mode, interpolate_lines
        )

    def get_graph(self) -> GraphHelpers:
        self.logger.info("Prepare graph")
        self._check_network_output_data()

        graph = GraphHelpers(
            self.logger, is_directed=network_queries[self._mode]["directed_graph"]
        )

        for feature in self._output_data:
            graph.add_edge(*self.__compute_edges(feature))

        return graph

    def _check_network_output_data(self):

        if len(self._output_data) == 0:
            raise EmptyData("Data is empty!")

        # here we check the first feature, all feature should have the same structure
        first_feature = self._output_data[0]
        assert (
            self._GEOMETRY_FIELD in first_feature
        ), f"{self._GEOMETRY_FIELD} key not found!"
        assert (
            first_feature[self._GEOMETRY_FIELD].geom_type
            == self._OUTPUT_EXPECTED_GEOM_TYPE
        ), f"{self._GEOMETRY_FIELD} key not found!"
        assert self._TOPO_FIELD in first_feature, f"{self._TOPO_FIELD} key not found!"

    def __compute_edges(self, feature: Dict) -> Tuple[str, str, str, float]:
        geometry = feature[self._GEOMETRY_FIELD]
        first_coords, *_, last_coords = geometry.coords
        return (
            Point(first_coords).wkt,
            Point(last_coords).wkt,
            feature[self._TOPO_FIELD],
            compute_wg84_line_length(geometry),
        )

    def __build_network_topology(
        self,
        raw_data: List[Dict],
        additional_nodes: Optional[gpd.GeoDataFrame],
        mode: str,
        interpolate_lines: bool,
    ) -> List[Dict]:
        if additional_nodes is not None:
            additional_nodes = self._check_topology_field(additional_nodes)
            # filter nodes from study_area_geom
            additional_nodes_mask = additional_nodes.intersects(self._study_area_geom)
            additional_nodes_filtered = additional_nodes.loc[additional_nodes_mask]

            if additional_nodes_filtered.shape[0] != additional_nodes.shape[0]:
                additional_nodes_outside = set(
                    map(lambda x: x.wkt, additional_nodes["geometry"].to_list())
                ).difference(
                    set(
                        map(
                            lambda x: x.wkt,
                            additional_nodes_filtered["geometry"].to_list(),
                        )
                    )
                )
                raise AdditionalNodesOutsideWorkingArea(
                    f"These following points are outside the working area: {', '.join(additional_nodes_outside)}"
                )

            additional_nodes = additional_nodes_filtered.to_dict("records")

        raw_data_restructured = self.__rebuild_network_data(raw_data)
        raw_data_topology_rebuild = NetworkTopology(
            self.logger,
            raw_data_restructured,
            additional_nodes,
            self._TOPO_FIELD,
            self._ID_OSM_FIELD,
            mode,
            interpolate_lines,
        ).run()

        return raw_data_topology_rebuild

    def __rebuild_network_data(self, raw_data: List[Dict]) -> List[Dict]:
        self.logger.info("Rebuild network data")

        raw_data = filter(
            lambda x: x[self._FEATURE_TYPE_OSM_FIELD] == self._FEATURE_OSM_TYPE,
            raw_data,
        )
        features: list = []
        for uuid_enum, feature in enumerate(raw_data, start=1):
            geometry = LineString(
                [
                    (coords[self._LNG_FIELD], coords[self._LAT_FIELD])
                    for coords in feature[self._GEOMETRY_FIELD]
                ]
            )
            del feature[self._GEOMETRY_FIELD]

            feature_build = self._build_feature_from_osm(uuid_enum, geometry, feature)
            features.append(feature_build)

        return features

    @staticmethod
    def _get_query_from_mode(mode: str) -> str:
        return network_queries[mode]["query"]

    def topology_checker(self) -> Dict[str, gpd.GeoDataFrame]:
        self.logger.info("Prepare topology data")

        network_gdf = super().get_gdf(verbose=False)

        lines_unchanged = network_gdf.loc[network_gdf["topology"] == "unchanged"]
        lines_added = network_gdf.loc[network_gdf["topology"] == "added"]
        if network_queries[self._mode]["directed_graph"]:
            nodes_added = network_gdf.loc[
                (network_gdf["topology"] == "added")
                & (network_gdf[self._TOPO_FIELD].str.contains(forward_tag))
            ]
        else:
            nodes_added = network_gdf.loc[network_gdf["topology"] == "added"]
        nodes_added = linestring_points_fom_positions(nodes_added, epsg_4326, [0])
        lines_split = network_gdf.loc[network_gdf["topology"] == "split"]
        intersections_added = linestring_points_fom_positions(
            network_gdf.loc[network_gdf["topology"] == "split"], epsg_4326, [0, -1]
        )

        return {
            "lines_unchanged": lines_unchanged[topology_fields],
            "lines_added": lines_added[topology_fields],
            "lines_split": lines_split[topology_fields],
            "nodes_added": nodes_added[topology_fields],
            "intersections_added": intersections_added[topology_fields],
        }

import warnings

import logging

from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple
from typing import Union

from osmgt.compoments.roads import OsmGtRoads

from osmgt.helpers.global_values import epsg_4326
from osmgt.helpers.global_values import epsg_3857
from osmgt.helpers.global_values import km_hour_2_m_sec
from osmgt.helpers.global_values import min_2_sec
from osmgt.helpers.global_values import distance_unit
from osmgt.helpers.global_values import time_unit
from osmgt.helpers.global_values import isochrone_display_mode
from osmgt.helpers.global_values import water_area_query

from osmgt.helpers.misc import find_list_dicts_from_key_and_value

import math

from operator import itemgetter

import geopandas as gpd
import pandas as pd

import itertools
from collections import Counter

from graph_tool.topology import shortest_distance

from shapely.wkt import loads
from shapely.geometry import Point
from shapely.geometry import MultiPoint
from shapely.geometry import Polygon
from shapely.geometry import MultiPolygon

from osmgt.geometry.geom_helpers import reprojection
from osmgt.geometry.geom_helpers import split_multiline_to_lines
from osmgt.geometry.geom_helpers import convert_to_polygon

from shapely.ops import unary_union

from osmgt.network.gt_helper import GraphHelpers

import concurrent.futures
from collections import Counter

warnings.simplefilter(action="ignore", category=UserWarning)


class IsochroneArgError(Exception):
    pass


class IsochroneGeomError(Exception):
    pass


class IsochroneError(Exception):
    pass


class OsmGtIsochrone(OsmGtRoads):
    logging.getLogger("geopandas.geodataframe").setLevel(logging.CRITICAL)

    __DISTANCE_TOLERANCE: float = 1.3
    __ISOCHRONE_NAME_FIELD: str = "iso_name"
    __ISODISTANCE_NAME_FIELD: str = "iso_distance"
    __DISSOLVE_NAME_FIELD: str = "__dissolve__"
    __TOPO_FIELD_REGEX_CLEANER: str = r"_[0-9]+$"
    __NETWORK_MASK: str = "topo_uuids"
    __DECIMAL_ROUNDED: int = 2

    __ROADS_BUFFER_EROSION_DIVISOR: int = 10

    __DEFAULT_CAPSTYLE: int = 1
    __DEFAULT_JOINSTYLE: int = 1

    __DISTANCE_UNIT_FIELD: str = "distance_unit"
    __TIME_UNIT_FIELD: str = "time_unit"

    def __init__(
        self,
        trip_speed: float,
        isochrones_times: Optional[List],
        distance_to_compute: Optional[List] = None,
        build_polygon: bool = True
    ) -> None:
        super().__init__()
        self.logger.info("Isochrone processing...")

        self.__topo_uuids: List[str] = []
        self._isochrones_data: List[Dict] = []
        self._source_vertex: Optional[str] = None
        self._location_point_reprojected_buffered_bounds: Optional[Tuple[float]] = None
        self._network_gdf: Optional[gpd.GeoDataFrame] = None
        self._graph: Optional[GraphHelpers] = None

        self._build_polygon = build_polygon
        self._display_mode_params = isochrone_display_mode

        # trip_speed in km/h
        self._speed_to_m_s: float = trip_speed / km_hour_2_m_sec

        if isochrones_times is None and distance_to_compute is None:
            raise IsochroneArgError(
                "class needs one of 'isochrones_times' and 'distance_to_compute'"
            )
        elif isochrones_times is not None and distance_to_compute is not None:
            raise IsochroneArgError(
                "class needs one of 'isochrones_times' and 'distance_to_compute'"
            )

        if isochrones_times is not None:
            self._isochrones_times = self._prepare_isochrone_values_from_times(
                isochrones_times
            )
        elif distance_to_compute is not None:
            self._isochrones_times = self._prepare_isochrone_values_from_distance(
                distance_to_compute
            )

    def _prepare_isochrone_values_from_times(self, isochrones_times: List) -> List:
        isochrones_times.sort()

        # iso time = min
        times_dist: Dict = {
            round(iso_time, self.__DECIMAL_ROUNDED): round(
                math.ceil((iso_time * min_2_sec) * self._speed_to_m_s),
                self.__DECIMAL_ROUNDED,
            )  # distance
            for iso_time in isochrones_times
        }
        return self._compute_isochrones_ingredient(times_dist)

    def _prepare_isochrone_values_from_distance(
        self, distance_to_compute: List
    ) -> List:
        distance_to_compute.sort()

        times_dist: Dict = {
            round(
                distance / self._speed_to_m_s / min_2_sec, self.__DECIMAL_ROUNDED
            ): round(
                distance, self.__DECIMAL_ROUNDED
            )  # distance
            for distance in distance_to_compute
        }
        return self._compute_isochrones_ingredient(times_dist)

    @staticmethod
    def _compute_isochrones_ingredient(input_ingredients: Dict) -> List:

        times_dist: List = sorted(
            input_ingredients.items(), key=lambda x: x[1], reverse=True
        )
        return times_dist

    def from_location_points(
        self, location_points: List[Point], mode: str
    ) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        self._mode = mode

        location_points = [
            loads(node)
            for node in set([point.wkt for point in location_points])
        ]

        points_bbox = MultiPoint(location_points)
        max_distance = max(self._isochrones_times, key=itemgetter(1))[-1]
        # compute bbox
        location_point_reproj = reprojection(points_bbox, epsg_4326, epsg_3857)
        location_point_reproj_buffered = location_point_reproj.buffer(
            max_distance * self.__DISTANCE_TOLERANCE
        )
        self._location_point_reprojected_buffered_bounds = reprojection(
            location_point_reproj_buffered, epsg_3857, epsg_4326
        ).bounds

        additional_nodes = [
            {self._TOPO_FIELD: idx, "geometry": location_point}
            for idx, location_point in enumerate(location_points)
        ]
        pois_df = pd.DataFrame(additional_nodes)

        geometry = pois_df["geometry"]
        additional_nodes_gdf = gpd.GeoDataFrame(
            pois_df.drop(["geometry"], axis=1),
            crs=int(epsg_4326),
            geometry=geometry.to_list(),
        )
        self.from_bbox(
            self._location_point_reprojected_buffered_bounds,
            additional_nodes=additional_nodes_gdf,
            mode=mode,
            interpolate_lines=True,
        )

        self.__get_water_area_from_osm()

        self._network_gdf = super().get_gdf()
        if self._network_gdf.shape[0] == 0:
            raise IsochroneError("None network found!")
        self._graph = self.get_graph()

        self._source_vertices = []
        for idx, location_point in enumerate(location_points):
            self._source_vertices.append(self._graph.find_vertex_from_name(location_point.wkt))

        # reset output else isochrone will be append
        self._output_data = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(self._compute_isochrone, self._isochrones_times)
        # to debug
        # for param in self._isochrones_times:
        #     self._compute_isochrone(param)

        self.__clean_network()
        if self._build_polygon:
            self.__clean_isochrones()

        self._OUTPUT_EXPECTED_GEOM_TYPE = "Polygon"  # mandatory

        isochrones_gdf = None
        if self._build_polygon:
            isochrones_gdf = self.get_gdf(verbose=False)

        return isochrones_gdf, self._network_gdf

    def _compute_isochrone(self, params) -> None:

        iso_time, dist = params
        self.logger.info(f"Compute isochrone: {iso_time} minutes => {dist} meters")

        points_found = []
        for source in self._source_vertices:
            _, pred = shortest_distance(
                self._graph,
                source=source,
                weights=self._graph.edge_weights,
                max_dist=dist,
                return_reached=True,
            )
            points_found.extend([self._graph.vertex_names[vertex] for vertex in pred])

        all_edges_found_topo_uuids_count = Counter(
            list(
                itertools.chain(
                    *[self._graph.find_edges_from_vertex(pt) for pt in points_found]
                )
            )
        )
        all_edges_found_topo_uuids = set(
            list(
                dict(
                    filter(
                        lambda x: x[1] > 1, all_edges_found_topo_uuids_count.items(),
                    )
                ).keys()
            )
        )

        network_mask = self._network_gdf["topo_uuid"].isin(all_edges_found_topo_uuids)


        if self._build_polygon:
            iso_polygon_computed = (
                self._network_gdf.loc[network_mask]
                .buffer(
                    self._display_mode_params["path_buffered"],
                    cap_style=self.__DEFAULT_CAPSTYLE,
                    join_style=self.__DEFAULT_JOINSTYLE,
                    resolution=self._display_mode_params["resolution"],
                )
                .unary_union
            )
            # we want to isolate subnetwork, so if we got a multipolygon it means that we have 2+ subnetwork
            if iso_polygon_computed.geom_type == "Polygon":
                iso_polygon_computed = MultiPolygon([iso_polygon_computed])

            output_iso_polygon = []
            for polyg in iso_polygon_computed.geoms:
                iso_polygon = polyg.buffer(  # merge them now
                    self._display_mode_params["dilatation"],
                    cap_style=self._display_mode_params["cap_style"],
                    join_style=self._display_mode_params["join_style"],
                    resolution=self._display_mode_params["resolution"],
                ).buffer(
                    self._display_mode_params["erosion"],
                    cap_style=self._display_mode_params["cap_style"],
                    join_style=self._display_mode_params["join_style"],
                    resolution=self._display_mode_params["resolution"],
                )
                iso_polygon = convert_to_polygon(iso_polygon)
                output_iso_polygon.extend(iso_polygon)

            iso_polygon = MultiPolygon(output_iso_polygon)

            # compute exterior
            iso_polygon = MultiPolygon(
                [
                    Polygon(iso_polygon_part.exterior)
                    for iso_polygon_part in convert_to_polygon(iso_polygon)
                ]
            )
        else:
            iso_polygon = None

        self._isochrones_data.append(
            {
                self.__ISOCHRONE_NAME_FIELD: iso_time,
                self.__TIME_UNIT_FIELD: time_unit,
                self.__ISODISTANCE_NAME_FIELD: dist,
                self.__DISTANCE_UNIT_FIELD: distance_unit,
                self.__NETWORK_MASK: network_mask,
                "geometry": iso_polygon,
            }
        )

    def __clean_network(self) -> None:
        # reverse order for isochrone, because isochrone mask is like russian dolls
        self._isochrones_data = sorted(
            self._isochrones_data,
            key=lambda k: k[self.__ISOCHRONE_NAME_FIELD],
            reverse=True,
        )
        for isochrone_computed in self._isochrones_data:
            self._network_gdf.loc[
                isochrone_computed[self.__NETWORK_MASK], self.__ISOCHRONE_NAME_FIELD
            ] = isochrone_computed[self.__ISOCHRONE_NAME_FIELD]
            self._network_gdf.loc[
                isochrone_computed[self.__NETWORK_MASK], self.__ISODISTANCE_NAME_FIELD
            ] = isochrone_computed[self.__ISODISTANCE_NAME_FIELD]
            del isochrone_computed[self.__NETWORK_MASK]

        self._network_gdf[self._TOPO_FIELD].replace(
            self.__TOPO_FIELD_REGEX_CLEANER, "", regex=True, inplace=True
        )

        self._network_gdf[self.__DISSOLVE_NAME_FIELD] = (
            self._network_gdf[self._TOPO_FIELD].astype(str)
            + "__"
            + self._network_gdf[self.__ISOCHRONE_NAME_FIELD].astype(str)
        )
        self._network_gdf = self._network_gdf.dissolve(
            by=self.__DISSOLVE_NAME_FIELD
        ).reset_index(drop=True)

        # convert multilinestring to LineStrings
        self._network_gdf = split_multiline_to_lines(
            self._network_gdf, epsg_4326, self._TOPO_FIELD
        )

        self._network_gdf = self._network_gdf[
            self._network_gdf[self.__ISOCHRONE_NAME_FIELD].notnull()
        ]

    def __clean_isochrones(self) -> None:
        # find iso index pair in order to create hole geom. isochrones are like russian dolls
        iso_values = sorted(
            list(map(lambda x: x[-1], self._isochrones_times)), reverse=True
        )
        iso_values_map: Dict = {
            x[0]: x[-1] for x in list(zip(iso_values, iso_values[1:]))
        }
        self._isochrones_built = []
        for iso_value_main_part, iso_value_part_to_remove in iso_values_map.items():
            # get main and part_to_remove isochrones
            iso_value_main_part_feature_idx: int = find_list_dicts_from_key_and_value(
                self._isochrones_data,
                self.__ISODISTANCE_NAME_FIELD,
                iso_value_main_part,
            )
            iso_value_part_to_remove_feature_idx: int = find_list_dicts_from_key_and_value(
                self._isochrones_data,
                self.__ISODISTANCE_NAME_FIELD,
                iso_value_part_to_remove,
            )

            iso_value_main_part_feature: Dict = self._isochrones_data[
                iso_value_main_part_feature_idx
            ]
            iso_value_part_to_remove_feature: Dict = self._isochrones_data[
                iso_value_part_to_remove_feature_idx
            ]

            # compute a raw isochrone
            isochrone_computed = iso_value_main_part_feature["geometry"].difference(
                iso_value_part_to_remove_feature["geometry"]
            )
            isochrone_computed = self.__improve_isochrone(
                isochrone_computed, iso_value_main_part_feature
            )

            # _isochrones_built will be used to remove roads outside of the proceed isochrone
            # and force last isochrones to be part of the current isochrone
            if len(self._isochrones_built) != 0:
                isochrone_computed = isochrone_computed.difference(
                    unary_union(self._isochrones_built)
                )
            self._isochrones_built.append(isochrone_computed)

            # finalize
            for iso_polygon_part in convert_to_polygon(isochrone_computed):
                iso_value_main_part_feature_copy = dict(iso_value_main_part_feature)
                iso_value_main_part_feature_copy["geometry"] = iso_polygon_part
                self._output_data.append(iso_value_main_part_feature_copy)

        # go here if there only 1 isochrone
        # should be the lowest, only 1
        isochrone_left = list(set(iso_values) - set(list(iso_values_map.keys())))
        assert len(isochrone_left) == 1
        last_iso_to_proceed_idx = find_list_dicts_from_key_and_value(
            self._isochrones_data, self.__ISODISTANCE_NAME_FIELD, isochrone_left[0]
        )
        last_iso_to_proceed_feature = self._isochrones_data[last_iso_to_proceed_idx]

        # get all isochrones to finish the last isochrone
        isochrones_to_remove = unary_union(self._isochrones_built)
        # compute the last isochrone
        isochrone_computed = last_iso_to_proceed_feature["geometry"].difference(
            isochrones_to_remove
        )

        if len(iso_values) == 1:
            isochrone_computed = self.__improve_isochrone(
                isochrone_computed, last_iso_to_proceed_feature
            )

        for isochrone_geom in convert_to_polygon(isochrone_computed):
            last_iso_to_proceed_feature_copy = dict(last_iso_to_proceed_feature)
            last_iso_to_proceed_feature_copy["geometry"] = isochrone_geom
            self._output_data.append(last_iso_to_proceed_feature_copy)

    def __improve_isochrone(
        self,
        isochrone_computed: Union[Polygon, MultiPolygon],
        current_main_isochrone: Dict,
    ) -> Union[Polygon, MultiPolygon]:
        # add roads on the raw isochrone to respect isochrone area
        iso_value_main_part_roads_buffered = (
            self._network_gdf.loc[
                self._network_gdf[self.__ISOCHRONE_NAME_FIELD]
                == current_main_isochrone[self.__ISOCHRONE_NAME_FIELD]
            ]
            .buffer(
                self._display_mode_params["path_buffered"],
                resolution=self._display_mode_params["resolution"],
                cap_style=self._display_mode_params["cap_style"],
            )
            .unary_union.buffer(
                self._display_mode_params["path_buffered"]
                / self.__ROADS_BUFFER_EROSION_DIVISOR,
                resolution=self._display_mode_params["resolution"],
            )
        )
        iso_value_main_part_roads_buffered = MultiPolygon(
            [
                iso_polygon_part
                for iso_polygon_part in convert_to_polygon(
                    iso_value_main_part_roads_buffered
                )
            ]
        )
        # remove water area
        isochrone_computed_without_water_area = isochrone_computed.difference(
            self._water_area
        )

        # finalize
        isochrone_computed = unary_union(
            [isochrone_computed_without_water_area, iso_value_main_part_roads_buffered]
        )

        return isochrone_computed

    def __get_water_area_from_osm(self) -> None:

        self.logger.info("Get water data from OSM")
        # get water area
        bbox_input: Tuple[float] = self._location_point_reprojected_buffered_bounds
        bbox_value = (bbox_input[1], bbox_input[0], bbox_input[3], bbox_input[2])
        request: str = self._from_bbox_query_builder(bbox_value, water_area_query)
        raw_data: List[Dict] = self._query_on_overpass_api(request)
        water_area: List[Polygon] = []
        for feature in raw_data:
            if feature["type"] == "relation":
                water_area.extend(
                    [
                        Polygon(
                            [(geom["lon"], geom["lat"]) for geom in member["geometry"]]
                        )
                        for member in feature["members"]
                    ]
                )
            else:
                if "geometry" in feature:
                    water_area.append(
                        Polygon(
                            [(geom["lon"], geom["lat"]) for geom in feature["geometry"]]
                        )
                    )
        self._water_area: Union[Polygon, MultiPolygon] = unary_union(water_area)

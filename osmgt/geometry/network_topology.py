from typing import Tuple
from typing import List
from typing import Dict
from typing import Optional
from typing import Set
from typing import Union
from typing import Iterator

from scipy import spatial

from shapely.geometry import LineString

import rtree

import numpy as np

from collections import Counter

from more_itertools import split_at

from numba import jit
from numba import types as nb_types

import concurrent.futures

from osmgt.helpers.global_values import forward_tag
from osmgt.helpers.global_values import backward_tag


class NetworkTopologyError(Exception):
    pass


class NetworkTopology:

    __INTERPOLATION_LEVEL: int = 7
    __INTERPOLATION_LINE_LEVEL: int = 4
    __NB_OF_NEAREST_LINE_ELEMENTS_TO_FIND: int = 10

    __NUMBER_OF_NODES_INTERSECTIONS: int = 2
    __ITEM_LIST_SEPARATOR_TO_SPLIT_LINE: str = "_"

    __CLEANING_FILED_STATUS: str = "topology"
    __GEOMETRY_FIELD: str = "geometry"
    __COORDINATES_FIELD: str = "coordinates"

    # OSM fields
    __ONEWAY_FIELD: str = "oneway"
    __ONEWAY_VALUE: str = "yes"
    __JUNCTION_FIELD: str = "junction"
    __JUNCTION_VALUES: List[str] = ["roundabout", "jughandle"]

    __TOPOLOGY_TAG_SPLIT: str = "split"
    __TOPOLOGY_TAG_ADDED: str = "added"
    __TOPOLOGY_TAG_UNCHANGED: str = "unchanged"

    __INSERT_OPTIONS: Dict = {"after": 1, "before": -1, None: 0}

    # ugly footway processing...
    # __PLACE_NODE_FIELD: str = "amenity"
    # __PLACE_NODE_DEFAULT_VALUE: str = "park_node"
    # __FOOTWAY_VALUE: str = "footway"
    # __TRUNK_VALUE: str = "trunk"
    # __HIGHWAY_FIELD: str = "highway"

    def __init__(
        self,
        logger,
        network_data: List[Dict],
        additional_nodes: Optional[List[Dict]],
        uuid_field: str,
        original_field_id: str,
        mode_post_processing: str,
        improve_line_output: bool = False,
    ) -> None:
        """

        :param logger:
        :type network_data: list of dict
        :type additional_nodes: list of dict
        :type uuid_field: str
        :type mode_post_processing: str
        """
        self.logger = logger
        self.logger.info("Network cleaning...")

        self.__topology_stats: dict = {"to add": 0, "to split": 0}

        self._network_data: Union[List[Dict], Dict] = self._check_inputs(network_data)
        self._mode_post_processing = mode_post_processing
        self._improve_line_output = improve_line_output  # link to __INTERPOLATION_LINE_LEVEL

        self._additional_nodes = additional_nodes
        if self._additional_nodes is None:
            self._additional_nodes: Dict = {}

        # ugly footway processing...
        # self._force_footway_connection = False

        self.__FIELD_ID = uuid_field  # have to be an integer.. thank rtree...
        self._original_field_id = original_field_id

        self._intersections_found: Optional[Set[Tuple[float, float]]] = None
        self.__connections_added: Dict = {}
        self._output: List[Dict] = []

    def run(self) -> List[Dict]:
        self._prepare_data()

        # ugly footway processing...
        # if self._force_footway_connection:
        #     self.prepare_footway_nodes()

        # connect all the added nodes
        if len(self._additional_nodes) > 0:
            self.compute_added_node_connections()

        # find all the existing intersection from coordinates
        self._intersections_found = set(self.find_intersections_from_ways())

        self.logger.info("Build lines")
        for feature in self._network_data.values():
            self.build_lines(feature)

        return self._output

    # def prepare_footway_nodes(self) -> None:
    #     import itertools
    #
    #     # # add this into __get_nearest_line method
    #     # if node.get(self.__HIGHWAY_FIELD , None) not in [self.__FOOTWAY_VALUE , self.__TRUNK_VALUE]:
    #     #     self.__NB_OF_NEAREST_LINE_ELEMENTS_TO_FIND = 2
    #     # else:
    #     #     self.__NB_OF_NEAREST_LINE_ELEMENTS_TO_FIND = 1
    #
    #     network_data_footway = list(
    #         filter(lambda x: x[self.__HIGHWAY_FIELD] == self.__FOOTWAY_VALUE if self.__HIGHWAY_FIELD in x else None, self._network_data.values()))
    #
    #     all_fl_coord_points_footway = list(itertools.chain(*[
    #         feature[self.__COORDINATES_FIELD][::len(feature[self.__COORDINATES_FIELD]) - 1]
    #         for feature in network_data_footway
    #     ]))
    #     all_fl_coord_points_footway2 = Counter(all_fl_coord_points_footway)
    #     coord_fl_points_footway_intersections_found = list(
    #         filter(
    #             lambda x: x[1] == 1 ,
    #             all_fl_coord_points_footway2.items() ,
    #         )
    #     )
    #     all_unique_fl_points = [
    #         value[0]
    #         for value in coord_fl_points_footway_intersections_found
    #     ]
    #     ########
    #
    #     all_coord_points_footway = list(itertools.chain(*[
    #         feature[self.__COORDINATES_FIELD]
    #         for feature in network_data_footway
    #     ]))
    #
    #     all_coord_points_footway2 = Counter(all_coord_points_footway)
    #     coord_points_footway_intersections_found = list(
    #         filter(
    #             lambda x: x[1] == 1 ,
    #             all_coord_points_footway2.items() ,
    #         )
    #     )
    #     all_unique_points = [
    #         value[0]
    #         for value in coord_points_footway_intersections_found
    #     ]
    #
    #     nodes_footway_bounds = set(all_unique_points).intersection(set(all_unique_fl_points))
    #     footway_additional_nodes = {
    #         len(self._additional_nodes) + idx: {
    #             self.__COORDINATES_FIELD: coords,
    #             self.__FIELD_ID: len(self._additional_nodes) + idx,
    #             self.__GEOMETRY_FIELD: Point([coords]),
    #             self.__PLACE_NODE_FIELD: self.__PLACE_NODE_DEFAULT_VALUE
    #         }
    #         for idx, coords in enumerate(nodes_footway_bounds , start=1)  # take care if additional node is none
    #     }
    #     self._additional_nodes = {**self._additional_nodes , **footway_additional_nodes}

    def build_lines(self, feature: Dict) -> None:
        # compare line coords and intersections points
        coordinates_list = set(feature[self.__COORDINATES_FIELD])
        points_intersections: Set[Tuple[float, float]] = coordinates_list.intersection(
            self._intersections_found
        )

        # rebuild linestring
        if len(set(feature[self.__COORDINATES_FIELD])) > 1:
            lines_coordinates_rebuild = self._topology_builder(
                feature[self.__COORDINATES_FIELD], points_intersections
            )

            if len(lines_coordinates_rebuild) > 1:

                for new_suffix_id, line_coordinates in enumerate(
                    lines_coordinates_rebuild
                ):
                    feature_updated = dict(feature)
                    feature_updated[
                        self.__FIELD_ID
                    ] = f"{feature_updated[self.__FIELD_ID]}_{new_suffix_id}"
                    feature_updated[
                        self.__CLEANING_FILED_STATUS
                    ] = self.__TOPOLOGY_TAG_SPLIT
                    feature_updated[self.__COORDINATES_FIELD] = line_coordinates

                    new_features = self.mode_processing(feature_updated)
                    self._output.extend(new_features)
            else:
                # nothing to change
                feature[self.__FIELD_ID] = feature[self.__FIELD_ID]
                new_features = self.mode_processing(feature)
                self._output.extend(new_features)

    def mode_processing(self, input_feature):
        new_elements = []

        if self._mode_post_processing == "vehicle":
            # by default
            new_forward_feature = self._direction_processing(input_feature, forward_tag)
            new_elements.extend(new_forward_feature)
            if input_feature.get(self.__JUNCTION_FIELD, None) in self.__JUNCTION_VALUES:
                return new_elements

            if input_feature.get(self.__ONEWAY_FIELD, None) != self.__ONEWAY_VALUE:

                new_backward_feature = self._direction_processing(
                    input_feature, backward_tag
                )
                new_elements.extend(new_backward_feature)

        elif self._mode_post_processing == "pedestrian":
            # it's the default behavior

            feature = self._direction_processing(input_feature)
            new_elements.extend(feature)

        return new_elements

    def _direction_processing(
        self, input_feature: Dict, direction: Optional[str] = None
    ):
        new_features = []
        input_feature_copy = dict(input_feature)

        if self._improve_line_output:
            new_coords = list(
                self._split_line(input_feature_copy, self.__INTERPOLATION_LINE_LEVEL)
            )
            new_lines_coords = list(zip(new_coords, new_coords[1:]))
            del input_feature_copy[self.__COORDINATES_FIELD]

            for idx, sub_line_coords in enumerate(new_lines_coords):
                new_features.append(
                    self.__proceed_direction_geom(
                        direction, input_feature_copy, sub_line_coords, idx
                    )
                )
        else:
            new_coords = list(self._split_line(input_feature_copy, 1))
            del input_feature_copy[self.__COORDINATES_FIELD]
            new_features.append(
                self.__proceed_direction_geom(direction, input_feature_copy, new_coords)
            )

        return new_features

    def __proceed_direction_geom(
        self, direction, input_feature, sub_line_coords, idx=None
    ):
        feature = dict(input_feature)

        if idx is not None:
            idx = f"_{idx}"
        else:
            idx = ""

        if direction == "backward":
            new_linestring = LineString(sub_line_coords[::-1])
        elif direction in ["forward", None]:
            new_linestring = LineString(sub_line_coords)
        else:
            raise NetworkTopologyError(f"Direction issue: value '{direction}' found")
        feature[self.__GEOMETRY_FIELD] = new_linestring

        if direction is not None:
            feature[self.__FIELD_ID] = f"{feature[self.__FIELD_ID]}{idx}_{direction}"
        else:
            feature[self.__FIELD_ID] = f"{feature[self.__FIELD_ID]}{idx}"

        return feature

    def _split_line(self, feature: Dict, interpolation_level: int) -> List:
        new_line_coords = interpolate_curve_based_on_original_points(
            np.array(feature[self.__COORDINATES_FIELD]), interpolation_level,
        )
        return new_line_coords

    def _prepare_data(self):

        self._network_data = {
            feature[self.__FIELD_ID]: {
                **{self.__COORDINATES_FIELD: feature[self.__GEOMETRY_FIELD].coords[:]},
                **feature,
                **{self.__CLEANING_FILED_STATUS: self.__TOPOLOGY_TAG_UNCHANGED},
            }
            for feature in self._network_data
        }
        if self._additional_nodes is not None:
            self._additional_nodes = {
                feature[self.__FIELD_ID]: {
                    **{
                        self.__COORDINATES_FIELD: feature[self.__GEOMETRY_FIELD].coords[
                            0
                        ]
                    },
                    **feature,
                }
                for feature in self._additional_nodes
            }

    def compute_added_node_connections(self):
        self.logger.info("Starting: Adding new nodes on the network")

        self.logger.info("Find nearest line for each node")
        node_keys_by_nearest_lines_filled = (
            self.__find_nearest_line_for_each_key_nodes()
        )

        self.logger.info("Split line")
        # for nearest_line_key in node_keys_by_nearest_lines_filled:
        #     self.split_line(nearest_line_key)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(self.split_line, node_keys_by_nearest_lines_filled)

        self._network_data: Dict = {**self._network_data, **self.__connections_added}

        self.logger.info(
            f"Topology lines checker: {', '.join([f'{key}: {value}' for key, value in self.__topology_stats.items()])}"
        )

    def split_line(self, node_key_by_nearest_lines):
        nearest_line_content = self.__node_by_nearest_lines[node_key_by_nearest_lines]
        default_line_updater = self.proceed_nodes_on_network(
            (node_key_by_nearest_lines, nearest_line_content)
        )
        if default_line_updater is not None:
            self.insert_new_nodes_on_its_line(default_line_updater)

    def insert_new_nodes_on_its_line(self, item):
        original_line_key = item["original_line_key"]
        end_points_found = item["end_points_found"]

        linestring_with_new_nodes = self._network_data[original_line_key][
            self.__COORDINATES_FIELD
        ]
        linestring_with_new_nodes.extend(end_points_found)
        linestring_with_new_nodes = set(linestring_with_new_nodes)
        self.__topology_stats["to split"] += len(
            linestring_with_new_nodes.intersection(end_points_found)
        )

        # build new LineStrings
        linestring_linked_updated = list(
            filter(lambda x: x in linestring_with_new_nodes, item["interpolated_line"],)
        )

        self._network_data[original_line_key][
            self.__COORDINATES_FIELD
        ] = linestring_linked_updated

    def proceed_nodes_on_network(self, nearest_line_content):
        nearest_line_key, node_keys = nearest_line_content

        interpolated_line_coords = interpolate_curve_based_on_original_points(
            np.array(self._network_data[nearest_line_key][self.__COORDINATES_FIELD]),
            self.__INTERPOLATION_LEVEL,
        )
        line_tree = spatial.cKDTree(interpolated_line_coords)
        interpolated_line_coords_rebuilt = list(map(tuple, interpolated_line_coords))

        nodes_coords = [
            self._additional_nodes[node_key][self.__COORDINATES_FIELD]
            for node_key in node_keys
        ]
        _, nearest_line_object_idxes = line_tree.query(nodes_coords)
        end_points_found = [
            interpolated_line_coords_rebuilt[nearest_line_key]
            for nearest_line_key in nearest_line_object_idxes
        ]

        connections_coords = list(
            zip(node_keys, list(zip(nodes_coords, end_points_found)))
        )
        self.__topology_stats["to add"] += len(connections_coords)

        connections_coords_valid = list(
            filter(lambda x: len(set(x[-1])) > 0, connections_coords)
        )
        for node_key, connection in connections_coords_valid:

            # to split line at node (and also if node is on the network). it builds intersection used to split lines
            # additional are converted to lines
            self.__connections_added[f"from_node_id_{node_key}"] = {
                self.__COORDINATES_FIELD: connection,
                self.__GEOMETRY_FIELD: connection,
                self.__CLEANING_FILED_STATUS: self.__TOPOLOGY_TAG_ADDED,
                self.__FIELD_ID: f"{self.__TOPOLOGY_TAG_ADDED}_{node_key}",
                self._original_field_id: f"{self.__TOPOLOGY_TAG_ADDED}_{node_key}",
            }

        return {
            "interpolated_line": interpolated_line_coords_rebuilt,
            "original_line_key": nearest_line_key,
            "end_points_found": end_points_found,
        }

    def _topology_builder(
        self,
        coordinates: List[Tuple[float, float]],
        points_intersections: Set[Tuple[float, float]],
    ):

        is_rebuild = False
        coordinates_updated: List[List[Tuple[float, float]]] = []

        # split coordinates found at intersection to respect the topology
        first_value, *middle_coordinates_values, last_value = coordinates
        for point_intersection in points_intersections:

            point_intersection = tuple(point_intersection)

            if point_intersection in middle_coordinates_values:
                # we get the middle values from coordinates to avoid to catch the first and last value when editing

                middle_coordinates_values = self._insert_value(
                    middle_coordinates_values,
                    point_intersection,
                    tuple([point_intersection]),
                )

                middle_coordinates_values = self._insert_value(
                    middle_coordinates_values,
                    point_intersection,
                    self.__ITEM_LIST_SEPARATOR_TO_SPLIT_LINE,
                    "after",
                )
                coordinates = [first_value] + middle_coordinates_values + [last_value]
                is_rebuild = True

        if is_rebuild:
            coordinates_updated = list(split_at(coordinates, lambda x: x == "_"))

        if not is_rebuild:
            coordinates_updated = list([coordinates])

        return coordinates_updated

    def find_intersections_from_ways(self) -> Set[Tuple[float, float]]:
        self.logger.info("Starting: Find intersections")
        all_coord_points = Counter(
            [
                coords
                for feature in self._network_data.values()
                for coords in feature[self.__COORDINATES_FIELD]
            ],
        )

        intersections_found = dict(
            filter(
                lambda x: x[1] >= self.__NUMBER_OF_NODES_INTERSECTIONS,
                all_coord_points.items(),
            )
        ).keys()
        self.logger.info("Done: Find intersections")

        return set(intersections_found)

    def __rtree_generator_func(
        self,
    ) -> Iterator[Tuple[int, Tuple[str, str, str, float], None]]:
        for fid, feature in self._network_data.items():
            # fid is an integer
            yield fid, feature[self.__GEOMETRY_FIELD].bounds, None

    def __find_nearest_line_for_each_key_nodes(self) -> Iterator[int]:
        # find the nearest network arc to interpolate
        self.__tree_index = rtree.index.Index(self.__rtree_generator_func())

        # find nearest line
        self.__node_by_nearest_lines = dict(
            (key, []) for key in self._network_data.keys()
        )

        # not working because rtree cannot be MultiThreaded
        # with concurrent.futures.ThreadPoolExecutor(4) as executor:
        #     executor.map(self.__get_nearest_line, self._additional_nodes.items())
        for node_info in self._additional_nodes.items():
            self.__get_nearest_line(node_info)

        node_keys_by_nearest_lines_filled = filter(
            lambda x: len(self.__node_by_nearest_lines[x]) > 0,
            self.__node_by_nearest_lines,
        )

        return node_keys_by_nearest_lines_filled

    def __get_nearest_line(self, node_info: Tuple[int, Dict]) -> None:
        node_uuid, node = node_info
        distances_computed: List[Tuple[float, int]] = []
        node_geom = node[self.__GEOMETRY_FIELD]

        for index_feature in self.__tree_index.nearest(
            node_geom.bounds, self.__NB_OF_NEAREST_LINE_ELEMENTS_TO_FIND
        ):
            line_geom = self._network_data[index_feature][self.__GEOMETRY_FIELD]
            distance_from_node_to_line = node_geom.distance(line_geom)
            if distance_from_node_to_line == 0:
                # means that we node is on the network, looping is not necessary anymore
                distances_computed = [(distance_from_node_to_line, index_feature)]
                break
            distances_computed.append((distance_from_node_to_line, index_feature))

        _, line_min_index = min(distances_computed)
        self.__node_by_nearest_lines[line_min_index].append(node_uuid)

    @staticmethod
    def _check_inputs(inputs: List[Dict]) -> List[Dict]:
        assert len(inputs) > 0
        return inputs

    def _insert_value(
        self,
        list_object: List[Tuple[float, float]],
        search_value: Tuple[float, float],
        value_to_add: Union[str, Tuple[Tuple[float, float]]],
        position: Optional[str] = None,
    ) -> List[Tuple[float, float]]:

        assert position in self.__INSERT_OPTIONS.keys()

        index_increment = self.__INSERT_OPTIONS[position]
        index: int = list_object.index(search_value) + index_increment
        list_object[index:index] = value_to_add

        return list_object


signature_interpolation_func = nb_types.Array(nb_types.float64, 2, "C")(
    nb_types.Array(nb_types.float64, 2, "C"), nb_types.int64
)


@jit(signature_interpolation_func, nopython=True, nogil=True, cache=True)
def interpolate_curve_based_on_original_points(x, n):
    # source :
    # https://stackoverflow.com/questions/31243002/higher-order-local-interpolation-of-implicit-curves-in-python/31335255
    if n > 1:
        m = 0.5 * (x[:-1] + x[1:])
        if x.ndim == 2:
            m_size = (x.shape[0] + m.shape[0], x.shape[1])
        else:
            raise NotImplementedError
        x_new = np.empty(m_size, dtype=x.dtype)
        x_new[0::2] = x
        x_new[1::2] = m
        return interpolate_curve_based_on_original_points(x_new, n - 1)

    elif n == 1:
        return x

    else:
        raise ValueError

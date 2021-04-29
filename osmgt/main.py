import geopandas as gpd
from shapely.geometry import Point

from osmgt.compoments.roads import OsmGtRoads
from osmgt.compoments.poi import OsmGtPoi

from osmgt.processing.isochrone import OsmGtIsochrone
from osmgt.processing.shortest_path import OsmGtShortestPath

from typing import Tuple
from typing import List
from typing import Optional
from typing import Union


class OsmgGtLimit(Exception):
    pass


class OsmGt:
    @staticmethod
    def roads_from_location(
        location_name: str,
        mode: str = "pedestrian",
        additional_nodes: Optional[gpd.GeoDataFrame] = None,
    ) -> OsmGtRoads:
        """
        Get OpenStreetMap roads from a location name

        :param location_name: the name of the location
        :type location_name: the name of the location
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :param additional_nodes: additional nodes to connect on the network
        :type additional_nodes: geopandas.GeoDataFrame
        :return: OsmGtRoads class
        :rtype: OsmGtRoads
        """
        osm_road = OsmGtRoads()
        osm_road.from_location(location_name, additional_nodes, mode)
        return osm_road

    @staticmethod
    def roads_from_bbox(
        bbox_value: Tuple[float, float, float, float],
        mode: str = "pedestrian",
        additional_nodes: Optional[gpd.GeoDataFrame] = None,
    ) -> OsmGtRoads:
        """
        Get OpenStreetMap roads from a bbox

        :param bbox_value: a bbox value : (min_x , min_y , max_x , max_y) or (min_lng, min_lat, max_lng, max_lat)
        :type bbox_value: tuple of float
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :param additional_nodes: additional nodes to connect on the network
        :type additional_nodes: geopandas.GeoDataFrame
        :return: OsmGtRoads class
        :rtype: OsmGtRoads
        """
        osm_road = OsmGtRoads()
        osm_road.from_bbox(bbox_value, additional_nodes, mode)
        return osm_road

    @staticmethod
    def pois_from_location(location_name: str) -> OsmGtPoi:
        """
        Find OSM POIs from a location name

        :param location_name: a location name
        :type location_name: str
        :return: OsmGtRoads class
        :rtype: OsmGtRoads
        """
        osm_poi = OsmGtPoi()
        osm_poi.from_location(location_name,)
        return osm_poi

    @staticmethod
    def pois_from_bbox(bbox_values: Tuple[float, float, float, float]) -> OsmGtPoi:
        """
        Find OSM POIs from a bbox value

        :param bbox_values: a bbox value : (min_x , min_y , max_x , max_y) or (min_lng, min_lat, max_lng, max_lat)
        :type bbox_values: tuple of float
        :return: OsmGtRoads class
        :rtype: OsmGtRoads
        """
        osm_poi = OsmGtPoi()
        osm_poi.from_bbox(bbox_values)
        return osm_poi

    @staticmethod
    def isochrone_times_from_nodes(
        source_nodes: List[Point],
        isochrones_times: List[Union[int, float]],
        trip_speed: float,
        mode: str = "pedestrian",
    ) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """
        :param source_nodes: location points
        :type source_nodes: shapely.geometry.Point
        :param isochrones_times: isochrones to build (in minutes)
        :type isochrones_times: list of int
        :param trip_speed: trip speed in km/h
        :type trip_speed: int
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :return: 2 GeoDataframe : isochrones polygons and isochrones lines (roads)
        :rtype: tuple(geopandas.GeoDataFrame)
        """

        min_time = 1
        if min(isochrones_times) < min_time:
            raise OsmgGtLimit(f"Minimal distance must be >= {min_time} minutes")

        isochrone_polygons_gdf, isochrone_lines_gdf = OsmGtIsochrone(
            trip_speed, isochrones_times
        ).from_location_points(source_nodes, mode)

        return isochrone_polygons_gdf, isochrone_lines_gdf

    @staticmethod
    def isochrone_distances_from_nodes(
        source_nodes: List[Point],
        distances: List[Union[int, float]],
        trip_speed: float,
        mode: str = "pedestrian",
    ) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """
        :param source_nodes: location points
        :type source_nodes: shapely.geometry.Point
        :param distances: distances (meters)
        :type distances: list of int
        :param trip_speed: trip speed in km/h
        :type trip_speed: int
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :return: 2 GeoDataframe : isochrones polygons and isochrones lines (roads)
        :rtype: tuple(geopandas.GeoDataFrame)
        """
        min_distance = 20
        if min(distances) < min_distance:
            raise OsmgGtLimit(f"Minimal distance must be >= {min_distance} meters")

        isochrone_polygons_gdf, isochrone_lines_gdf = OsmGtIsochrone(
            trip_speed, None, distances
        ).from_location_points(source_nodes, mode)

        return isochrone_polygons_gdf, isochrone_lines_gdf

    @staticmethod
    def shortest_path_from_location(
        location_name: str,
        source_target_points: List[Tuple[Point, Point]],
        mode: str = "pedestrian",
    ) -> gpd.GeoDataFrame:
        """

        :param location_name: the name of the location
        :type location_name: the name of the location
        :param source_target_points: list of tuple source and target points
        :type source_target_points: list of tuple (shapely.geometry.Point)
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :return: GeoDataframe containing all the shortest paths
        :rtype: geopandas.GeoDataFrame
        """

        return OsmGtShortestPath(source_target_points).from_location(
            location_name, None, mode
        )

    @staticmethod
    def shortest_path_from_bbox(
        bbox_value: Tuple[float, float, float, float],
        source_target_points: List[Tuple[Point, Point]],
        mode: str = "pedestrian",
    ) -> gpd.GeoDataFrame:
        """

        :param bbox_value: a bbox value : (min_x , min_y , max_x , max_y) or (min_lng, min_lat, max_lng, max_lat)
        :type bbox_value: tuple of float
        :param source_target_points: list of tuple source and target points
        :type source_target_points: list of tuple (shapely.geometry.Point)
        :param mode: the transport mode
        :type mode: str, default 'pedestrian', one of : pedestrian, vehicle
        :return: GeoDataframe containing all the shortest paths
        :rtype: geopandas.GeoDataFrame
        """

        return OsmGtShortestPath(source_target_points).from_bbox(bbox_value, None, mode)

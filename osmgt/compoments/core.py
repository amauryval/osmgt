from typing import Tuple
from typing import List
from typing import Optional
from typing import Dict
from typing import Union

import pandas as pd
import geopandas as gpd

from osmgt.helpers.logger import Logger

from osmgt.apis.nominatim import NominatimApi
from osmgt.apis.overpass import OverpassApi

from osmgt.helpers.global_values import network_queries
from osmgt.helpers.global_values import epsg_4326
from osmgt.helpers.global_values import out_geom_query

from shapely.geometry import Point
from shapely.geometry import LineString
from shapely.geometry import Polygon
from shapely.geometry import box

from osmgt.helpers.global_values import osm_url

from osmgt.helpers.misc import chunker


class ErrorOsmGtCore(Exception):
    pass


class IncompatibleFormat(Exception):
    pass


class EmptyData(Exception):
    pass


class OsmGtCore(Logger):

    _QUERY_ELEMENTS_FIELD: str = "elements"
    __USELESS_COLUMNS: List = []
    _location_id: Optional[int] = None

    _NOMINATIM_DEFAULT_ID: int = 3600000000  # this is it
    _NOMINATIM_OSM_ID_FIELD: str = "osm_id"
    _NOMINATIM_NUMBER_RESULT: str = 1
    _NOMINATIM_GEOJSON_FIELD: str = "geojson"
    _DEFAULT_NAN_VALUE_TO_USE: str = "None"

    _GEOMETRY_FIELD: str = "geometry"
    _LAT_FIELD: str = "lat"
    _LNG_FIELD: str = "lon"

    _TOPO_FIELD: str = "topo_uuid"

    _FEATURE_TYPE_OSM_FIELD: str = "type"
    _PROPERTIES_OSM_FIELD: str = "tags"
    _ID_OSM_FIELD: str = "id"
    _OSM_URL_FIELD: str = "osm_url"
    _ID_DEFAULT_FIELD: str = "id"

    _FEATURE_OSM_TYPE: Optional[str] = None

    _OUTPUT_EXPECTED_GEOM_TYPE: Optional[str] = None

    def __init__(self) -> None:
        super().__init__()

        self._study_area_geom: Optional[Polygon] = None

        self._output_data: Optional[Union[gpd.geodataframe, List[Dict]]] = None
        self._bbox_value: Optional[Tuple[float, float, float, float]] = None
        self._bbox_mode: bool = False

    def from_location(self, location_name: str, *args) -> None:
        self.logger.info(f"From location: {location_name}")
        self.logger.info("Loading data...")

        location_found = list(
            NominatimApi(
                self.logger, q=location_name, limit=self._NOMINATIM_NUMBER_RESULT
            ).data()
        )

        if len(location_found) == 0:
            raise ErrorOsmGtCore("Location not found!")
        elif len(location_found) > 1:
            self.logger.warning(
                f"Multiple locations found for {location_name} ; the first will be used"
            )
        location_id = location_found[0][self._NOMINATIM_OSM_ID_FIELD]
        self._study_area_geom = Polygon(
            location_found[0][self._NOMINATIM_GEOJSON_FIELD]["coordinates"][0]
        )

        self._location_id = self._location_osm_default_id_computing(location_id)

    def from_bbox(self, bbox_value: Tuple[float, float, float, float]) -> None:
        self._bbox_mode: bool = True
        self.logger.info(f"From bbox: {bbox_value}")
        self.logger.info("Loading data...")
        self._study_area_geom = box(*bbox_value, ccw=True)
        # reordered because of nominatim
        self._bbox_value = (bbox_value[1], bbox_value[0], bbox_value[3], bbox_value[2])

    @property
    def study_area(self) -> Polygon:
        """
        return the shapely geometry of the study area (data area)

        :return: the shapely geometry of the study area. If None, it means that nothing has been loaded or run
        :rtype: shapely.geometry.Polygon
        """
        return self._study_area_geom

    def _query_on_overpass_api(self, request: str) -> List[Dict]:
        return OverpassApi(self.logger).query(request)[self._QUERY_ELEMENTS_FIELD]

    @staticmethod
    def _from_location_name_query_builder(location_osm_id: int, query: str) -> str:
        geo_tag_query: str = "area.searchArea"
        query = query.format(geo_filter=geo_tag_query)
        return f"area({location_osm_id})->.searchArea;({query});{out_geom_query};"

    @staticmethod
    def _from_bbox_query_builder(
        bbox_value: Tuple[float, float, float, float], query: str
    ) -> str:
        assert isinstance(bbox_value, tuple)
        assert len(bbox_value) == 4
        bbox_value_str = ", ".join(map(str, bbox_value))
        query = query.format(geo_filter=bbox_value_str)
        return f"({query});{out_geom_query};"

    def _check_topology_field(self, input_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if self._TOPO_FIELD not in input_gdf.columns.tolist():
            input_gdf[self._TOPO_FIELD] = input_gdf.index.apply(lambda x: int(x))

        input_gdf = input_gdf.fillna(self._DEFAULT_NAN_VALUE_TO_USE)
        return input_gdf

    def get_gdf(self, verbose: bool = True) -> gpd.GeoDataFrame:
        """
        Return a GeoDataframe

        :param verbose: to activate log messages
        :return: geopandas.GeoDataframe
        """
        if verbose:
            self.logger.info("Prepare GeoDataframe")

        if len(self._output_data) == 0:
            raise EmptyData(
                "GeoDataframe creation is impossible, because no data has been found"
            )

        if not isinstance(self._output_data, gpd.GeoDataFrame):
            # more performance comparing .from_features() method
            df = pd.DataFrame()
            for chunk in chunker(self._output_data, 100000):
                df_tmp = pd.DataFrame(chunk)
                df = pd.concat((df, df_tmp), axis=0)
            df: pd.DataFrame = pd.DataFrame(self._output_data)

            geometry = df[self._GEOMETRY_FIELD]
            output_gdf: gpd.GeoDataFrame = gpd.GeoDataFrame(
                df.drop([self._GEOMETRY_FIELD], axis=1),
                crs=f"EPSG:{epsg_4326}",
                geometry=geometry.to_list(),
            )

        else:
            output_gdf: gpd.GeoDataFrame = self._output_data

        self._check_build_input_data(output_gdf)

        output_gdf: gpd.GeoDataFrame = self._clean_attributes(output_gdf)

        self.logger.info("GeoDataframe Ready")

        return output_gdf

    def _check_build_input_data(self, output_gdf) -> None:
        if output_gdf.shape[0] == 0:
            raise EmptyData("Data is empty!")

        geom_types_found = set(output_gdf[self._GEOMETRY_FIELD].geom_type.to_list())
        if geom_types_found != {self._OUTPUT_EXPECTED_GEOM_TYPE}:
            raise ErrorOsmGtCore(
                f"Geom type not supported! Only {self._OUTPUT_EXPECTED_GEOM_TYPE} supported ; {geom_types_found} found"
            )

    def _clean_attributes(self, input_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        for col_name in input_gdf.columns:
            if col_name in self.__USELESS_COLUMNS:
                input_gdf.drop(columns=[col_name], inplace=True)

        if self._ID_DEFAULT_FIELD not in input_gdf.columns:
            input_gdf.loc[:, self._ID_DEFAULT_FIELD] = input_gdf.index.astype(str)

        return input_gdf

    def _location_osm_default_id_computing(self, osm_location_id: int) -> int:
        return osm_location_id + self._NOMINATIM_DEFAULT_ID

    def _build_feature_from_osm(
        self, uuid_enum: int, geometry: Union[Point, LineString], properties: Dict
    ) -> Dict:
        properties_found: Dict = properties.get(self._PROPERTIES_OSM_FIELD, {})
        properties_found[self._ID_OSM_FIELD] = str(properties[self._ID_OSM_FIELD])
        properties_found[
            self._OSM_URL_FIELD
        ] = f"{osm_url}/{self._FEATURE_OSM_TYPE}/{properties_found[self._ID_OSM_FIELD]}"

        # used for topology
        properties_found[
            self._TOPO_FIELD
        ] = uuid_enum  # do not cast to str, because topology processing need an int..
        properties_found[self._GEOMETRY_FIELD] = geometry
        feature_build: Dict = properties_found

        return feature_build

    @staticmethod
    def _check_transport_mode(mode: str) -> None:
        assert (
            mode in network_queries.keys()
        ), f"'{mode}' not found in {', '.join(network_queries.keys())}"

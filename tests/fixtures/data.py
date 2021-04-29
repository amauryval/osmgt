import pytest

from shapely.wkt import loads
from shapely.geometry import LineString
from shapely.geometry import Point

import geojson
import geopandas as gpd


wkt_point_a = "Point (30 10 5)"
wkt_point_b = "Point(4 10 3)"
wkt_point_c = "Point (0 0 4)"


def build_geojson_features(input_data):
    all_geojson_features = []
    for feature in input_data:
        feature["properties"]["bounds"] = ", ".join(
            map(str, feature["geometry"].bounds)
        )

        feature = geojson.Feature(
            geometry=feature["geometry"], properties=feature["properties"]
        )
        all_geojson_features.append(feature)
    output_gdf = gpd.GeoDataFrame.from_features(all_geojson_features)
    output_gdf = output_gdf.fillna(value="None")
    return output_gdf


@pytest.fixture
def location_point():
    return Point(4.0697088, 46.0410178)


@pytest.fixture
def isochrone_values():
    return {2, 5, 10}


@pytest.fixture
def isochrone_distance_values():
    return [250, 500, 1000]

@pytest.fixture
def isochrone_distance_values2():
    return [500, 1000, 1500]


@pytest.fixture
def point_a():
    return loads(wkt_point_a)


@pytest.fixture
def point_b():
    return loads(wkt_point_b)


@pytest.fixture
def point_c():
    return loads(wkt_point_c)


@pytest.fixture
def epsg_2154():
    return 2154


@pytest.fixture
def epsg_4326():
    return 4326


@pytest.fixture
def some_line_features():
    all_features = [
        {
            "geometry": LineString(
                [
                    (4.07114907206290066, 46.03760345278882937),
                    (4.07091681769133018, 46.03699538217645681),
                    (4.07079583285433966, 46.03660928470699787),
                ]
            ),
            "properties": {"uuid": 10, "id": "10"},
        },
        {
            "geometry": LineString(
                [
                    (4.07079583285433966, 46.03660928470699787),
                    (4.07085925751677191, 46.03660294861677471),
                    (4.07086909165722677, 46.03667793393773877),
                    (4.07093731600662867, 46.03674923145603515),
                    (4.0710313549747239, 46.03670313392265712),
                    (4.07098587207512264, 46.03662323153146474),
                ]
            ),
            "properties": {"uuid": 11, "id": "11"},
        },
        {
            "geometry": LineString(
                [
                    (4.07132541293213457, 46.03636692445581957),
                    (4.07195460627399886, 46.0366250550576126),
                    (4.07215358194621313, 46.03668152112675216),
                    (4.0724305345710512, 46.03630508066581228),
                ]
            ),
            "properties": {"uuid": 12, "id": "12", "oneway": "yes"},
        },
    ]
    output_gdf = build_geojson_features(all_features)

    return output_gdf.to_dict("records")


@pytest.fixture
def some_point_features():
    all_features = [
        {
            "geometry": Point((4.07083953255024333, 46.03693156996429536)),
            "properties": {"uuid": 1, "id": "1"},
        },  # outside
        {
            "geometry": Point((4.07089961963211167, 46.03664388029959298)),
            "properties": {"uuid": 2, "id": "2"},
        },  # outside
        {
            "geometry": Point((4.07097056291628423, 46.03710105075762726)),
            "properties": {"uuid": 3, "id": "3"},
        },  # outside
        {
            "geometry": Point((4.07114907206290066, 46.03760345278882937)),
            "properties": {"uuid": 4, "id": "4"},
        },  # at the line start node
        {
            "geometry": Point((4.07091681769133018, 46.03699538217645681)),
            "properties": {"uuid": 5, "id": "5"},
        },  # at one linestring node
        {
            "geometry": Point((4.070811393410536, 46.036724772414075)),
            "properties": {"uuid": 6, "id": "6"},
        },
        {
            "geometry": Point((4.07088624242873376, 46.03680095802188532)),
            "properties": {"uuid": 7, "id": "7"},
        },
        {
            "geometry": Point((4.07103594046512729, 46.03720327149468972)),
            "properties": {"uuid": 8, "id": "8"},
        },
        {
            "geometry": Point((4.07101188185213569, 46.0373516329414727)),
            "properties": {"uuid": 9, "id": "9"},
        },
    ]
    output_gdf = build_geojson_features(all_features)

    return output_gdf.to_dict("records")


@pytest.fixture
def default_output_pois_columns():
    return {"id", "topo_uuid", "geometry", "osm_url"}


@pytest.fixture
def default_output_network_columns():
    return {"id", "topo_uuid", "topology", "geometry", "osm_url"}


@pytest.fixture
def shortest_path_output_default_columns():
    return {"id", "source_node", "target_node", "osm_ids", "osm_urls", "geometry"}


@pytest.fixture()
def isochrones_polygons_output_default_columns():
    return {"id", "iso_name", "iso_distance", "geometry"}


@pytest.fixture()
def isochrones_lines_output_default_columns():
    return {"id", "iso_name", "iso_distance", "topo_uuid", "topology", "osm_url", "geometry"}


@pytest.fixture
def points_gdf_from_coords():
    point_a = Point(451754.566, 5786544.841)
    point_b = Point(454531.361, 5789346.920)
    return gpd.GeoDataFrame(index=[0, 1], crs="EPSG:3857", geometry=[point_a, point_b])


@pytest.fixture
def points_gdf_from_coords2():
    point_a = Point(4.056578, 46.041645)
    point_b = Point(4.070440, 46.042196)
    return gpd.GeoDataFrame(index=[0, 1], crs="EPSG:3857", geometry=[point_a, point_b])



@pytest.fixture
def start_and_end_nodes():
    return (Point(4.0697088, 46.0410178), Point(4.0757785, 46.0315038))


@pytest.fixture
def start_and_end_nodes_2():
    return (Point(-74.004110, 40.722584), Point(-74.000205, 40.721494))


@pytest.fixture
def start_and_end_nodes_3():
    return (Point(-74.004110, 40.722584), Point(4.0757785, 46.0315038))


@pytest.fixture()
def bbox_values_1():
    return (4.0237426757812, 46.019674567761, 4.1220188140869, 46.072575637028)


@pytest.fixture()
def bbox_values_2():
    return (-74.018433, 40.718087, -73.982749, 40.733356)


@pytest.fixture()
def bbox_values_3():
    return (4.042110, 46.006263, 4.098072, 46.057509)

from setuptools import setup, find_packages

# used by meta.yaml, do not forget space
requirements = [
    "geopandas >=0.8.0",
    "requests ==2.23.0",
    "numpy ==1.18.1",
    "geojson ==2.5.0",
    "python-dateutil ==2.8.1",
    "graph-tool ==2.33",
    "cairo ==1.16.0",
    "scipy ==1.3.2",
    "more-itertools ==8.4.0",
    "numba ==0.48.0",
    "requests-futures ==1.0.0",
    "pygeos ==0.8.0"
]

setup_requirements = []

test_requirements = []

setup(
    author="amauryval",
    author_email='amauryval@gmail.com',
    url="https://github.com/amauryval/osmgt",
    version='0.7.11',
    description="A library to play with OSM roads (and POIs) data using graph tool network library",
    entry_points={},
    install_requires=requirements,
    license="GPL3",
    long_description="",
    include_package_data=True,
    keywords='network POIS roads shortest_path isochrone',
    name='osmgt',
    packages=find_packages(include=["osmgt", "osmgt.*"]),
    # setup_requires=setup_requirements,
    test_suite='tests',
    # tests_require=test_requirements,
    zip_safe=False,
    python_requires=">=3.7",
)

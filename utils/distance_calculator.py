import numpy as np
import pandas as pd
from typing import Iterable

EARTH_RADIUS_KM: float = 6371.0088


def haversine_np(latitudes: Iterable, longitudes: Iterable, center_latitude: float, center_longitude: float) -> pd.Series:
    """
    Compute Haversine distance in kilometers between arrays of points and a single center point.

    Parameters
    ----------
    latitudes : Iterable
        Iterable (e.g., pandas Series or numpy array) of latitudes in degrees.
    longitudes : Iterable
        Iterable (e.g., pandas Series or numpy array) of longitudes in degrees.
    center_latitude : float
        Latitude of the center point in degrees.
    center_longitude : float
        Longitude of the center point in degrees.

    Returns
    -------
    pandas.Series
        Distances in kilometers.
    """
    lat1 = np.radians(pd.to_numeric(pd.Series(latitudes), errors="coerce").astype(float))
    lon1 = np.radians(pd.to_numeric(pd.Series(longitudes), errors="coerce").astype(float))
    lat2 = np.radians(float(center_latitude))
    lon2 = np.radians(float(center_longitude))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(a))

    distances_km = EARTH_RADIUS_KM * c
    return pd.Series(distances_km)


def assign_distance_category(distances_km: pd.Series) -> pd.Series:
    """
    Assign categorical ranges based on distance in kilometers.

    Categories:
      - 0-5 km
      - 5-10 km
      - 10-20 km
      - 20-50 km
      - 50+ km
    """
    bins = [-np.inf, 5, 10, 20, 50, np.inf]
    labels = [
        "0-5 km",
        "5-10 km",
        "10-20 km",
        "20-50 km",
        "50+ km",
    ]
    return pd.cut(distances_km, bins=bins, labels=labels, right=True)
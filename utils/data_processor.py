from __future__ import annotations

import io
import re
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd

# Heuristic patterns for latitude and longitude column detection
LATITUDE_CANDIDATE_PATTERNS = [
    r"^lat$",
    r"^latitude$",
    r"^y$",
    r"lat",
    r"_lat$",
    r"latitude\s*\(deg\)",
]
LONGITUDE_CANDIDATE_PATTERNS = [
    r"^lon$",
    r"^lng$",
    r"^long$",
    r"^longitude$",
    r"^x$",
    r"lon|lng|long",
    r"_lon$|_lng$|_long$",
    r"longitude\s*\(deg\)",
]

COORDINATE_TEXT_COLUMN_CANDIDATES = [
    r"location",
    r"coordinates",
    r"coord",
    r"point",
    r"geo",
]


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _match_first(patterns: List[str], columns: List[str]) -> Optional[str]:
    for p in patterns:
        regex = re.compile(p, flags=re.IGNORECASE)
        for c in columns:
            if regex.search(c):
                return c
    return None


def _parse_coordinate_text(value: str) -> Optional[Tuple[float, float]]:
    """
    Attempt to parse a coordinate from text formats like:
      - "43.7, -79.2"
      - "(43.7, -79.2)"
      - "POINT(-79.2 43.7)" (WKT, lon lat)
    Returns (lat, lon) if successful.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text:
        return None

    # POINT(lon lat)
    match_wkt = re.match(r"POINT\s*\((-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)", text, flags=re.IGNORECASE)
    if match_wkt:
        lon = float(match_wkt.group(1))
        lat = float(match_wkt.group(2))
        if _valid_lat(lat) and _valid_lon(lon):
            return lat, lon

    # (lat, lon) or "lat, lon"
    match_pair = re.findall(r"-?\d+\.?\d*", text)
    if len(match_pair) >= 2:
        lat = float(match_pair[0])
        lon = float(match_pair[1])
        if _valid_lat(lat) and _valid_lon(lon):
            return lat, lon

    return None


def _valid_lat(lat: float) -> bool:
    try:
        return -90.0 <= float(lat) <= 90.0
    except Exception:
        return False


def _valid_lon(lon: float) -> bool:
    try:
        return -180.0 <= float(lon) <= 180.0
    except Exception:
        return False


def detect_coordinate_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to detect latitude and longitude columns in a dataframe.
    Returns a tuple (lat_col, lon_col). Either may be None if not found.
    """
    df = _standardize_columns(df)
    cols = list(df.columns)

    lat_col = _match_first(LATITUDE_CANDIDATE_PATTERNS, cols)
    lon_col = _match_first(LONGITUDE_CANDIDATE_PATTERNS, cols)

    if lat_col and lon_col:
        return lat_col, lon_col

    # Try detect a single coordinate text column
    coord_text_col = _match_first(COORDINATE_TEXT_COLUMN_CANDIDATES, cols)
    if coord_text_col is not None:
        return coord_text_col, None

    # Fallback: try any two numeric-like columns that look like lat/lon
    numeric_like_cols = []
    for c in cols:
        try:
            series = pd.to_numeric(df[c], errors="coerce")
            if series.notna().sum() > max(3, int(0.3 * len(series))):
                numeric_like_cols.append(c)
        except Exception:
            continue

    # Heuristic: choose pair where values fit lat/lon ranges most
    best_pair: Tuple[Optional[str], Optional[str]] = (None, None)
    best_score = -1
    for i in range(len(numeric_like_cols)):
        for j in range(i + 1, len(numeric_like_cols)):
            a = pd.to_numeric(df[numeric_like_cols[i]], errors="coerce")
            b = pd.to_numeric(df[numeric_like_cols[j]], errors="coerce")
            a_in_lat = a.between(-90, 90, inclusive="both").sum()
            b_in_lon = b.between(-180, 180, inclusive="both").sum()
            score1 = a_in_lat + b_in_lon
            a_in_lon = a.between(-180, 180, inclusive="both").sum()
            b_in_lat = b.between(-90, 90, inclusive="both").sum()
            score2 = a_in_lon + b_in_lat
            if max(score1, score2) > best_score:
                if score1 >= score2:
                    best_pair = (numeric_like_cols[i], numeric_like_cols[j])
                    best_score = score1
                else:
                    best_pair = (numeric_like_cols[j], numeric_like_cols[i])
                    best_score = score2

    return best_pair


def load_and_clean_csv(file: io.BytesIO | io.StringIO) -> Tuple[pd.DataFrame, Optional[str], Optional[str]]:
    """
    Load CSV into DataFrame, detect/clean coordinate columns, and standardize column names.
    Returns (df, lat_col, lon_col).
    """
    df = pd.read_csv(file)
    df = _standardize_columns(df)

    lat_col, lon_col = detect_coordinate_columns(df)

    if lat_col and lon_col:
        # If we detected a text column as lat_col with lon_col None, we'll parse later
        pass

    if lon_col is None and lat_col is not None:
        # lat_col is a coordinate text column containing both coords
        coords = df[lat_col].apply(_parse_coordinate_text)
        df["latitude"] = coords.apply(lambda x: x[0] if isinstance(x, tuple) else np.nan)
        df["longitude"] = coords.apply(lambda x: x[1] if isinstance(x, tuple) else np.nan)
        lat_col, lon_col = "latitude", "longitude"
    else:
        # Coerce named columns to numeric
        if lat_col is not None:
            df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        if lon_col is not None:
            df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    # Validate ranges
    if lat_col is not None:
        df.loc[~df[lat_col].apply(_valid_lat), lat_col] = np.nan
    if lon_col is not None:
        df.loc[~df[lon_col].apply(_valid_lon), lon_col] = np.nan

    # Standardize column names for coordinates
    if lat_col is not None and lat_col != "latitude":
        df.rename(columns={lat_col: "latitude"}, inplace=True)
        lat_col = "latitude"
    if lon_col is not None and lon_col != "longitude":
        df.rename(columns={lon_col: "longitude"}, inplace=True)
        lon_col = "longitude"

    return df, lat_col, lon_col


def sanitize_display_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace NaN/None/empty strings with 'Not specified' for user-facing display only.
    Does not mutate the input DataFrame.
    """
    display_df = df.copy()
    display_df.replace(to_replace=[np.nan, None, "", "nan", "NaN"], value="Not specified", inplace=True)
    return display_df
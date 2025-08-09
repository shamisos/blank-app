from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from folium import FeatureGroup, LayerControl, Map, Marker, Popup
from folium.features import DivIcon
from folium.plugins import MousePosition
import folium
from streamlit_folium import st_folium

from utils.data_processor import load_and_clean_csv, sanitize_display_values
from utils.distance_calculator import haversine_np, assign_distance_category
from utils import database as db

APP_TITLE = "Dialysis Patient Distribution Analyzer"
DEFAULT_FACILITY_NAME = "78 Corporate Drive"
DEFAULT_FACILITY_LAT = 43.78029
DEFAULT_FACILITY_LON = -79.2509

DISTANCE_CATEGORY_COLORS = {
    "0-5 km": "green",
    "5-10 km": "yellow",
    "10-20 km": "orange",
    "20-50 km": "red",
    "50+ km": "black",
}

DISPLAY_MISSING = "Not specified"


def init_session_state() -> None:
    if "facility" not in st.session_state:
        st.session_state["facility"] = {
            "name": DEFAULT_FACILITY_NAME,
            "lat": DEFAULT_FACILITY_LAT,
            "lon": DEFAULT_FACILITY_LON,
        }
    if "data" not in st.session_state:
        st.session_state["data"] = None  # Raw DataFrame
    if "db_url" not in st.session_state:
        st.session_state["db_url"] = os.getenv("DATABASE_URL", "")
    if "engine" not in st.session_state:
        st.session_state["engine"] = None
    if "filters" not in st.session_state:
        st.session_state["filters"] = {}


def connect_database(db_url: str) -> Optional[Any]:
    try:
        engine = db.get_engine(db_url)
        db.create_all_tables(engine)
        return engine
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None


def compute_distances(df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame:
    if df is None or lat_col not in df or lon_col not in df:
        return df
    center = st.session_state["facility"]
    distances = haversine_np(df[lat_col], df[lon_col], center["lat"], center["lon"]).astype(float)
    df = df.copy()
    df["distance_km"] = distances
    df["distance_category"] = assign_distance_category(df["distance_km"]).astype(str)
    return df


def apply_filters(df: pd.DataFrame, filter_state: Dict[str, Any]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    filtered = df.copy()

    # Distance categories
    active_cats = filter_state.get("distance_categories")
    if active_cats is not None and len(active_cats) > 0:
        filtered = filtered[filtered["distance_category"].isin(active_cats)]

    # Demographic filters
    for col in ["treatment_type", "gender", "ethnicity", "immigration_status"]:
        selected = filter_state.get(col)
        if selected is not None and len(selected) > 0:
            # Treat missing as DISPLAY_MISSING in UI; map back to NaN here
            filtered = filtered[filtered[col].fillna(DISPLAY_MISSING).isin(selected)]

    # Clinical (social determinants)
    for col in [
        "material_deprivation",
        "residential_instability",
        "dependency",
        "ethnic_concentration",
    ]:
        if col in filtered.columns:
            selected = filter_state.get(col)
            if selected is not None and len(selected) > 0:
                filtered = filtered[filtered[col].fillna(DISPLAY_MISSING).isin(selected)]

    return filtered


def get_category_counts(df: pd.DataFrame) -> Dict[str, int]:
    counts = {k: 0 for k in DISTANCE_CATEGORY_COLORS.keys()}
    if df is None or df.empty or "distance_category" not in df:
        return counts
    tmp = df["distance_category"].value_counts(dropna=False)
    for k in counts.keys():
        counts[k] = int(tmp.get(k, 0))
    return counts


def build_map(df: pd.DataFrame, map_height: int, map_width: int) -> Tuple[folium.Map, Dict[str, int]]:
    facility = st.session_state["facility"]
    fmap = Map(location=[facility["lat"], facility["lon"]], zoom_start=10, control_scale=True, tiles="CartoDB positron")

    # Draggable facility marker
    Marker(
        location=[facility["lat"], facility["lon"]],
        draggable=True,
        icon=folium.Icon(color="blue", icon="hospital-o", prefix="fa"),
        popup=Popup(html=f"<b>Facility:</b> {facility['name']}<br>{facility['lat']:.6f}, {facility['lon']:.6f}", max_width=300),
    ).add_to(fmap)

    category_groups: Dict[str, FeatureGroup] = {}
    for cat, color in DISTANCE_CATEGORY_COLORS.items():
        group = FeatureGroup(name=f"{cat}", show=True)
        group.add_to(fmap)
        category_groups[cat] = group

    # Add patient markers
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            if pd.isna(row.get("latitude")) or pd.isna(row.get("longitude")):
                continue
            cat = str(row.get("distance_category", "50+ km"))
            color = DISTANCE_CATEGORY_COLORS.get(cat, "gray")
            # Popup content
            fields = [
                ("Distance", f"{row['distance_km']:.2f} km" if not pd.isna(row.get("distance_km")) else DISPLAY_MISSING),
                ("Distance category", cat),
                ("Latitude", f"{row['latitude']:.6f}" if not pd.isna(row.get("latitude")) else DISPLAY_MISSING),
                ("Longitude", f"{row['longitude']:.6f}" if not pd.isna(row.get("longitude")) else DISPLAY_MISSING),
                ("Treatment type", row.get("treatment_type", DISPLAY_MISSING)),
                ("Gender", row.get("gender", DISPLAY_MISSING)),
                ("Ethnicity", row.get("ethnicity", DISPLAY_MISSING)),
                ("Immigration status", row.get("immigration_status", DISPLAY_MISSING)),
                ("Material deprivation", row.get("material_deprivation", DISPLAY_MISSING)),
                ("Residential instability", row.get("residential_instability", DISPLAY_MISSING)),
                ("Dependency", row.get("dependency", DISPLAY_MISSING)),
                ("Ethnic concentration", row.get("ethnic_concentration", DISPLAY_MISSING)),
            ]
            html_rows = "".join(
                f"<tr><th style='text-align:left;padding-right:8px'>{k}</th><td>{(DISPLAY_MISSING if pd.isna(v) or v == '' else v)}</td></tr>"
                for k, v in fields
            )
            popup_html = f"""
            <div style='font-size:14px'>
                <table>{html_rows}</table>
            </div>
            """
            Marker(
                location=[row["latitude"], row["longitude"]],
                icon=folium.Icon(color=color),
                popup=Popup(popup_html, max_width=350),
            ).add_to(category_groups.get(cat, fmap))

    LayerControl(collapsed=False).add_to(fmap)

    # Custom legend
    counts = get_category_counts(df)
    legend_items = "".join(
        f"<div style='margin:2px 0'><span style='display:inline-block;width:12px;height:12px;background:{DISTANCE_CATEGORY_COLORS[k]};margin-right:6px;border:1px solid #666'></span>{k}: <b>{counts[k]}</b></div>"
        for k in DISTANCE_CATEGORY_COLORS.keys()
    )
    legend_html = f"""
        <div style='position: fixed; bottom: 50px; left: 10px; z-index: 9999; background: white; padding: 10px 12px; border: 1px solid #ccc; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.2); font-size: 13px;'>
            <div style='font-weight:600;margin-bottom:6px'>Legend</div>
            {legend_items}
            <div style='margin-top:6px;font-size:12px;color:#555'>Click map to set facility location.</div>
        </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    # Mouse position helper
    MousePosition(position="topright", prefix="Lat/Lon:", separator=", ").add_to(fmap)

    return fmap, counts


def sidebar_controls(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    st.sidebar.markdown("### Database")
    db_url = st.sidebar.text_input("Database URL (PostgreSQL)", value=st.session_state["db_url"], placeholder="postgresql+psycopg2://user:pass@host:5432/dbname")
    col_db = st.sidebar.columns([1, 1])
    with col_db[0]:
        if st.button("Connect", use_container_width=True):
            engine = connect_database(db_url)
            if engine is not None:
                st.session_state["db_url"] = db_url
                st.session_state["engine"] = engine
                st.success("Connected and ensured tables exist.")
    with col_db[1]:
        if st.session_state.get("engine") is not None and st.button("Disconnect", use_container_width=True):
            st.session_state["engine"] = None
            st.info("Disconnected from database.")

    st.sidebar.markdown("---")

    st.sidebar.markdown("### Facility")
    facility = st.session_state["facility"]
    st.sidebar.text_input("Name", key="facility_name", value=facility.get("name", DEFAULT_FACILITY_NAME))
    lat = st.sidebar.number_input("Latitude", value=float(facility["lat"]), format="%.6f")
    lon = st.sidebar.number_input("Longitude", value=float(facility["lon"]), format="%.6f")
    if lat != facility["lat"] or lon != facility["lon"]:
        st.session_state["facility"]["lat"] = float(lat)
        st.session_state["facility"]["lon"] = float(lon)
    st.sidebar.caption("Tip: Click on the map to move the facility. Distances update instantly.")

    if st.session_state.get("engine") is not None:
        save_cols = st.sidebar.columns([1, 1])
        with save_cols[0]:
            if st.button("Save Facility", use_container_width=True):
                fid = db.save_facility(
                    st.session_state["engine"],
                    st.session_state.get("facility_name") or None,
                    st.session_state["facility"]["lat"],
                    st.session_state["facility"]["lon"],
                )
                st.success(f"Saved facility with id {fid}")
        with save_cols[1]:
            facilities = db.list_facilities(st.session_state["engine"]) or []
            if len(facilities) > 0:
                names = [f"{name} ({lat:.4f}, {lon:.4f})" for (_, name, lat, lon) in facilities]
                idx = st.selectbox("Load facility", options=list(range(len(facilities))), format_func=lambda i: names[i])
                if st.button("Load", use_container_width=True):
                    fid, name, latv, lonv = facilities[idx]
                    st.session_state["facility"] = {"name": name, "lat": latv, "lon": lonv}
                    st.experimental_rerun()

    st.sidebar.markdown("---")

    st.sidebar.markdown("### Filters")
    tabs = st.sidebar.tabs(["Distance", "Demographics", "Clinical"])  # type: ignore[attr-defined]

    filter_state: Dict[str, Any] = st.session_state.get("filters", {})

    # Distance tab
    with tabs[0]:
        if df is not None and not df.empty:
            counts_all = get_category_counts(df)
        else:
            counts_all = {k: 0 for k in DISTANCE_CATEGORY_COLORS.keys()}
        active_categories: List[str] = []
        for cat in DISTANCE_CATEGORY_COLORS.keys():
            checked = st.checkbox(f"{cat} ({counts_all[cat]})", value=True, key=f"filter_cat_{cat}")
            if checked:
                active_categories.append(cat)
        filter_state["distance_categories"] = active_categories

    # Demographics tab
    with tabs[1]:
        if df is not None and not df.empty:
            for col in ["treatment_type", "gender", "ethnicity", "immigration_status"]:
                if col in df.columns:
                    options = sorted(df[col].fillna(DISPLAY_MISSING).unique().tolist())
                    default = options
                    selected = st.multiselect(col.replace("_", " ").title(), options=options, default=default, key=f"filter_{col}")
                    filter_state[col] = selected

    # Clinical tab
    with tabs[2]:
        if df is not None and not df.empty:
            for col in [
                "material_deprivation",
                "residential_instability",
                "dependency",
                "ethnic_concentration",
            ]:
                if col in df.columns:
                    options = sorted(df[col].fillna(DISPLAY_MISSING).unique().tolist())
                    default = options
                    selected = st.multiselect(col.replace("_", " ").title(), options=options, default=default, key=f"filter_{col}")
                    filter_state[col] = selected

    st.session_state["filters"] = filter_state
    return filter_state


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    init_session_state()

    st.title(APP_TITLE)
    st.caption("Professional analytics dashboard for dialysis facility planning and patient access analysis.")

    # File uploader and data controls
    with st.expander("Data Upload and Preview", expanded=True):
        uploaded = st.file_uploader("Upload patient CSV", type=["csv"], accept_multiple_files=False)
        load_cols = st.columns([1, 1, 1])
        with load_cols[0]:
            if st.button("Load Example (Empty Template)"):
                example = pd.DataFrame(
                    {
                        "external_id": [],
                        "name": [],
                        "latitude": [],
                        "longitude": [],
                        "treatment_type": [],
                        "gender": [],
                        "ethnicity": [],
                        "immigration_status": [],
                        "material_deprivation": [],
                        "residential_instability": [],
                        "dependency": [],
                        "ethnic_concentration": [],
                    }
                )
                st.session_state["data"] = example
        with load_cols[1]:
            if st.session_state.get("engine") is not None and st.button("Load Patients from DB"):
                st.session_state["data"] = db.load_patients(st.session_state["engine"]) or pd.DataFrame()
        with load_cols[2]:
            if st.session_state.get("engine") is not None and st.session_state.get("data") is not None and not st.session_state["data"].empty:
                if st.button("Save Patients to DB"):
                    inserted = db.save_patients(st.session_state["engine"], st.session_state["data"])
                    st.success(f"Saved {inserted} patient records to DB.")

        if uploaded is not None:
            df, lat_col, lon_col = load_and_clean_csv(uploaded)
            if lat_col is None or lon_col is None:
                st.warning("Could not detect coordinate columns. Please ensure latitude and longitude are present.")
            st.session_state["data"] = df

        df = st.session_state.get("data")
        if df is not None and not df.empty:
            df = compute_distances(df)
            st.session_state["data"] = df
            st.write("Preview", sanitize_display_values(df).head(50))
            st.write("Summary Statistics", df[["distance_km"]].describe())
        else:
            st.info("Upload a CSV or load from the database to begin.")

    df = st.session_state.get("data")
    filter_state = sidebar_controls(df if df is not None else None)

    # Map sizing controls
    st.markdown("---")
    ui_cols = st.columns([1, 1, 2, 2])
    with ui_cols[0]:
        map_height = st.slider("Map height (px)", min_value=500, max_value=1000, value=700, step=50)
    with ui_cols[1]:
        expand = st.toggle("Expand width", value=False, help="Expand from 700px to 1200px width")
    map_width = 1200 if expand else 700

    # Apply filters
    if df is not None and not df.empty:
        filtered = apply_filters(df, filter_state)
    else:
        filtered = df

    # Build and display map
    if filtered is not None and not filtered.empty:
        fmap, counts = build_map(filtered, map_height, map_width)
        map_output = st_folium(fmap, width=map_width, height=map_height, returned_objects=["last_object_clicked"])  # type: ignore[arg-type]

        # Update facility on map click
        loc = map_output.get("last_object_clicked") if isinstance(map_output, dict) else None
        if loc and "lat" in loc and "lng" in loc:
            st.session_state["facility"]["lat"] = float(loc["lat"])  # type: ignore[index]
            st.session_state["facility"]["lon"] = float(loc["lng"])  # type: ignore[index]
            # Recompute distances immediately
            df = compute_distances(st.session_state["data"])
            st.session_state["data"] = df
    else:
        st.info("No data to display on the map with current filters.")

    # Export controls
    st.markdown("---")
    if filtered is not None and not filtered.empty:
        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("Download filtered results (CSV)", data=csv_bytes, file_name="analysis_results.csv", mime="text/csv")

    # Save analysis session
    if st.session_state.get("engine") is not None and df is not None and not df.empty:
        if st.button("Save Analysis Session"):
            summary = {
                "counts": get_category_counts(filtered if filtered is not None else df),
                "total_patients": int(len(df)),
                "filtered_patients": int(len(filtered)) if filtered is not None else 0,
            }
            fid: Optional[int] = None
            # Attempt to match facility in DB or save ad-hoc
            try:
                fid = db.save_facility(
                    st.session_state["engine"],
                    (st.session_state.get("facility_name") or st.session_state["facility"].get("name")),
                    st.session_state["facility"]["lat"],
                    st.session_state["facility"]["lon"],
                )
            except Exception:
                fid = None
            sid = db.save_analysis_session(st.session_state["engine"], fid, st.session_state.get("filters", {}), summary)
            st.success(f"Saved analysis session #{sid}")

    st.markdown("---")
    st.caption("All missing values are displayed as 'Not specified'. Coordinates are validated and invalid entries are excluded from the map.")


if __name__ == "__main__":
    main()

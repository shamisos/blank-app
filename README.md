# Dialysis Patient Distribution Analyzer

A production-ready Streamlit dashboard for healthcare administrators to analyze dialysis patient distribution, distances to a facility epicenter, and demographic/clinical filters. Built with Folium maps and PostgreSQL persistence via SQLAlchemy.

## Features
- Upload CSVs with flexible coordinate detection (latitude/longitude or combined text like "POINT(-79.2 43.7)")
- Data validation: invalid coordinates are cleared; missing values display as "Not specified"
- Interactive Folium map with draggable facility marker and color-coded patient markers by distance bands
- Layer controls, custom legend, dynamic sizing (500–1000px height, 700/1200px width)
- Sidebar filters (Distance, Demographics, Clinical) with live counts
- PostgreSQL integration to save/load Patients, Facilities, and Analysis Sessions
- Export filtered analysis results as CSV

## Quickstart
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. (Optional) Set database URL for PostgreSQL:
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/dbname"
   ```
3. Run the app:
   ```bash
   streamlit run streamlit_app.py --server.headless true --server.address 0.0.0.0 --server.port 5000
   ```
4. Open the provided URL and upload your CSV. Click on the map to reposition the facility; distances update in real time.

## CSV Expectations
- The app attempts to auto-detect coords:
  - Separate columns named like `latitude/lat/y` and `longitude/lon/lng/x`
  - A single text column with formats such as `"43.7, -79.2"` or `"POINT(-79.2 43.7)"`
- Additional columns are optional: `external_id`, `name`, `treatment_type`, `gender`, `ethnicity`, `immigration_status`, `material_deprivation`, `residential_instability`, `dependency`, `ethnic_concentration`.

## Notes
- Draggable facility marker is provided for UX; to update the epicenter in Streamlit, click on the map at the new location (drag events are not reliably captured by the Streamlit-Folium bridge).
- Distance categories: 0–5 km (green), 5–10 km (yellow), 10–20 km (orange), 20–50 km (red), 50+ km (black).
- All user-facing missing values render as "Not specified".

## Tech
- Streamlit, Folium, streamlit-folium, pandas, numpy, SQLAlchemy, psycopg2-binary, Alembic

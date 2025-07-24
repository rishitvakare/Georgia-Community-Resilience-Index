#
# ─── ALL IMPORTS ────────────────────────────────────────────────────────────────
#
import re
import os
import json
import math
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from shapely.geometry import shape
import feedparser
import urllib.parse
import requests
from sklearn.cluster import KMeans
import numpy as np


# Disable Hugging Face progress bars
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

# Set Streamlit page config
st.set_page_config(layout="wide")

#
# ─── DATA & PATHS ────────────────────────────────────────────────────────────────
#
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
CRI_CSV = DATA_DIR / "community_resilience_index.csv"
GEOJSON = DATA_DIR / "counties.geojson"


#
# ─── LOAD & PREP DATA ────────────────────────────────────────────────────────────
#
@st.cache_data
def load_data():
    dataframe = pd.read_csv(CRI_CSV, dtype=str)

    # Build FIPS
    dataframe["state"]  = dataframe["StateFIPS"].str.zfill(2)
    dataframe["county"] = dataframe["CountyFIPS"].str.zfill(3)
    dataframe["fips"]   = dataframe["state"] + dataframe["county"]

    # Numeric columns
    for column in [
        "Socioeconomic Resilience",
        "Food Resilience",
        "Healthcare Resilience",
        "Community Resilience Index (CRI)"
    ]:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").round(4)

    # Keep only Georgia (state FIPS == '13')
    dataframe = dataframe[dataframe["state"] == "13"].copy()

    # Load geojson & compute centroids for the counties
    gj = json.loads((GEOJSON).read_text())
    cents = {}
    for feat in gj["features"]:
        geoid = feat["properties"]["GEOID"]
        cent  = shape(feat["geometry"]).centroid
        cents[geoid] = (cent.y, cent.x)

    # Returns the DataFrame, the GeoJSON, and the centroids
    return dataframe, gj, cents

# Load the data
cri_df, counties_geojson, centroids = load_data()



#
# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────────────────
#

# To calculate the distance between two lat/lon pairs using the Haversine formula (In handy for radius filtering)
def haversine(a, b):
    latitude1, longitude1 = a
    latitude2, longitude2 = b
    dist_lat = math.radians(latitude2 - latitude1)
    dist_lon = math.radians(longitude2 - longitude1)
    hsine = math.sin(dist_lat/2)**2 + math.cos(math.radians(latitude1)) \
        * math.cos(math.radians(latitude2)) * math.sin(dist_lon/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(hsine))

# Filter the CRI DataFrame based on a range
def cri_range(low, high):
    sub = cri_df[(cri_df["Community Resilience Index (CRI)"] >= low) & (cri_df["Community Resilience Index (CRI)"] <= high)]
    return sub.sort_values("Community Resilience Index (CRI)", ascending=False)

# Parse the CRI range based on the user input in the chat bot
def parse_cri_range(text: str):
    txt = text.lower()
    # between X and Y
    mid = re.search(r"between\s*([0-9]*\.?[0-9]+)\s*(?:and|to)\s*([0-9]*\.?[0-9]+)", txt)
    if mid:
        return float(mid.group(1)), float(mid.group(2))
    # above X
    mid = re.search(r"above\s*([0-9]*\.?[0-9]+)", txt)
    if mid:
        return float(mid.group(1)), 1.0
    # below X
    mid = re.search(r"below\s*([0-9]*\.?[0-9]+)", txt)
    if mid:
        return 0.0, float(mid.group(1))
    raise ValueError("Sorry, I couldn't parse a CRI range from that question. " \
    "Please format your question in the example given above and try again.")

# Fetch the NOAA weather warnings for counties in Georgia that have an active warning
@st.cache_data(ttl=300)
def fetch_noaa_warnings():
    noaa_url = "https://api.weather.gov/alerts/active?area=GA"
    req = requests.get(noaa_url, timeout=10)
    req.raise_for_status()
    noaa_data = req.json()
    warning_fips = set()
    for feat in noaa_data["features"]:
        geocode = feat["properties"].get("geocode",{}) or {}
        for code in geocode.get("SAME", []):
            # NWS SAME codes are 5-digit state+county FIPS (e.g. "13057")
            if len(code) == 5 and code.startswith("13"):
                warning_fips.add(code)
    return warning_fips

@st.cache_data
def compute_res_clusters(df, n_clusters=4):
    # Through scikit-learn's KMeans, we can cluster the counties based on their resilience scores.
    # We will use the four resilience scores as features for clustering.
    X = df[[
        "Socioeconomic Resilience",
        "Food Resilience",
        "Healthcare Resilience"
    ]].to_numpy()
    kmeans = KMeans(n_clusters=n_clusters, random_state=0)
    labels = kmeans.fit_predict(X)
    df2 = df.copy()
    df2["cluster"] = labels.astype(str)
    return df2, kmeans

# Compute the clusters
clustered_df, kmeans_model = compute_res_clusters(cri_df)

#
# ─── SIDEBAR : NEWS FEED + NOAA WARNINGS ───────────────────────────────────────────────────────────────────────
#

# Sidebar components
with st.sidebar:

    # Title for the sidebar
    st.sidebar.markdown(
    "<div style='font-size:24px; font-weight:bold; margin-bottom:8px;'>📰 Live News & NOAA Warning Feed</div>",
    unsafe_allow_html=True,
    )

    # Let's the user input keywords separated by commas 
    keyword_input = st.sidebar.text_input(
        "Enter keywords (comma-separated)",
        value="Social inequality"
    )

    # Can pull up to 50 articles at a time
    articles = st.sidebar.slider("Max articles to fetch", 1, 50, 20)

    # Builds the RSS search algorithm through google articles 
    terms = [keyword.strip() + " Georgia" for keyword in keyword_input.split(",") if keyword.strip()]
    quote = urllib.parse.quote_plus(" OR ".join(terms))
    feed_urls = f"https://news.google.com/rss/search?q={quote}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(feed_urls)


    sidebar_entries = feed.entries[:articles]

    # Pagination logic
    if "news_page" not in st.session_state or st.session_state.get("news_query") != feed_urls:
        st.session_state.news_page = 1
        st.session_state.news_query = feed_urls
    curr_page = st.session_state.news_page
    per_page = 5
    total_pages = math.ceil(len(sidebar_entries) / per_page) or 1

    # Just render the sidebar entries for the current page
    start = (curr_page - 1) * per_page
    end = start + per_page
    for entry in sidebar_entries[start:end]:
        date = entry.get("published", "").split("T")[0]
        st.sidebar.markdown(
            f"**[{entry.title}]({entry.link})**  \n*{date}*"
        )
    
    # Renders the page navigation buttons
    previous_col, middle_col, next_col = st.sidebar.columns([1, 2, 1])
    if previous_col.button("« Prev Page") and curr_page > 1:
        st.session_state.news_page -= 1
    if next_col.button("Next Page »") and curr_page < total_pages:
        st.session_state.news_page += 1

    middle_col.markdown(
    f"<div style='text-align: center; font-weight:600;'>Page {curr_page} of {total_pages}</div>",
    unsafe_allow_html=True,
)
    
    
#
# ─── MAIN LAYOUT ───────────────────────────────────────────────────────────────────────
#

# Title centered
st.markdown("<h1 style='text-align:center'>Georgia Community Resilience Index Dashboard</h1>", unsafe_allow_html=True)

# Two-column layout
# - Left: Filters and Chatbot
# - Right: Map and Bar Chart
left, right = st.columns([1,3], gap="large")

# Left column: Filters and Chatbot
with left:
    # Sets the subheader for the filters section
    st.subheader("🔎 Filters")
    # CRI slider filter
    min_c, max_c = st.slider(
        "CRI range",
        float(cri_df["Community Resilience Index (CRI)"].min()),
        float(cri_df["Community Resilience Index (CRI)"].max()),
        (
          float(cri_df["Community Resilience Index (CRI)"].min()),
          float(cri_df["Community Resilience Index (CRI)"].max()),
        )
    )
    # County and radius filters
    county = st.selectbox("County", ["All"]+sorted(cri_df["County Name"].unique()))
    radius = st.slider("Radius (mi)", 1, 100, 25)

    st.markdown("---")
    # Chatbot for CRI range queries
    st.subheader("💬 Ask the CRI Bot")
    query = st.text_input("e.g. Which counties above 0.7?")
    if st.button("Run Chat"):
        try:
            low, high = parse_cri_range(query)
            df_out = cri_range(low, high)
            st.write(df_out[["County Name","Community Resilience Index (CRI)"]])
        except Exception as error:
            st.error(error)

# Right column: Map and Bar Chart
with right:
    # Pick your base: raw CRI vs. cluster
    map_toggle = st.radio(
        "Color Map By:",
        ["Community Resilience Index (CRI)", "Resilience Clusters"],
        index=0,
    )

    # If we are using clusters, we need to prepare the DataFrame for the clusters
    # and show the cluster centers
    if map_toggle == "Resilience Clusters":
        centers = pd.DataFrame(
            kmeans_model.cluster_centers_,
            columns=[
                "Socioeconomic Resilience",
                "Food Resilience",
                "Healthcare Resilience"
            ],
            index=[f"Cluster {i}" for i in range(len(kmeans_model.cluster_centers_))]
        ).round(4)
        st.subheader("Resilience Cluster Centers")
        st.table(centers)
        
        base = clustered_df.copy()
        color_col = "cluster"
    else:
        base = cri_df.copy()
        color_col = "Community Resilience Index (CRI)"


    
    # Prepare the map DataFrame
    # Filter the base DataFrame based on the CRI range and county selection
    df_map = base[(base["Community Resilience Index (CRI)"] >= min_c) & (base["Community Resilience Index (CRI)"] <= max_c)].copy()
    if county!="All":
        center = centroids[cri_df.loc[cri_df["County Name"]==county,"fips"].iloc[0]]
        df_map["dist"] = df_map["fips"].map(lambda f: haversine(center, centroids[f]))
        df_map = df_map[df_map["dist"] <= radius]

    # Warning fip codes are received from the helper function calling the NOAA API
    warning_fips = fetch_noaa_warnings()
    df_map["warning"] = df_map["fips"].isin(warning_fips)


    # Build the choropleth map using Plotly Express

    # If the map toggle is resilience cluster
    if map_toggle == "Resilience Clusters":
        fig = px.choropleth(
            df_map,
            geojson=counties_geojson,
            locations="fips",
            featureidkey="properties.GEOID",
            color="cluster",
            scope="usa",
            category_orders={ "cluster": sorted(df_map["cluster"].unique()) },
            color_discrete_sequence = px.colors.qualitative.Plotly,
            title="Counties by Resilience Clusters",
            hover_data=[
                "County Name",
                "Socioeconomic Resilience",
                "Food Resilience",
                "Healthcare Resilience",
                "cluster"
            ],
        )
        fig.update_traces(marker_line_width=0.5)

    # If the map toggle is Community Resilience Index (CRI)
    else:
        fig = px.choropleth(
            df_map,
            geojson=counties_geojson,
            locations="fips",
            featureidkey="properties.GEOID",
            color="Community Resilience Index (CRI)",
            color_continuous_scale="Viridis",
            scope="usa",
            title="CRI by Georgia County",
            hover_data=[
                "County Name",
                "Socioeconomic Resilience",
                "Food Resilience",
                "Healthcare Resilience",
                "Community Resilience Index (CRI)",
            ],
        )

    # Override the default hover template to include custom data
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Socioeconomic: %{customdata[1]:.4f}<br>"
            "Food: %{customdata[2]:.4f}<br>"
            "Healthcare: %{customdata[3]:.4f}<br>"
            "CRI: %{customdata[4]:.4f}<extra></extra>"
        )
    )

    # To make sure NOAA warnings are shown properly with coloring already going on for CRI and Resilience Clusters,
    # we need to set the border colors and widths based on the warning status
    border_colors  = ["red" if w else "#444" for w in df_map["warning"]]
    border_widths  = [3 if w else 1 for w in df_map["warning"]]
    fig.update_traces(
        marker_line_color=border_colors,
        marker_line_width=border_widths
    )


    # Title alignment for the graph
    fig.update_layout(title_x=0.3)


    # Show the active NOAA warnings in the sidebar with the FIPS codes
    codes = sorted(warning_fips)
    if codes:
        st.sidebar.write("Active alert FIPS codes:", codes)
    else:
        st.sidebar.info("No active NOAA alerts for Georgia right now.")

    # Update the map layout
    fig.update_geos(
        fitbounds="locations", visible=False,
        lonaxis=dict(range=[-85.5, -80.5]),
        lataxis=dict(range=[30, 35.5])
    )
    fig.update_layout(margin={"t": 30, "b": 0, "l": 0, "r": 0}, title_x=0.3)
    st.plotly_chart(fig, use_container_width=True)

    # Bar chart + Details
    st.subheader("CRI Distribution")
    st.bar_chart(df_map.set_index("County Name")["Community Resilience Index (CRI)"])

    if county != "All" and not df_map.empty:
        r = df_map.iloc[0]
        st.subheader(f"Details: {county}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Socioeconomic", f"{r['Socioeconomic Resilience']:.4f}")
        c2.metric("Food",         f"{r['Food Resilience']:.4f}")
        c3.metric("Healthcare",   f"{r['Healthcare Resilience']:.4f}")
        c4.metric("CRI",          f"{r['Community Resilience Index (CRI)']:.4f}")

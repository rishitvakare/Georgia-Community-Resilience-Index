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
from huggingface_hub import snapshot_download
from pathlib import Path
import feedparser
import urllib.parse
import requests

# Disable Hugging Face progress bars
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"


st.set_page_config(layout="wide")

#
# ─── DATA & PATHS ────────────────────────────────────────────────────────────────
#
HERE      = Path(__file__).resolve().parent
DATA_DIR  = HERE / "data"
CRI_CSV   = DATA_DIR / "community_resilience_index.csv"
GEOJSON   = DATA_DIR / "counties.geojson"
MODEL_DIR = HERE / "models" / "Llama-2-7b-chat-hf"


#
# ─── LOAD & PREP DATA ────────────────────────────────────────────────────────────
#
@st.cache_data
def load_data():
    df = pd.read_csv(CRI_CSV, dtype=str)

    # Build FIPS
    df["state"]  = df["StateFIPS"].str.zfill(2)
    df["county"] = df["CountyFIPS"].str.zfill(3)
    df["fips"]   = df["state"] + df["county"]

    # Numeric columns
    for col in [
        "Socioeconomic Resilience",
        "Food Resilience",
        "Healthcare Resilience",
        "Community Resilience Index (CRI)"
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(4)

    # Keep only Georgia (state FIPS == '13')
    df = df[df["state"] == "13"].copy()

    # Load geojson & compute centroids
    gj = json.loads((GEOJSON).read_text())
    cents = {}
    for feat in gj["features"]:
        geoid = feat["properties"]["GEOID"]
        cent  = shape(feat["geometry"]).centroid
        cents[geoid] = (cent.y, cent.x)

    return df, gj, cents

cri_df, counties_geojson, centroids = load_data()


#
# ─── HELPERS ─────────────────────────────────────────────────────────────────────
#

# To calculate the distance between two lat/lon pairs using the Haversine formula
def haversine(a, b):
    """Return miles between lat/lon pairs."""
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(h))

# Filter the CRI DataFrame based on a range
def filter_cri(lo, hi):
    sub = cri_df[(cri_df["Community Resilience Index (CRI)"]>=lo) & (cri_df["Community Resilience Index (CRI)"]<=hi)]
    return sub.sort_values("Community Resilience Index (CRI)", ascending=False)

# Parse the CRI range based on the user input in the chat bot
def parse_cri_range(text: str):
    """
    Simple rule-based parser:
      - "above X" → (X, 1.0)
      - "below X" → (0.0, X)
      - "between X and Y" → (X, Y)
    """
    t = text.lower()
    # between X and Y
    m = re.search(r"between\s*([0-9]*\.?[0-9]+)\s*(?:and|to)\s*([0-9]*\.?[0-9]+)", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    # above X
    m = re.search(r"above\s*([0-9]*\.?[0-9]+)", t)
    if m:
        return float(m.group(1)), 1.0
    # below X
    m = re.search(r"below\s*([0-9]*\.?[0-9]+)", t)
    if m:
        return 0.0, float(m.group(1))
    raise ValueError("Sorry, I couldn't parse a CRI range from that question. " \
    "Please format your question in the example given above and try again.")

# Fetch the NOAA weather warnings for Georgia
@st.cache_data(ttl=300)
def fetch_noaa_warnings():
    url = "https://api.weather.gov/alerts/active?area=GA"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    warning_fips = set()
    for feat in data["features"]:
        geocode = feat["properties"].get("geocode",{}) or {}
        for code in geocode.get("SAME", []):
            # NWS SAME codes are 5-digit state+county FIPS (e.g. "13057")
            if len(code) == 5 and code.startswith("13"):
                warning_fips.add(code)
    return warning_fips

#
# ─── SIDEBAR : JUST THE NEWS FEED ───────────────────────────────────────────────────────────────────────
#
with st.sidebar:
    st.sidebar.markdown(
    "<div style='font-size:24px; font-weight:bold; margin-bottom:8px;'>📰 Live News Feed</div>",
    unsafe_allow_html=True,
)

    # 1) let the user type any keywords (comma-sep)  
    kw_input = st.sidebar.text_input(
        "Enter keywords (comma-separated)",
        value="disaster resilience, food desert"
    )

    # 2) how many total articles to pull (1–50)
    total_to_fetch = st.sidebar.slider("Max articles to fetch", 1, 50, 20)

    # build & fetch RSS
    terms = [kw.strip() + " Georgia" for kw in kw_input.split(",") if kw.strip()]
    q = urllib.parse.quote_plus(" OR ".join(terms))
    feed_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(feed_url)

    all_entries = feed.entries[:total_to_fetch]

    # 3) pagination state
    if "news_page" not in st.session_state or st.session_state.get("news_query") != feed_url:
        st.session_state.news_page = 1
        st.session_state.news_query = feed_url

    page = st.session_state.news_page
    per_page = 5
    total_pages = math.ceil(len(all_entries) / per_page) or 1

    # 4) slice & render just this page’s 5 articles
    start = (page - 1) * per_page
    end   = start + per_page
    for entry in all_entries[start:end]:
        date = entry.get("published", "").split("T")[0]
        st.sidebar.markdown(
            f"**[{entry.title}]({entry.link})**  \n*{date}*"
        )
    
    # 5) page nav buttons
    prev_col, mid_col, next_col = st.sidebar.columns([1, 2, 1])
    if prev_col.button("« Prev Page") and page > 1:
        st.session_state.news_page -= 1
    if next_col.button("Next Page »") and page < total_pages:
        st.session_state.news_page += 1

    mid_col.markdown(
    f"<div style='text-align: center; font-weight:600;'>Page {page} of {total_pages}</div>",
    unsafe_allow_html=True,
)
    
    
#
# ─── MAIN LAYOUT ───────────────────────────────────────────────────────────────────────
#
# Title centered
st.markdown("<h1 style='text-align:center'>Georgia Community Resilience Index Dashboard</h1>", unsafe_allow_html=True)

# Two-column layout: Filters/Chat on left, Map+Charts on right
left, right = st.columns([1,3], gap="large")

with left:
    st.subheader("🔎 Filters")
    min_c, max_c = st.slider(
        "CRI range",
        float(cri_df["Community Resilience Index (CRI)"].min()),
        float(cri_df["Community Resilience Index (CRI)"].max()),
        (
          float(cri_df["Community Resilience Index (CRI)"].min()),
          float(cri_df["Community Resilience Index (CRI)"].max()),
        )
    )
    county = st.selectbox("County", ["All"]+sorted(cri_df["County Name"].unique()))
    rad    = st.slider("Radius (mi)", 1, 100, 25)

    st.markdown("---")
    st.subheader("💬 Ask the CRI Bot")
    q = st.text_input("e.g. Which counties above 0.7?")
    if st.button("Run Chat"):
        try:
            lo, hi = parse_cri_range(q)
            df_out = filter_cri(lo, hi)
            st.write(df_out[["County Name","Community Resilience Index (CRI)"]])
        except Exception as err:
            st.error(err)

with right:
    # filter for map & bar chart
    df_map = filter_cri(min_c, max_c)
    if county!="All":
        center = centroids[cri_df.loc[cri_df["County Name"]==county,"fips"].iloc[0]]
        df_map["dist"] = df_map["fips"].map(lambda f: haversine(center, centroids[f]))
        df_map = df_map[df_map["dist"]<=rad]

    warning_fips = fetch_noaa_warnings()
    # flag those rows in your map‐DataFrame
    df_map["warning"] = df_map["fips"].isin(warning_fips)


    # when you call px.choropleth, add custom_data=…
    fig = px.choropleth(
        df_map,
        geojson=counties_geojson,
        locations="fips",
        featureidkey="properties.GEOID",
        color="Community Resilience Index (CRI)",
        color_continuous_scale="Viridis",
        scope="usa",
        # we list all five fields, in the exact order we want them in the hover
        custom_data=[
            "County Name",
            "Socioeconomic Resilience",
            "Food Resilience",
            "Healthcare Resilience",
            "Community Resilience Index (CRI)",
        ],
        title="CRI by Georgia Counties",
    )

    # now override the default hover to use our customdata array:
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Socioeconomic: %{customdata[1]:.4f}<br>"
            "Food: %{customdata[2]:.4f}<br>"
            "Healthcare: %{customdata[3]:.4f}<br>"
            "CRI: %{customdata[4]:.4f}<extra></extra>"
        )
    )
    # Title alignment
    fig.update_layout(title_x=0.3)

    line_colors = [
    "red" if warn else "#444" 
    for warn in df_map["warning"]
    ]
    fig.update_traces(
        marker_line_color=line_colors,
        marker_line_width=2
    )

    codes = sorted(warning_fips)
    if codes:
        st.sidebar.write("Active alert FIPS codes:", codes)
    else:
        st.sidebar.info("No active NOAA alerts for Georgia right now.")

    fig.update_geos(fitbounds="locations", visible=False,
                    lonaxis=dict(range=[-85.5,-80.5]),
                    lataxis=dict(range=[30,35.5]))
    fig.update_layout(margin={"t":30,"b":0,"l":0,"r":0})
    st.plotly_chart(fig, use_container_width=True)

    # Bar chart + details
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

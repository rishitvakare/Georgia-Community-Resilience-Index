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

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"


st.set_page_config(layout="wide")
st.title("Georgia Community Resilience Index Dashboard")

#
# ─── DATA & PATHS ────────────────────────────────────────────────────────────────
#
HERE      = Path(__file__).resolve().parent
DATA_DIR  = HERE / "data"
CRI_CSV   = DATA_DIR / "community_resilience_index.csv"
GEOJSON   = DATA_DIR / "counties.geojson"
MODEL_DIR = HERE / "models" / "Llama-2-7b-chat-hf"
snapshot_download(
    repo_id="meta-llama/Llama-2-7b-chat-hf",
    repo_type="model",
    local_dir=MODEL_DIR,
    resume_download=True,
    token=os.getenv("HUGGINGFACE_HUB_TOKEN"),
)

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


#----------- FETCH NEWS FUNCTION -----------
@st.cache_data(ttl=600)
def fetch_news(topics: list[str], page_size: int = 10):
    """
    Pull the latest articles from NewsAPI.org matching:
      - “Georgia AND (topic1 OR topic2 OR ... )”
    """
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        raise RuntimeError("Please set NEWSAPI_KEY in your environment")
    # Build the q parameter
    q = "Georgia, USA AND (" + " OR ".join(f'"{t}"' for t in topics) + ")"
    url = "https://newsapi.org/v2/everything"
    params  = {
    "q":        f"({user_query}) AND Georgia, USA",   # <= here
    "pageSize": max_articles,
    "apiKey":   api_key,
    "sortBy":   "publishedAt",
    "language": "en",
    }
    res = requests.get(url, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()
    return data.get("articles", [])


#
# ─── HELPERS ─────────────────────────────────────────────────────────────────────
#
def haversine(a, b):
    """Return miles between lat/lon pairs."""
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(h))

def filter_cri(min_cri: float, max_cri: float):
    """Return list of {County Name, CRI} between the given range."""
    sub = cri_df[
        (cri_df["Community Resilience Index (CRI)"] >= min_cri) &
        (cri_df["Community Resilience Index (CRI)"] <= max_cri)
    ]
    return (
        sub[["County Name","Community Resilience Index (CRI)"]]
        .sort_values("Community Resilience Index (CRI)", ascending=False)
        .to_dict(orient="records")
    )

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
    raise ValueError("Sorry, I couldn't parse a CRI range from that question. Please format your question in the example given above and try again.")

#
# ─── LAYOUT ───────────────────────────────────────────────────────────────────────
#
col_chat, col_main = st.columns([1, 3])

with col_chat:
    st.header("Ask the CRI Bot")
    user_q = st.text_input("e.g. Which counties have a CRI above 0.6?")
    if st.button("Run"):
        if not user_q.strip():
            st.warning("Please enter a question.")
        else:
            try:
                lo, hi = parse_cri_range(user_q)
                result = filter_cri(lo, hi)
                st.json(result)
            except Exception as e:
                st.error(str(e))

with col_main:
    
# -------- ALL SIDEBAR COMPONENTS --------
    st.sidebar.header("Filters")

    # Slider
    min_c, max_c = st.sidebar.slider(
        "CRI range",
        float(cri_df["Community Resilience Index (CRI)"].min()),
        float(cri_df["Community Resilience Index (CRI)"].max()),
        (
            float(cri_df["Community Resilience Index (CRI)"].min()),
            float(cri_df["Community Resilience Index (CRI)"].max())
        ),
    )

    # County dropdown + radius
    selected = st.sidebar.selectbox(
        "Select a county",
        ["All"] + sorted(cri_df["County Name"].unique()),
    )
    rad = st.sidebar.slider("Radius (miles)", 1, 100, 25)

    # Base filter
    flt = cri_df[
        (cri_df["Community Resilience Index (CRI)"] >= min_c) &
        (cri_df["Community Resilience Index (CRI)"] <= max_c)
    ]

    # If a county is picked, filter by distance
    if selected != "All":
        row = cri_df[cri_df["County Name"] == selected]
        if not row.empty:
            center = centroids[row.iloc[0]["fips"]]
            flt = flt.assign(
                distance_mi=flt["fips"]
                    .map(lambda f: haversine(center, centroids.get(f, (None,None))))
            )
            flt = flt[flt["distance_mi"] <= rad]
    
    # ── News feed controls ─────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Search Georgia News")
    # 1) let the user type _any_ query
    user_query = st.sidebar.text_input(
    "Search term(s)", 
    value="disaster resilience" 
    )

    max_articles = st.sidebar.slider("How many articles?", 1, 20, 5)

    # 3) when they click, go fetch!
    if st.sidebar.button("Fetch News"):
        if not user_query.strip():
            st.sidebar.warning("Please enter at least one term.")
            articles = []
        else:
            api_key = os.getenv("NEWSAPI_KEY")
            url     = "https://newsapi.org/v2/everything"
            params  = {
                "q": f"({user_query}) AND Georgia, USA",
                "pageSize": max_articles,
                "apiKey":   api_key,
                "sortBy":   "publishedAt",
                "language": "en",
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                if data.get("status") != "ok":
                    raise ValueError(data.get("message","Unknown error"))
                articles = data["articles"]
            except Exception as e:
                st.sidebar.error(f"NewsAPI error: {e}")
                articles = []
    else:
        articles = []

    # Choropleth
    fig = px.choropleth(
        flt,
        geojson=counties_geojson,
        locations="fips",
        featureidkey="properties.GEOID",
        color="Community Resilience Index (CRI)",
        color_continuous_scale="Viridis",
        scope="usa",
        hover_data=[
            "County Name",
            "Socioeconomic Resilience",
            "Food Resilience",
            "Healthcare Resilience",
            "Community Resilience Index (CRI)"
        ],
        title="CRI by County"
    )
    fig.update_geos(fitbounds="locations", visible=False,
                    lonaxis=dict(range=[-85.5,-80.5]),
                    lataxis=dict(range=[30,35.5]))
    fig.update_layout(margin={"t":30,"b":0,"l":0,"r":0})
    st.plotly_chart(fig, use_container_width=True)

    # Bar chart + details
    st.subheader("CRI Distribution")
    st.bar_chart(flt.set_index("County Name")["Community Resilience Index (CRI)"])

    if selected != "All" and not flt.empty:
        r = flt.iloc[0]
        st.subheader(f"Details: {selected}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Socioeconomic", f"{r['Socioeconomic Resilience']:.4f}")
        c2.metric("Food",         f"{r['Food Resilience']:.4f}")
        c3.metric("Healthcare",   f"{r['Healthcare Resilience']:.4f}")
        c4.metric("CRI",          f"{r['Community Resilience Index (CRI)']:.4f}")

    # ── Render News ────────────────────────────────────────────────────────
    if articles:
        st.subheader("📰 Latest News")
        for art in articles:
            title = art.get("title","No title")
            url   = art.get("url","")
            src   = art.get("source",{}).get("name","")
            date  = art.get("publishedAt","")[:10]
            desc  = art.get("description","")
            st.markdown(
                f"### [{title}]({url})  \n"
                f"*{src}, {date}*  \n\n"
                f"{desc}"
            )
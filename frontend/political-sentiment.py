from typing import List

import altair as alt
import pandas as pd
import requests
import folium
import streamlit as st
from streamlit import session_state
from streamlit_folium import st_folium

API_BASE = "http://localhost:9090"
ELECTION_DATE = "2025-05-03"

PARTY_KEYWORDS = {
    "ALP": [
        "Labor Party",
        "Australian Labor Party",
        "Labor Government Australia",
    ],
    "LNP": [
        "Liberal National Party",
        "The Nationals",
        "Tories",
    ],
    "LP": [
        "Liberal Party",
        "Libs",
        "The Coalition",
    ],
    "GRN": [
        "Green Party",
        "Greens",
        "Australian Greens",
    ],
    "ON": [
        "One Nation Party",
        "Pauline Hanson One Nation",
        "One Nation Australia",
    ],
}

st.set_page_config(layout="wide")

# Store the initial value of widgets in session state
col1, col2 = st.columns([4, 4])
list_parties = []
list_candidates = []


@st.cache_data(show_spinner="Loading candidates...")
def fetch_candidates():
    params = {}
    resp = requests.get(
        f"{API_BASE}/elections/top-candidates", params=params, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner="Loading parties...")
def fetch_parties():
    params = {}
    resp = requests.get(
        f"{API_BASE}/elections/top-parties", params=params, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


def _get_data(
    party: str | None = None,
    candidate: str | None = None,
    exclude_neutral: bool = False,
    group_by: str = "week",
):
    if party:
        kw = [party] + PARTY_KEYWORDS.get(party, [])
    else:
        kw = [candidate]
    return {
        "topic_name": party or candidate,
        "keywords": kw,
        "exclude_neutral": exclude_neutral,
        "aggregate_by": group_by,
    }


@st.cache_data(show_spinner="Loading sentiments...")
def fetch_sentiments1(
    party=None, candidate=None, exclude_neutral=False, group_time="week"
):
    payload = _get_data(party, candidate, exclude_neutral, group_time)
    resp = requests.post(
        f"{API_BASE}/trends/sentiment/compute", json=payload, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner="Loading sentiments...")
def fetch_sentiments2(
    party=None, candidate=None, exclude_neutral=False, group_time="week"
):
    payload = _get_data(party, candidate, exclude_neutral, group_time)
    resp = requests.post(
        f"{API_BASE}/trends/emotion/compute", json=payload, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner="Loading proportion of posts with mention...")
def fetch_proportions(keywords: tuple[str, ...], group_time="week"):
    payload = {
        "keywords": list(keywords),
        "topic_name": keywords[0],
        "aggregate_by": group_time,
    }
    resp = requests.post(
        f"{API_BASE}/trends/count-proportion/compute", json=payload, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


list_parties = (fetch_parties()).get("parties", [])
list_candidates = (fetch_candidates()).get("candidates", [])

candidates_df = pd.DataFrame(list_candidates)
if not candidates_df.empty:
    if "candidate_id" in candidates_df.columns:
        candidates_df = candidates_df.drop(columns=["candidate_id"])
    if "candidate_surname" in candidates_df.columns:
        candidates_df = candidates_df.rename(
            columns={"candidate_surname": "surname"}
        )
        candidates_df["surname"] = (
            candidates_df["surname"].astype(str).str.capitalize()
        )
    first_cols = [
        c
        for c in ["candidate_given_name", "surname", "total_votes"]
        if c in candidates_df.columns
    ]
    other_cols = [c for c in candidates_df.columns if c not in first_cols]
    candidates_df = candidates_df[first_cols + other_cols]

table_col1, table_col2 = st.columns(2)
with table_col1:
    st.subheader("Parties")
    st.dataframe(list_parties, use_container_width=True, hide_index=True)
with table_col2:
    st.subheader("Candidates")
    st.dataframe(candidates_df, use_container_width=True, hide_index=True)

st.radio(
    "Choose a criteria to filter",
    key="criteria",
    options=["party", "candidate"],
)
by_party = st.selectbox(
    "Select a party",
    ([party.get("party_abbreviation", "Other") for party in list_parties]),
    disabled=bool(st.session_state.criteria == "candidate"),
)
by_candidate = st.selectbox(
    "Select a candidate",
    (
        [
            f"{candidate.get('candidate_given_name', 'Others')} {candidate.get('candidate_surname', '')}"
            for candidate in list_candidates
        ]
    ),
    disabled=bool(st.session_state.criteria == "party"),
)
no_neutral = st.checkbox("Exclude neutral sentiment posts", value=False)
group_by_time = st.radio(
    "Group Results By",
    key="group_by_time",
    options=["week", "month"],
)


if st.session_state.criteria == "party":
    selected_party = by_party
    selected_candidate = None
else:
    selected_party = None
    selected_candidate = by_candidate


sentiments1 = fetch_sentiments1(
    party=selected_party,
    candidate=selected_candidate,
    group_time=group_by_time,
    exclude_neutral=no_neutral,
).get("data", [])
df1 = pd.DataFrame(sentiments1)
if not df1.empty:
    df1["date"] = pd.to_datetime(df1["date"])
    df1_long = df1.melt(
        id_vars=["date"],
        value_vars=["avg_positive", "avg_negative", "avg_neutral"],
        var_name="metric",
        value_name="value",
    )
    sentiment_chart = (
        alt.Chart(df1_long)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("value:Q", title="Average sentiment"),
            color=alt.Color(
                "metric:N",
                title="Metric",
                scale=alt.Scale(
                    domain=["avg_positive", "avg_negative", "avg_neutral"],
                    range=["green", "red", "blue"],
                ),
            ),
        )
        .properties(title="Average sentiment over time")
    )
    election_rule = (
        alt.Chart(pd.DataFrame({"date": [pd.to_datetime(ELECTION_DATE)]}))
        .mark_rule(color="black", strokeDash=[6, 4])
        .encode(x="date:T")
    )
    st.altair_chart(sentiment_chart + election_rule, use_container_width=True)
else:
    st.info("No sentiment data available.")


sentiments2 = fetch_sentiments2(
    party=selected_party,
    candidate=selected_candidate,
    group_time=group_by_time,
    exclude_neutral=no_neutral,
).get("data", [])
emotion_rows = []
for entry in sentiments2:
    date = entry.get("date")
    for emotion, count in (entry.get("emotions") or {}).items():
        emotion_rows.append({"date": date, "emotion": emotion, "count": count})

df2 = pd.DataFrame(emotion_rows)
if not df2.empty:
    df2["date"] = pd.to_datetime(df2["date"])
    emotion_order = sorted(df2["emotion"].unique().tolist())
    emotion_chart = (
        alt.Chart(df2)
        .mark_area()
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("count:Q", stack="zero", title="Count"),
            color=alt.Color(
                "emotion:N",
                title="Emotion",
                sort=emotion_order,
                legend=alt.Legend(direction="vertical"),
            ),
            order=alt.Order("emotion:N", sort="ascending"),
        )
        .properties(title="Emotions over time")
    )
    emotion_rule = (
        alt.Chart(pd.DataFrame({"date": [pd.to_datetime(ELECTION_DATE)]}))
        .mark_rule(color="black", strokeDash=[6, 4])
        .encode(x="date:T")
    )
    st.altair_chart(emotion_chart + emotion_rule, use_container_width=True)
else:
    st.info("No emotion data available.")


kw_source = st.text_area(
    "Enter keywords separated by comma to check proportions",
    value="Barnaby Joyce",
)
if kw_source:
    keywords = tuple(filter(None, map(str.strip, kw_source.split(","))))
    kw_counts = fetch_proportions(keywords, group_by_time)["data"]
    df_prop = pd.DataFrame(kw_counts)
    df_prop["date"] = pd.to_datetime(df_prop["date"])
    df_prop_long = df_prop.melt(
        id_vars=["date"],
        value_vars=["pct_mentioned"],
        var_name="metric",
        value_name="value",
    )
    proportion_chart = (
        alt.Chart(df_prop_long)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("value:Q", title="Percentage of Posts with Match"),
            color=alt.Color(
                "metric:N",
                title="Metric",
                scale=alt.Scale(
                    domain=["pct_mentioned"],
                    range=["red"],
                ),
            ),
        )
        .properties(title="Proportion of posts with mention over time")
    )
    election_rule = (
        alt.Chart(pd.DataFrame({"date": [pd.to_datetime(ELECTION_DATE)]}))
        .mark_rule(color="black", strokeDash=[6, 4])
        .encode(x="date:T")
    )
    st.altair_chart(proportion_chart + election_rule, use_container_width=True)

# --- GDELT News Sentiment Section ---
st.markdown("---")
st.subheader("News Sentiment & Geographic Distribution")

st.info(
    "💡 **Understanding GDELT Sentiment:** Global news skews negative:\n"
    "* **0 to -1.0:** Factual/Neutral | **-1.5 to -3.0:** Critical/Political Tension | **< -3.5:** Crisis/Scandal."
)

@st.cache_data(show_spinner="Loading GDELT news sentiment...")
def fetch_gdelt_timeseries(party=None, candidate=None, group_time="week"):
    kw = PARTY_KEYWORDS.get(party, [party])[0] if party else candidate
    try:
        resp = requests.get(f"{API_BASE}/api/gdelt/timeseries", params={"keywords": kw, "interval": group_time}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("timeseries", []) if isinstance(data, dict) else data
    except Exception:
        return []

gdelt_records = fetch_gdelt_timeseries(selected_party, selected_candidate, group_by_time)

if not gdelt_records:
    st.info("No GDELT data available for this selection.")
else:
    df_gdelt = pd.DataFrame(gdelt_records)
    df_gdelt["date"] = pd.to_datetime(df_gdelt["date"], utc=True).dt.tz_localize(None)
    
    # Fast numeric conversion
    for col in ["average_sentiment", "article_count"]:
        if col in df_gdelt.columns:
            df_gdelt[col] = pd.to_numeric(df_gdelt[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x), errors='coerce')
    
    df_gdelt = df_gdelt[df_gdelt["article_count"] > 0].dropna()

    # Sync dates
    x_scale = alt.Scale()
    if 'df1' in locals() and not df1.empty:
        min_d, max_d = pd.to_datetime(df1["date"]).min(), pd.to_datetime(df1["date"]).max()
        df_gdelt = df_gdelt[(df_gdelt["date"] >= min_d) & (df_gdelt["date"] <= max_d)]
        x_scale = alt.Scale(domain=[min_d.isoformat(), max_d.isoformat()])

    if not df_gdelt.empty:
        # --- POLISHED DUAL-AXIS CHART ---
        base = alt.Chart(df_gdelt).encode(x=alt.X("date:T", title="Date", scale=x_scale))
        
        # Left Axis: Volume
        bars = base.mark_bar(opacity=0.3, color="#8884d8", size=15).encode(
            y=alt.Y("article_count:Q", title="Volume (Articles)", axis=alt.Axis(orient="left", titleColor="#8884d8"))
        )
        
        # Right Axis: Sentiment
        line = base.mark_line(color="gray", strokeWidth=1.5, opacity=0.6).encode(
            y=alt.Y("average_sentiment:Q", title="Average Sentiment", axis=alt.Axis(orient="right", titleColor="gray"))
        )
        
        dots = base.mark_circle(size=80).encode(
            y=alt.Y("average_sentiment:Q", axis=None),
            color=alt.Color("average_sentiment:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[-4, 0]), 
                            legend=alt.Legend(orient="bottom", direction="horizontal", title="Sentiment Index")),
            tooltip=[alt.Tooltip("date:T"), alt.Tooltip("average_sentiment:Q", format=".2f"), alt.Tooltip("article_count:Q")]
        )
        
        volume_text = base.mark_text(align='center', dy=-5, fontSize=9, color="#8884d8").encode(
            y=alt.Y("article_count:Q", axis=None), text=alt.Text("article_count:Q", format=".2s")
        )
        
        election_rule = alt.Chart(pd.DataFrame({"date": [pd.to_datetime(ELECTION_DATE)]})).mark_rule(color="black", strokeDash=[6, 4]).encode(x="date:T")

        st.altair_chart(alt.layer(bars, line, dots, election_rule).resolve_scale(y='independent').properties(height=400), use_container_width=True)        
        
        # MAP PLOTTING        
        #Flatten data using a list
        loc_data = [
            {"lat": loc["lat"], "lon": loc["lon"], "name": loc["location_name"], "val": val}
            for entry in gdelt_records
            for loc in entry.get("locations", [])
            if (val := (entry.get("average_sentiment") if isinstance(entry.get("average_sentiment"), (int, float)) 
                       else (entry.get("average_sentiment", {}).get("value") if isinstance(entry.get("average_sentiment"), dict) else 0)))
        ]

        if loc_data:
            import numpy as np
            df_loc = pd.DataFrame(loc_data)
            
            #VECTORIZED COLOR ASSIGNMENT 
            conditions = [
                (df_loc['val'] > -1),
                (df_loc['val'] > -2)
            ]
            choices = ['#1a9850', '#fee08b'] # Green, Yellow
            df_loc['color'] = np.select(conditions, choices, default='#d73027') # Red default

            c1, c2, c3 = st.columns([1, 10, 1])
            with c2:
                m = folium.Map(location=[-25.27, 133.77], zoom_start=4) 
                # We cap at 1000 points to keep the frontend responsive
                for _, row in df_loc.head(1000).iterrows():
                    folium.CircleMarker(
                        location=[row['lat'], row['lon']],
                        radius=5, 
                        color=row['color'], 
                        fill=True, 
                        fill_opacity=0.4, 
                        opacity=0.2,
                        popup=f"{row['name']} (Sentiment: {row['val']:.2f})"
                    ).add_to(m)
                
                st_folium(m, width=1200, height=600)
        else:
            st.info("No location data available.")
    else:
        st.info("No data in the selected date range.")
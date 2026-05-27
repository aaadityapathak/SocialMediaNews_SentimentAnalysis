from typing import List

import altair as alt
import pandas as pd
import requests
import folium
import streamlit as st
from streamlit_folium import st_folium

API_BASE = "http://localhost:9090"

AVAILABLE_YEARS = [2021, 2016]
AUSTRALIAN_STATES = [
    "All states",
    "Victoria",
    "New South Wales",
    "Queensland",
    # "South Australia",
    "Western Australia",
    "Tasmania",
    # "Northern Territory",
    # "Australian Capital Territory",
]
MODE_COLORS = {
    "car_driver": "#e74c3c",
    "car": "#e74c3c",
    "car_passenger": "#e67e22",
    "train": "#3498db",
    "bus": "#27ae60",
    "tram": "#8e44ad",
    "bicycle": "#f39c12",
    "walk_only": "#1abc9c",
    "other": "#95a5a6",
}


@st.cache_data(show_spinner="Loading zones...")
def fetch_geojson(year: int, state: str | None) -> dict:
    tolerance = 0.05 if not state else 0.01
    params = {"year": year, "tolerance": tolerance}
    if state:
        params["state"] = state
    resp = requests.get(f"{API_BASE}/census/travel", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner="Loading transport-group counts…")
def fetch_transport_groups(
    platform: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    params: dict[str, str] = {}
    if platform:
        params["platform"] = platform
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    resp = requests.get(
        f"{API_BASE}/social/transport-groups", params=params, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner="zones...")
def fetch_transport_sentiment(
    platform: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    year: int | None = None,
) -> dict:
    params: dict[str, str] = {}
    if platform:
        params["platform"] = platform
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    if year:
        params["year"] = str(year)
    resp = requests.get(
        f"{API_BASE}/social/transport-sentiment", params=params, timeout=60
    )

    # resp.raise_for_status()
    return resp.json()


def matrix_to_dataframe(payload: dict, value_field: str = "count"):
    rows = []
    for entry in payload.get("matrix", []):
        row = {"mode": entry["mode"]}
        for cell in entry["cells"]:
            row[cell["sentiment"]] = cell[value_field]
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("mode")
    return df[payload.get("sentiments", df.columns.tolist())]


def matrix_heatmap(payload: dict, value_field: str = "count"):
    rows = []
    for entry in payload.get("matrix", []):
        mode = entry["mode"]
        for cell in entry["cells"]:
            rows.append(
                {
                    "mode": mode,
                    "sentiment": cell["sentiment"],
                    "value": cell[value_field],
                }
            )
    return pd.DataFrame(rows)


def build_map(geojson: dict, year: int) -> folium.Map:
    m = folium.Map(
        location=[-25.0, 134.0], zoom_start=4, tiles="CartoDB positron"
    )

    folium.GeoJson(
        geojson,
        style_function=lambda f: {
            "fillColor": MODE_COLORS.get(
                f["properties"].get("dominant_mode"), "#bdc3c7"
            ),
            "color": "#555",
            "weight": 0.5,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["zone_name", "state", "dominant_mode", "year"],
            aliases=["Zone", "State", "Dominant mode", "Year"],
        ),
    ).add_to(m)

    return m


def flatten_by_modes(geojson: dict) -> List[dict]:
    features = geojson.get("features", [])
    flatten = []
    for f in features:
        properties = f.get("properties", None)
        state = properties.get("state", None)
        if not state:
            continue
        travel_modes = properties.get("travel_modes", {})
        travel_modes_keys = travel_modes.keys()
        flatten.extend(
            [
                {
                    "state": state,
                    "travel_mode": travel_mode,
                    "quantity": travel_modes[f"{travel_mode}"],
                }
                for travel_mode in travel_modes_keys
            ]
        )
    return flatten


def compute_state_mode_proportions(geojson: dict) -> pd.DataFrame:
    totals: dict[str, dict[str, int]] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        state = props.get("state")
        if not state:
            continue
        modes = props.get("travel_modes", {})
        total_state = totals.setdefault(state, {})
        for mode, count in modes.items():
            if mode == "total" or count is None:
                continue

            total_state[mode] = int(count) + total_state.get(mode, 0)

    rows: list[dict] = []
    for state, modes in totals.items():
        state_total = sum(modes.values())
        if state_total == 0:
            continue
        for mode, count in modes.items():
            rows.append(
                {
                    "state": state,
                    "travel_mode": mode,
                    "count": count,
                    "proportion": round(count / state_total * 100, 2),
                }
            )
    return pd.DataFrame(rows)


st.set_page_config(layout="wide")
st.title("Method of Travel to Work — Australia Census")
st.caption("Census data (2021)")

col1, col2 = st.columns([1, 3])

with col1:
    year = st.selectbox("Census year", AVAILABLE_YEARS)
    state_label = st.selectbox("State", AUSTRALIAN_STATES)
    state = None if state_label == "All states" else state_label

    st.markdown("---")
    st.markdown("**Legend**")
    for mode, color in MODE_COLORS.items():
        if mode in ("car", "car_passenger"):
            continue
        st.markdown(
            f"<span style='background:{color};display:inline-block;"
            f"width:10px; height:10px; margin-right:6px; border-radius:2px;'></span>"
            f"{mode.replace('_', ' ')}",
            unsafe_allow_html=True,
        )

with col2:
    try:
        geojson = fetch_geojson(year, state)
        st.caption(f"{len(geojson['features'])} zones loaded")
        st_folium(
            build_map(geojson, year), use_container_width=True, height=650
        )
        st.markdown("---")
        flatten_geojson = flatten_by_modes(geojson)
        st.bar_chart(
            flatten_geojson, x="travel_mode", y="quantity", horizontal=True
        )

        st.markdown("---")
        st.subheader("Proportion of travel modes per state")
        proportions_df = compute_state_mode_proportions(geojson)
        if proportions_df.empty:
            st.info("No data available")
        else:
            st.bar_chart(
                proportions_df,
                x="state",
                y="proportion",
                color="travel_mode",
                stack="normalize",
                horizontal=True,
            )
            wide = (
                proportions_df.pivot(
                    index="state", columns="travel_mode", values="proportion"
                )
                .fillna(0)
                .round(2)
            )
            st.dataframe(wide.style.format("{:.2f}%"), use_container_width=True)

        st.markdown("---")
        st.subheader("Social post mentions by transport group")
        try:
            groups_payload = fetch_transport_groups()
        except Exception as e:
            st.error(f"Could not load transport groups: {e}")
        else:
            total_posts = groups_payload.get("total_posts", 0)
            st.caption(f"{total_posts} posts evaluated from social-posts-index")
            groups_df = pd.DataFrame(groups_payload.get("groups", []))
            if groups_df.empty:
                st.info("No transport-group data available")
            else:
                groups_df["proportion"] = (groups_df["proportion"] * 100).round(
                    2
                )
                groups_df = groups_df.rename(
                    columns={
                        "group": "Transport group",
                        "count": "Posts",
                        "proportion": "Share of total (%)",
                    }
                )
                st.dataframe(
                    groups_df, use_container_width=True, hide_index=True
                )

        st.markdown("---")
        st.subheader("Sentiment matrix: mode x sentiment")
        st.caption(
            "Counts of posts mentioning each transport mode  grouped by sentiment level."
        )
        try:
            sentiment_payload = fetch_transport_sentiment(year=year)
        except Exception as e:
            st.error(f"Could not load sentiment matrix: {e}")
        else:
            total_posts = sentiment_payload.get("total_posts", 0)
            st.caption(
                f"{total_posts} posts evaluated · "
                f"modes: {', '.join(sentiment_payload.get('modes', []))} · "
                f"sentiments: {', '.join(sentiment_payload.get('sentiments', []))}"
            )

            share_df = matrix_to_dataframe(
                sentiment_payload, "proportion_of_mode"
            )

            if share_df.empty:
                st.info("No data available")
            else:
                modes_order = sentiment_payload.get(
                    "modes", share_df.index.tolist()
                )
                sentiments_order = sentiment_payload.get(
                    "sentiments", share_df.columns.tolist()
                )

                heatmap = matrix_heatmap(
                    sentiment_payload, "proportion_of_mode"
                )
                heatmap["value"] = (heatmap["value"] * 100).round(2)
                value_title = "Sentiment proportion (%)"
                value_format = ".2f"
                table_df = (share_df * 100).round(2)
                table_format = "{:.2f}%"

                heatmap = (
                    alt.Chart(heatmap)
                    .mark_rect()
                    .encode(
                        x=alt.X(
                            "sentiment:N",
                            sort=sentiments_order,
                            title="Sentiment",
                        ),
                        y=alt.Y(
                            "mode:N",
                            sort=modes_order,
                            title="Transport mode",
                        ),
                        color=alt.Color(
                            "value:Q",
                            title=value_title,
                        ),
                        tooltip=[
                            alt.Tooltip("mode:N", title="Mode"),
                            alt.Tooltip("sentiment:N", title="Sentiment"),
                            alt.Tooltip(
                                "value:Q",
                                title=value_title,
                                format=value_format,
                            ),
                        ],
                    )
                    .properties(height=600)
                )
                st.altair_chart(heatmap, use_container_width=True)
                st.dataframe(
                    table_df.style.format(table_format),
                    use_container_width=True,
                )

    except Exception as e:
        st.error(f"Could not load data: {e}")

import streamlit as st

political_scenario = st.Page(
    "political-sentiment.py",
    title="Political sentiment",
    url_path="political-scenario",
    default=True,
)
transport_scenario = st.Page(
    "census_travel.py",
    title="Transport",
    url_path="transport-scenario",
)

pg = st.navigation([political_scenario, transport_scenario])
pg.run()

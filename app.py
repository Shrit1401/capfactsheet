"""Entry point: Tutor Arena + 'How we built it' pages."""

import streamlit as st

import keys

st.set_page_config(page_title="Factsheet Tutor Arena", page_icon="🧑‍🏫", layout="wide")

keys.api_keys_panel()

st.navigation([
    st.Page("study.py", title="Study", icon="🧪", default=True),
    st.Page("arena.py", title="Tutor Arena", icon="⚔️"),
    st.Page("model_check.py", title="Model check", icon="🧪"),
    st.Page("about.py", title="How we built it", icon="🗺️"),
], position="top").run()

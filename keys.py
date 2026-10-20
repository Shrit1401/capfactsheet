"""API keys: typed in the sidebar, or read from secrets.toml / env vars. Shared by every page."""

from __future__ import annotations

import os

import streamlit as st

import tutor_engine as te


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.environ.get(name) or ""


def api_keys_panel():
    ss = st.session_state
    ss.setdefault("openai_key", _secret("OPENAI_API_KEY"))
    ss.setdefault("gemini_key", _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY"))
    with st.sidebar.expander("🔑 API keys", expanded=not (ss.openai_key or ss.gemini_key)):
        st.text_input("OpenAI API key", type="password", key="openai_key", placeholder="sk-...")
        st.text_input("Gemini API key", type="password", key="gemini_key", placeholder="AIza...")
        st.caption("Kept only in this browser session. Each model picker shows the models your keys unlock.")


@st.cache_resource(show_spinner=False)
def _clients(openai_key: str, gemini_key: str) -> te.Clients:
    return te.Clients(openai_key or None, gemini_key or None)


def get_clients() -> te.Clients:
    ss = st.session_state
    return _clients((ss.get("openai_key") or "").strip(), (ss.get("gemini_key") or "").strip())


def pick_defaults(available: list[str], wanted: list[str], n: int) -> list[str]:
    """`wanted` models that are available, topped up with other available ones, up to n."""
    out = [m for m in wanted if m in available]
    out += [m for m in available if m not in out]
    return out[:n]

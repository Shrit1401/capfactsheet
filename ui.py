"""Small shared styles: progress dots and soft cards."""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
.dots { font-size:13px; color:#8e8e93; letter-spacing:1px; margin:-4px 0 6px; }
.card-soft { border:1px solid #8e8e9333; border-radius:16px; padding:16px 18px; height:100%; }
.card-soft .ic { font-size:24px; margin-bottom:6px; }
.card-soft h4 { margin:0 0 6px; padding:0; font-size:16px; }
.card-soft p { margin:0; font-size:14px; opacity:.8; line-height:1.5; }
.lead { font-size:18px; line-height:1.55; opacity:.9; max-width:760px; }
.kicker { text-transform:uppercase; letter-spacing:.08em; font-size:12px; color:#f4655b; font-weight:600; margin-top:28px; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def soft_card(icon: str, title: str, body: str):
    st.markdown(f'<div class="card-soft"><div class="ic">{icon}</div><h4>{title}</h4><p>{body}</p></div>',
                unsafe_allow_html=True)


def kicker(text: str):
    st.markdown(f'<div class="kicker">{text}</div>', unsafe_allow_html=True)

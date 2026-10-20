"""Model check page: send one prompt to many OpenAI and Gemini models at once and compare."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import streamlit as st

import keys
import tutor_engine as te

FACTSHEETS = Path(__file__).parent / "factsheets"
DEFAULT_MODELS = ["gpt-6-sol", "gpt-5.4-mini", "gemini-4-argon", "gemini-3.5-flash"]

ss = st.session_state
ss.setdefault("check_results", [])

st.title("🧪 Model check")
st.caption("Send the same prompt to several models at once. Use it to confirm your keys work and compare "
           "answers, speed and cost before picking tutor models.")

clients = keys.get_clients()
available = clients.models()
if not available:
    st.info("Add an OpenAI and/or Gemini API key in the sidebar (🔑 API keys) to start.")
    st.stop()

models = st.multiselect("Models", available, default=keys.pick_defaults(available, DEFAULT_MODELS, 4),
                        accept_new_options=True,
                        help="Type any other model id (e.g. gpt-5.5 or gemini-3.1-pro-preview) to add it.")
prompt = st.text_area("Prompt", "In two sentences: what is a mutual fund's exit load?", height=100)
c1, c2, c3 = st.columns([2, 2, 1.2], vertical_alignment="bottom")
factsheets = ["(none)"] + sorted(p.name for p in FACTSHEETS.glob("*.pdf"))
attach = c1.selectbox("Attach factsheet PDF", factsheets)
effort = c2.select_slider("Thinking", ["none", "minimal", "low", "medium", "high"], value="low")
run = c3.button("▶️ Run", type="primary", width="stretch", disabled=not (models and prompt.strip()))


def run_one(model: str, inp) -> dict:
    t0 = time.time()
    try:
        text, usage = te.ping(clients, model, prompt, inp, effort)
        return {"model": model, "ok": True, "seconds": time.time() - t0, "text": text, "usage": usage}
    except Exception as e:
        return {"model": model, "ok": False, "seconds": time.time() - t0, "text": f"{type(e).__name__}: {e}",
                "usage": te.Usage(model)}


if run:
    missing = [m for m in models if not clients.has(m)]
    if missing:
        st.warning(f"No key for: {', '.join(missing)}")
    inp = None
    if attach != "(none)":
        pdf = te.pdf_part((FACTSHEETS / attach).read_bytes(), attach)
        inp = [{"role": "user", "content": [pdf, {"type": "input_text", "text": prompt}]}]
    with st.spinner(f"Asking {len(models)} model(s)…"):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ss.check_results = list(pool.map(lambda m: run_one(m, inp), models))

results = ss.check_results
if results:
    table = pd.DataFrame([{
        "model": r["model"], "status": "✅" if r["ok"] else "❌", "seconds": round(r["seconds"], 2),
        "input tokens": r["usage"].input_tokens, "output tokens": r["usage"].output_tokens,
        "cost (USD)": round(r["usage"].cost, 6) if r["model"] in te.PRICES else None,
    } for r in results])
    st.dataframe(table, hide_index=True, width="stretch")
    for r in results:
        with st.expander(f"{'✅' if r['ok'] else '❌'} {r['model']} · {r['seconds']:.1f}s", expanded=True):
            if r["ok"]:
                st.markdown(r["text"] or "_(empty reply)_")
            else:
                st.error(r["text"])

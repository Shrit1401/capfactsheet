"""Participant study page: factsheet viewer + one of the three study conditions.

Participant links look like:  /study?condition=hybrid&fund=Kotak_LargeCap_Feb_2026.pdf&model=gpt-5.4-mini&pid=P001&lock=1
(model is optional; lock=1 hides the researcher sidebar and navigation).
"""

from __future__ import annotations

import base64
import html
import io
import json
import time
from pathlib import Path

import pypdfium2 as pdfium
import streamlit as st

import charts
import keys
import study_config as cfg
import tutor_engine as te

ROOT = Path(__file__).parent
FACTSHEETS = ROOT / "factsheets"
SESSIONS = ROOT / "results" / "sessions"
STATUS_ICON = {"not_started": "○", "explained": "◐", "needs_help": "◐", "understood": "✅"}

ss = st.session_state
ss.setdefault("study", {})
params = st.query_params
locked = params.get("lock") == "1"

st.markdown("""
<style>
.panel-title { font-size:18px; font-weight:650; margin:0; }
.panel-sub { font-size:13.5px; opacity:.7; margin:2px 0 4px; }
.chat-head { background:#4f46e5; color:#fff; border-radius:14px 14px 0 0; padding:12px 18px; font-weight:650; font-size:17px; margin:-1rem -1rem 8px; }
.pdf-head { display:flex; justify-content:space-between; align-items:center; font-weight:600; font-size:16px; }
.pdf-scroll { height:760px; overflow:auto; border-radius:10px; background:#f3f4f6; padding:14px; }
.pdf-scroll img { display:block; margin:0 auto 14px; box-shadow:0 2px 10px rgba(0,0,0,.15); }
.path-row { font-size:14.5px; padding:5px 2px; }
.faq-answer { font-size:14.5px; line-height:1.5; padding:4px 6px 2px 36px; opacity:.9; }
div[data-testid="stButton"] button p { text-align:left; }
</style>""", unsafe_allow_html=True)
if locked:
    st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
                "[data-testid='stSidebarNav'],header{display:none !important}</style>", unsafe_allow_html=True)


# ---------------- settings (sidebar for researchers, URL params for participants) ----------------

bundled = sorted(p.name for p in FACTSHEETS.glob("*.pdf"))
cond_keys = list(cfg.CONDITIONS)
default_cond = params.get("condition") if params.get("condition") in cond_keys else "guided"
default_fund = params.get("fund") if params.get("fund") in bundled else bundled[0]
pid = params.get("pid", "researcher")

@st.cache_data(show_spinner=False)
def fund_label(file: str) -> str:
    """'Kotak_LargeCap_Feb_2026.pdf' -> 'Kotak Large Cap Fund · Feb 2026'."""
    parts = Path(file).stem.split("_")
    when = " ".join(parts[-2:]) if len(parts) >= 3 else ""
    name = te.fund_name_from_pdf((FACTSHEETS / file).read_bytes())
    return f"{name} · {when}" if when else name


client = keys.get_clients()
available = client.models()
default_model = params.get("model") or (keys.pick_defaults(available, ["gpt-5.4-mini"], 1) or ["gpt-5.4-mini"])[0]

if locked:
    cond, fund_file, model = default_cond, default_fund, default_model
else:
    ss.setdefault("study_cond", default_cond)
    ss.setdefault("cond_pick", ss.study_cond)
    ss.setdefault("study_model", default_model)
    if available and ss.study_model not in available:
        ss.study_model = available[0]

    def on_pick():  # segmented controls can be deselected; keep the last choice
        if ss.cond_pick is None:
            ss.cond_pick = ss.study_cond
        ss.study_cond = ss.cond_pick

    with st.container(border=True):
        c1, c2, c3 = st.columns([3.2, 2.2, 0.9], vertical_alignment="center")
        c1.segmented_control("Condition", cond_keys, format_func=lambda k: cfg.CONDITIONS[k]["short"],
                             key="cond_pick", on_change=on_pick, label_visibility="collapsed", width="stretch")
        cond = ss.study_cond
        fund_file = c2.selectbox("Factsheet", bundled, index=bundled.index(default_fund), format_func=fund_label,
                                 label_visibility="collapsed")
        with c3.popover("⚙️", width="stretch"):
            model = st.selectbox("Model", available or [ss.study_model], key="study_model")
            st.caption("Participant link — change `pid` per person:")
            st.code(f"/study?condition={cond}&fund={fund_file}&model={model}&pid=P001&lock=1", language=None)
            if st.button("🔄 Start this condition fresh", width="stretch"):
                ss.study.pop(f"{cond}|{fund_file}|{pid}", None)
                st.rerun()
        st.caption(f"**{cfg.CONDITIONS[cond]['name']}** — {cfg.CONDITIONS[cond]['about']}")
    st.query_params.update(condition=cond, fund=fund_file)

cinfo = cfg.CONDITIONS[cond]
pdf_bytes = (FACTSHEETS / fund_file).read_bytes()
fund = te.fund_name_from_pdf(pdf_bytes)
key = f"{cond}|{fund_file}|{pid}"
if key not in ss.study:
    ss.study[key] = {"history": [], "events": [], "start": time.time(), "completed": False, "faq_open": [],
                     "state": None, "open_card": None, "pending": None, "zoom": 100, "cost": 0.0}
S = ss.study[key]


def log(kind: str, detail: str = ""):
    S["events"].append({"t": round(time.time() - S["start"], 1), "type": kind, "detail": detail})


def queue(msg: str, kind: str, card_note: str | None = None):
    if S["completed"] or S["pending"]:
        return
    S["history"].append({"role": "user", "content": msg})
    S["pending"] = {"msg": msg, "card_note": card_note}
    log(kind, msg)


# ---------------- callbacks ----------------

def on_complete():
    S["completed"] = True
    log("mark_complete")
    SESSIONS.mkdir(parents=True, exist_ok=True)
    out = {"pid": pid, "condition": cond, "condition_name": cinfo["name"], "factsheet": fund_file, "model": model,
           "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(S["start"])),
           "seconds_spent": round(time.time() - S["start"], 1), "events": S["events"],
           "history": S["history"], "cost_usd": round(S["cost"], 5),
           "learner_state": S["state"].model_dump() if S["state"] else None}
    name = f"{time.strftime('%Y%m%d-%H%M%S')}_{pid}_{cond}.json"
    (SESSIONS / name).write_text(json.dumps(out, indent=2, ensure_ascii=False))


def on_zoom(d: int):
    S["zoom"] = max(50, min(200, S["zoom"] + d))


def on_example(q: str):
    queue(q, "example_question")


def on_faq_toggle(q: str):
    if q in S["faq_open"]:
        S["faq_open"].remove(q)
        log("faq_close", q)
    else:
        S["faq_open"].append(q)
        log("faq_open", q)


def on_faq_followup(q: str):
    queue(f"Can you tell me more about this: {q}", "faq_followup")


def on_chat():
    msg = (ss.get(f"chat-{key}") or "").strip()
    if msg:
        queue(msg, "typed_question")


def on_card(idx: int, choice: int):
    card = S["history"][idx]["activity"]
    if S["open_card"] != idx or S["pending"] or S["completed"]:
        return
    card["attempts"].append(choice)
    letter, right = chr(65 + choice), choice == card["correct_index"]
    correct = f"{chr(65 + card['correct_index'])}) {card['options'][card['correct_index']]}"
    if right:
        note = f"Participant chose {letter} — CORRECT (attempt {len(card['attempts'])}). Card closed."
    elif len(card["attempts"]) < 2:
        note = (f"Participant chose {letter} — WRONG (attempt 1 of 2). The card is still open: give a gentle hint "
                "without revealing the answer and invite another try.")
    else:
        note = f"Participant chose {letter} — WRONG again (final attempt). Card closed. Kindly reveal {correct} and explain."
    if right or len(card["attempts"]) >= 2:
        card["closed"], S["open_card"] = True, None
    queue(f"I'll go with {letter}) {card['options'][choice]}", "card_answer", note)


# ---------------- header ----------------

if not client.has(model):
    st.error(f"No API key for {model}. Add an OpenAI or Gemini key in the sidebar (🔑 API keys) "
             "or in `.streamlit/secrets.toml`.")
    st.stop()

h1, h2 = st.columns([5, 1], vertical_alignment="center")
with h1:
    st.markdown(f"### 📄 {fund}")
    st.caption("Review the Factsheet and use the available tools to understand the fund")
with h2:
    st.button("Mark Complete →", type="primary", on_click=on_complete, disabled=S["completed"], width="stretch")
if S["completed"]:
    st.success("Thanks — you're all done with this part! Please continue to the next step of the study.")

left, right = st.columns([1.05, 1], gap="large")


# ---------------- left: factsheet viewer ----------------

@st.cache_data(show_spinner=False)
def page_images(data: bytes) -> list[str]:
    doc = pdfium.PdfDocument(data)
    out = []
    for page in doc:
        img = page.render(scale=2.0).to_pil().convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


with left:
    with st.container(border=True):
        a, b, c, d = st.columns([6, 0.8, 1.2, 0.8], vertical_alignment="center")
        a.markdown(f"**📄 {fund}**")
        b.button("−", on_click=on_zoom, args=(-10,), key="zoom-out")
        c.markdown(f"<div style='text-align:center'>Zoom {S['zoom']}%</div>", unsafe_allow_html=True)
        d.button("+", on_click=on_zoom, args=(10,), key="zoom-in")
        imgs = "".join(f'<img src="data:image/jpeg;base64,{p}" style="width:{S["zoom"] * 0.9}%">'
                       for p in page_images(pdf_bytes))
        st.markdown(f'<div class="pdf-scroll">{imgs}</div>', unsafe_allow_html=True)


# ---------------- tutor-only setup ----------------

plan = None
if cond == "tutor":
    with right:
        with st.spinner("Getting your tutor ready…"):
            plan, usage = te.build_plan(client, client.helper("planner", model), pdf_bytes, fund_file)
            S["cost"] += usage.cost
    if S["state"] is None:
        S["state"] = te.initial_state(plan.available_topics())

if not S["history"] and not S["pending"] and not S["completed"]:
    S["pending"] = {"msg": None, "card_note": None}


# ---------------- right: condition panel + chat ----------------

def render_card(idx: int, card: dict):
    with st.container(border=True):
        st.markdown(f"**📝 {card['question']}**")
        is_open = S["open_card"] == idx and not S["pending"] and not S["completed"]
        for i, opt in enumerate(card["options"]):
            label = f"{chr(65 + i)}) {opt}"
            if card["closed"] or i in card["attempts"]:
                mark = "✅" if i == card["correct_index"] and card["closed"] else ("❌" if i in card["attempts"] else "▫️")
                st.markdown(f"{mark} {label}")
            else:
                st.button(label, key=f"card-{key}-{idx}-{i}", on_click=on_card, args=(idx, i),
                          disabled=not is_open, width="stretch")
        if not card["closed"] and card["attempts"]:
            st.caption("One more try 🙂")


with right:
    with st.container(border=True):
        st.markdown(f'<p class="panel-title">{cinfo["panel_title"]}</p><p class="panel-sub">{cinfo["panel_sub"]}</p>',
                    unsafe_allow_html=True)
        with st.container(height=250, border=False):
            if cond == "guided":
                for q in cfg.EXAMPLE_QUESTIONS:
                    st.button(q, key=f"ex-{q}", on_click=on_example, args=(q,), width="stretch",
                              disabled=S["completed"] or bool(S["pending"]))
            elif cond == "hybrid":
                cache = te.load_faq_cache(pdf_bytes, model)
                for i, q_tpl in enumerate(cfg.FAQ_QUESTIONS):
                    q = q_tpl.format(fund=fund)
                    is_open = q in S["faq_open"]
                    st.button(f"{i + 1}.  {q}  {'▴' if is_open else '▾'}", key=f"faq-{i}", on_click=on_faq_toggle,
                              args=(q,), width="stretch")
                    if is_open:
                        if q in cache:
                            st.markdown(f'<div class="faq-answer">{html.escape(cache[q])}</div>', unsafe_allow_html=True)
                        else:
                            ph = st.empty()
                            text = ""
                            pdf = te.pdf_part(pdf_bytes, fund_file)
                            for kind, val in te.stream_text(client, model, te.load_prompt("faq"), te.faq_input(pdf, q)):
                                if kind == "delta":
                                    text += val
                                    ph.markdown(f'<div class="faq-answer">{html.escape(text)} ▌</div>', unsafe_allow_html=True)
                                else:
                                    S["cost"] += val.cost
                            ph.markdown(f'<div class="faq-answer">{html.escape(text)}</div>', unsafe_allow_html=True)
                            te.save_faq_answer(pdf_bytes, model, q, text)
                        st.button("💬 Ask a follow-up about this", key=f"faq-fu-{i}", on_click=on_faq_followup,
                                  args=(q,), disabled=S["completed"] or bool(S["pending"]))
            else:
                for t in S["state"].topics:
                    st.markdown(f'<div class="path-row">{STATUS_ICON[t.status]}&nbsp; {t.topic}</div>',
                                unsafe_allow_html=True)

    with st.container(border=True):
        title = "🧑‍🏫 Your tutor" if cond == "tutor" else "🤖 AI Assistant"
        st.markdown(f'<div class="chat-head">{title}</div>', unsafe_allow_html=True)
        chat = st.container(height=430, border=False)
        with chat:
            for idx, msg in enumerate(S["history"]):
                with st.chat_message(msg["role"], avatar="🧑‍🏫" if msg["role"] == "assistant" else "🙂"):
                    if msg["content"]:
                        st.markdown(msg["content"])
                    act = msg.get("activity")
                    if act and act["type"] == "visual" and plan:
                        ch = charts.factsheet_chart(plan, act["chart"])
                        if ch is not None:
                            st.altair_chart(ch, width="stretch")
                    elif act and act["type"] == "quick_check":
                        render_card(idx, act)
            if S["pending"]:
                with st.chat_message("assistant", avatar="🧑‍🏫"):
                    placeholder = st.empty()
                    placeholder.markdown("_typing…_")
        st.chat_input("Ask a question…", key=f"chat-{key}", on_submit=on_chat,
                      disabled=S["completed"] or bool(S["pending"]))


# ---------------- run the pending assistant turn ----------------

if S["pending"]:
    p = S["pending"]
    pdf = te.pdf_part(pdf_bytes, fund_file)
    text, activities = "", []
    try:
        if cond == "tutor":
            if p["msg"] is not None:
                last_tutor = next((h["content"] + te.describe_activity(h.get("activity"))
                                   for h in reversed(S["history"][:-1]) if h["role"] == "assistant"), "")
                S["state"], u = te.update_learner_state(client, client.helper("tracker", model), plan, S["state"], last_tutor,
                                                        p["msg"], p["card_note"])
                S["cost"] += u.cost
            inp = te.build_tutor_input(pdf, plan, S["history"], S["state"], p["card_note"])
            stream = te.stream_tutor(client, model, te.load_prompt(cinfo["prompt"]), inp,
                                     te.tutor_tools(plan, True, True), "low")
        else:
            inp = te.build_tutor_input(pdf, None, S["history"], None)
            stream = te.stream_text(client, model, te.load_prompt(cinfo["prompt"]), inp)
        for kind, val in stream:
            if kind == "delta":
                text += val
                placeholder.markdown(text + " ▌")
            elif kind == "tool":
                a = te.tool_to_activity(*val, plan)
                if a:
                    activities.append(a)
            else:
                S["cost"] += val.cost
    except Exception as e:
        placeholder.error(f"Something went wrong, please try again. ({e})")
        if p["msg"] is not None:
            S["history"].pop()
        S["pending"] = None
        st.stop()
    act = next((a for a in activities if a["type"] == "quick_check"), None) or (activities[0] if activities else None)
    if act and act["type"] == "quick_check":
        if S["open_card"] is not None:
            S["history"][S["open_card"]]["activity"]["closed"] = True
        S["open_card"] = len(S["history"])
    S["history"].append({"role": "assistant", "content": text.strip(), "activity": act})
    log("assistant_reply", act["type"] if act else "")
    S["pending"] = None
    st.rerun()

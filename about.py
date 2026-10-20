"""'How we built it' page: the design story in plain words, with a few simple visuals."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import charts
import tutor_engine as te
import ui

ss = st.session_state
ui.inject_css()


def simple_bars(df: pd.DataFrame, label: str, value: str, fmt: str, title: str, domain=None) -> alt.Chart:
    """Clean horizontal bars with the number printed at the end: no gridlines, no clutter."""
    x = alt.X(f"{value}:Q", axis=None, scale=alt.Scale(domain=domain) if domain else alt.Undefined)
    base = alt.Chart(df).encode(y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelFontSize=13)), x=x)
    bars = base.mark_bar(cornerRadiusEnd=6, height=22).encode(
        color=alt.Color(f"{label}:N", scale=alt.Scale(range=charts.SERIES), legend=None),
        tooltip=[label, alt.Tooltip(f"{value}:Q", format=fmt)],
    )
    text = base.mark_text(align="left", dx=6, fontSize=13).encode(text=alt.Text(f"{value}:Q", format=fmt))
    return ((bars + text).properties(height=46 * len(df) + 10, title=alt.TitleParams(title, anchor="start", fontSize=14))
            .configure_view(strokeWidth=0).configure_axis(grid=False, domain=False, ticks=False))


# ---------------------------------------------------------------- intro
st.title("How we built it")
st.markdown(
    '<p class="lead">Our study asks a simple question: <b>which way of presenting a mutual-fund factsheet helps '
    "ordinary people understand it best?</b> Every participant sees the same factsheet, with one of three AI "
    "helpers next to it. Afterwards a short survey measures how much they understood. "
    "The AI always explains the fund; it never tells anyone what to invest in.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- three conditions
ui.kicker("The three conditions")
st.subheader("Same factsheet, three kinds of help")
c1, c2, c3 = st.columns(3)
with c1:
    ui.soft_card("🧭", "1 · Guided",
                 "Example questions you can tap, like <i>“What is the minimum SIP?”</i>, plus a chatbot. "
                 "You lead; the examples give you ideas on what to ask.")
with c2:
    ui.soft_card("📚", "2 · Hybrid FAQ",
                 "A list of common questions. Tap one to read a short answer, then ask the chatbot "
                 "if you want to dig deeper.")
with c3:
    ui.soft_card("🧑‍🏫", "3 · Tutor",
                 "A friendly tutor takes you through the factsheet one idea at a time and checks you've "
                 "got it with short questions.")
st.markdown("")
st.markdown(
    "The three differ in **who leads**. In Guided you ask, in Hybrid you read and then ask, "
    "and in the Tutor the AI leads and you respond."
)

# ---------------------------------------------------------------- conditions 1 & 2
ui.kicker("Conditions 1 & 2")
st.subheader("Guided and Hybrid: you ask, the Companion answers")
st.graphviz_chart("""
digraph C {
  rankdir=LR; bgcolor="transparent"; nodesep=0.5; ranksep=0.8;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=13, color="#00000000",
        fontcolor="#111111", margin="0.25,0.15"];
  edge [color="#8e8e93", penwidth=1.4, arrowsize=0.7, fontname="Helvetica", fontsize=11, fontcolor="#8e8e93"];
  you  [label="🙂  You", fillcolor="#ffe3a8"];
  ex   [label="🧭  Tap an example\nquestion (Guided)", fillcolor="#e5e7ee"];
  faq  [label="📚  Open an FAQ\n(Hybrid)", fillcolor="#e5e7ee"];
  ans  [label="📝  Short answer\nwritten once, saved", fillcolor="#c9d7ff"];
  bot  [label="🤖  Companion chatbot\nreads the factsheet", fillcolor="#ffc9c2"];
  you -> ex -> bot;
  you -> faq -> ans;
  ans -> bot [label="ask a follow-up"];
  you -> bot [label="or just type"];
}
""", width="stretch")
c1, c2, c3 = st.columns(3)
with c1:
    ui.soft_card("🤖", "The Companion",
                 "Both conditions use your Companion prompt. It answers exactly what was asked in 2–4 plain "
                 "sentences, puts numbers in context, then suggests one thing worth looking at next.")
with c2:
    ui.soft_card("📚", "FAQ answers are fair",
                 "The first time an FAQ is opened, the AI reads the factsheet and writes a short answer. It's saved, "
                 "so every participant sees exactly the same text.")
with c3:
    ui.soft_card("📄", "It reads the real PDF",
                 "The whole factsheet goes to the AI as a PDF, tables and charts included, so answers quote the "
                 "real figures. Missing info? It says so instead of guessing.")

# ---------------------------------------------------------------- condition 3 intro
ui.kicker("Condition 3")
st.subheader("The Tutor: learn it, don't just read it")
c1, c2, c3 = st.columns(3)
with c1:
    ui.soft_card("💬", "One idea at a time",
                 "Short messages, one concept each, with an everyday example: a SIP is like a gym membership.")
with c2:
    ui.soft_card("🎯", "Then a quick check",
                 "One question at a time, or a tap-to-answer card. Wrong first try? You get a hint, not the answer.")
with c3:
    ui.soft_card("🛡️", "Only the factsheet",
                 "Every number comes from the PDF. No advice, no predictions. If something isn't there, it says so.")

# ---------------------------------------------------------------- how it works
st.markdown("")
st.markdown("##### How the tutor works: three AI helpers, one conversation")
st.markdown(
    "Google's AMIE research (*Nature*, 2026) showed that a great AI conversation isn't just one clever prompt. "
    "It splits the work: one part thinks slowly and prepares, one part talks quickly and warmly. We did the same."
)
st.graphviz_chart("""
digraph G {
  rankdir=LR; bgcolor="transparent"; nodesep=0.6; ranksep=0.9;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=13, color="#00000000",
        fontcolor="#111111", margin="0.25,0.15"];
  edge [color="#8e8e93", penwidth=1.4, arrowsize=0.7, fontname="Helvetica", fontsize=11, fontcolor="#8e8e93"];
  pdf     [label="📄  Factsheet", fillcolor="#e5e7ee"];
  planner [label="📖  Planner\\nreads it once", fillcolor="#c9d7ff"];
  tutor   [label="🧑‍🏫  Tutor\\ntalks to you", fillcolor="#ffc9c2"];
  you     [label="🙂  You", fillcolor="#ffe3a8"];
  tracker [label="📝  Tracker\\nwatches how it's going", fillcolor="#cdeedd"];
  pdf -> planner [label="  "];
  planner -> tutor [label="lesson notes"];
  tutor -> you [label="messages, cards, charts"];
  you -> tracker [label="your replies"];
  tracker -> tutor [label="what to do next"];
}
""", width="stretch")
c1, c2, c3 = st.columns(3)
with c1:
    ui.soft_card("📖", "Planner · prepares",
                 "Reads the whole PDF once and writes teacher notes: exact figures, simple explanations, "
                 "analogies, likely mix-ups, and the numbers for charts.")
with c2:
    ui.soft_card("📝", "Tracker · pays attention",
                 "After every reply it notes: did they get it, partly, or not? Are they confused or bored? "
                 "Which topics are done? Then it suggests the next move.")
with c3:
    ui.soft_card("🧑‍🏫", "Tutor · talks",
                 "Uses the PDF and both sets of notes to reply in a few short, friendly messages. "
                 "This is the part we compare across AI models.")

# ---------------------------------------------------------------- what it sounds like
st.markdown("")
st.markdown("##### What it sounds like: from brochure to texting a friend")
left, right = st.columns(2)
with left:
    st.caption("BEFORE — an early reply (real output)")
    with st.chat_message("assistant", avatar="🧑‍🏫"):
        st.markdown(
            "Hi! We're looking at the **Kotak Flexicap Fund** (a **flexicap** mutual fund / dynamic equity scheme). "
            "In simple terms, it aims for **long-term capital appreciation** by investing across **large, mid, and "
            "small cap** stocks, and it often leans toward **a few selected sectors**.\n\n"
            "We'll go through what it invests in, its benchmark, sector/market-cap mix, costs like expense ratio, "
            "and the key risks/costs like exit load—at your pace. What do you want to start with: **what the fund "
            "is trying to do (objective)**, or **how it invests (sector + market-cap)**?"
        )
with right:
    st.caption("AFTER — the style we now ask for")
    with st.chat_message("assistant", avatar="🧑‍🏫"):
        st.markdown(
            "hey! 👋 so this is the Kotak Flexicap Fund. it can buy companies of any size, big, mid or small, "
            "and it's trying to grow money over the long run\n\n"
            "fun bit: almost a quarter of it is in banks 👀\n\n"
            "wanna pick a topic, or shall we start with what it's actually trying to do?"
        )
    with st.chat_message("user", avatar="🙂"):
        st.markdown("what's a benchmark")
    with st.chat_message("assistant", avatar="🧑‍🏫"):
        st.markdown(
            "it's basically the fund's report card 📊\n\n"
            "this one is compared with the Nifty 500 TRI, a big group of 500 Indian companies. "
            "beat it, and the manager earned their fee\n\n"
            "make sense, or want an example?"
        )
st.caption("The 'after' messages show the target style written into the prompt; real replies vary by model.")

# ---------------------------------------------------------------- inspiration
st.markdown("")
st.markdown("##### Where the ideas came from")
c1, c2, c3, c4 = st.columns(4)
with c1:
    ui.soft_card("🎓", "ChatGPT Study Mode",
                 "Build on what you know, mix up explanations and questions, two tries before the answer, keep it brief.")
with c2:
    ui.soft_card("✨", "Gemini Guided Learning", "Charts and visuals right inside the answer, plus quick quizzes.")
with c3:
    ui.soft_card("🔬", "Google LearnLM",
                 "A 29-point checklist experts use to judge tutors, and a warning: don't hold back answers so long it frustrates people.")
with c4:
    ui.soft_card("🩺", "Google AMIE (Nature)",
                 "A slow thinker and a fast talker working together, tested with simulated learners.")

# ---------------------------------------------------------------- what it can show
st.markdown("")
st.markdown("##### It can show you, not just tell you")
plan = ss.get("plan")
if plan and plan.charts.sector_allocation:
    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(charts.factsheet_chart(plan, "sector_allocation"), width="stretch")
    with right:
        top = max(plan.charts.sector_allocation, key=lambda p: p.value if p.label.lower() not in ("rest", "others") else 0)
        st.markdown(
            f"When you get to *where the money goes*, the tutor can drop this chart into the chat — drawn from the "
            f"factsheet's own numbers.\n\nThen it points out the interesting bit, like **{top.label} at "
            f"{top.value:g}%**, and asks what you think that means for the fund."
        )
else:
    st.info("Open the Tutor Arena once and this section will show a real chart from the factsheet.")

# ---------------------------------------------------------------- live results
lanes = {m: ln for m, ln in (ss.get("lanes") or {}).items() if ln["meta"]}
if lanes:
    ui.kicker("Your session")
    st.subheader("How the tutors are doing")
    graded = {m: ln["grade"]["categories"] for m, ln in lanes.items() if ln.get("grade")}
    left, right = st.columns(2)
    with left:
        speed = pd.DataFrame([{"model": m, "seconds": sum(x["ttft"] for x in ln["meta"]) / len(ln["meta"])}
                              for m, ln in lanes.items()])
        st.altair_chart(simple_bars(speed, "model", "seconds", ".1f", "Seconds until the first word (lower is better)"),
                        width="stretch")
    with right:
        if graded:
            score = pd.DataFrame([{"model": m, "score": sum(v for v in c.values() if v is not None) /
                                   max(1, sum(v is not None for v in c.values()))} for m, c in graded.items()])
            st.altair_chart(simple_bars(score, "model", "score", "+.1f", "Teaching score, −3 to +3 (higher is better)",
                                        domain=[0, 3]), width="stretch")
        else:
            topics = pd.DataFrame([{"model": m, "topics": sum(t.status == "understood" for t in ln["state"].topics)}
                                   for m, ln in lanes.items()])
            st.altair_chart(simple_bars(topics, "model", "topics", "d", "Topics the learner has understood"),
                            width="stretch")
            st.caption("Press **Grade all tutors** in the Arena sidebar to see teaching scores here.")

# ---------------------------------------------------------------- sources
st.divider()
st.caption(
    "Sources: [AMIE, Nature 2026](https://www.nature.com/articles/s41586-026-10764-5) · "
    "[LearnLM paper](https://arxiv.org/abs/2412.16429) · "
    "[LearnLM prompt guide](https://services.google.com/fh/files/misc/learnlm_prompt_guide.pdf) · "
    "[ChatGPT Study Mode prompt](https://simonwillison.net/2025/Jul/29/openai-introducing-study-mode/) · "
    "[Gemini Guided Learning](https://blog.google/products/gemini/new-gemini-tools-students-august-2025/) · "
    "[Kotak Flexicap factsheet](https://www.kotakmf.com/factsheet/July_2026/kotak/Download_pdf/Kotak%20Flexicap%20Fund_Factsheet%20One%20Pager.pdf)"
)

"""Tutor Arena page: friendly AI tutors side by side on a mutual-fund factsheet."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import streamlit as st

import charts
import keys
import tutor_engine as te
import ui

FACTSHEETS = Path(__file__).parent / "factsheets"
MAX_QUESTIONS = 30
DEFAULT_MODELS = ["gpt-5.4-mini", "gemini-4-argon", "gpt-6-sol"]
STATUS_ICON = {"not_started": "⚪", "explained": "🟡", "understood": "🟢", "needs_help": "🔴"}
LANE_ICONS = ["⚡", "🔵", "🟣"]
QUICK_REPLIES = ["🤔 I'm confused", "💡 Give me an example", "➡️ Next topic", "👋 I'm done for today"]

ss = st.session_state
ss.setdefault("system_prompt", te.load_prompt("tutor_friend"))
ss.setdefault("prompt_draft", ss.system_prompt)
ss.setdefault("lanes", {})
ss.setdefault("questions_used", 0)
ss.setdefault("plan", None)
ss.setdefault("plan_key", None)
ss.setdefault("aux_cost", {})       # planner / tracker / simulator / grader spend, by model
ss.setdefault("pending", {})        # model -> {"msg": str | None, "card_note": str | None}
ss.setdefault("active_models", [])
ss.setdefault("sim_remaining", 0)
ss.setdefault("grade_request", False)


# ---------------- state helpers ----------------

def reset_conversation():
    ss.lanes, ss.pending, ss.questions_used, ss.sim_remaining = {}, {}, 0, 0


def lane(model: str) -> dict:
    if model not in ss.lanes:
        topics = ss.plan.available_topics() if ss.plan else None
        ss.lanes[model] = {"history": [], "state": te.initial_state(topics), "meta": [], "cost": 0.0,
                           "open_card": None, "grade": None}
    return ss.lanes[model]


def add_aux_cost(usage: te.Usage):
    ss.aux_cost[usage.model] = ss.aux_cost.get(usage.model, 0.0) + usage.cost


def queue_message(models: list[str], msg: str):
    for m in models:
        lane(m)["history"].append({"role": "user", "content": msg})
        ss.pending[m] = {"msg": msg, "card_note": None}


def answer_card(m: str, choice: int) -> tuple[str, str]:
    """Record a card attempt; returns (participant message, reliable note for tutor/tracker)."""
    ln = lane(m)
    card = ln["history"][ln["open_card"]]["activity"]
    card["attempts"].append(choice)
    letter, right = chr(65 + choice), choice == card["correct_index"]
    correct = f"{chr(65 + card['correct_index'])}) {card['options'][card['correct_index']]}"
    msg = f"I'll go with {letter}) {card['options'][choice]}"
    if right:
        note = f"Participant chose {letter} — CORRECT (attempt {len(card['attempts'])}). Card closed."
    elif len(card["attempts"]) < 2:
        note = (f"Participant chose {letter} — WRONG (attempt 1 of 2). The card is still open: give a gentle "
                f"hint without revealing the answer and invite another try.")
    else:
        note = (f"Participant chose {letter} — WRONG again (final attempt). Card closed. Kindly reveal the right "
                f"answer ({correct}) and explain it simply.")
    if right or len(card["attempts"]) >= 2:
        card["closed"] = True
        ln["open_card"] = None
    return msg, note


# ---------------- callbacks (run before the script reruns) ----------------

def on_chat_submit():
    msg = (ss.get("chat_box") or "").strip()
    if msg and ss.questions_used < MAX_QUESTIONS:
        ss.questions_used += 1
        queue_message(ss.active_models, msg)


def on_quick_reply(label: str):
    if ss.questions_used < MAX_QUESTIONS:
        ss.questions_used += 1
        queue_message(ss.active_models, label.split(" ", 1)[1])


def on_card_click(m: str, choice: int):
    if lane(m)["open_card"] is None or m in ss.pending:
        return
    ss.questions_used += 1
    msg, note = answer_card(m, choice)
    lane(m)["history"].append({"role": "user", "content": msg})
    ss.pending[m] = {"msg": msg, "card_note": note}


PRESETS = {"Friendly tutor v2": "tutor_friend", "Original tutor draft": "tutor_original",
           "Companion (condition 2)": "companion"}


def on_preset():
    ss.prompt_draft = te.load_prompt(PRESETS[ss.preset])


def on_grade():
    ss.grade_request = True


def on_sim_start():
    ss.sim_remaining = ss.get("sim_turns", 4)


def on_sim_stop():
    ss.sim_remaining = 0


client = keys.get_clients()
available = client.models()


def helper_index(role: str) -> int | None:
    """Default planner/tracker pick: same provider as the first tutor, if its key is set."""
    if not available:
        return None
    m = client.helper(role, models[0] if models else None)
    return available.index(m) if m in available else 0


# ---------------- sidebar ----------------

with st.sidebar:
    st.subheader("📁 1. Factsheet")
    bundled = sorted(p.name for p in FACTSHEETS.glob("*.pdf"))
    choice = st.selectbox("Choose a factsheet", bundled + ["Upload my own…"], label_visibility="collapsed")
    if choice == "Upload my own…":
        up = st.file_uploader("Upload PDF", type="pdf")
        pdf_bytes, pdf_name = (up.getvalue(), up.name) if up else (None, None)
    else:
        pdf_bytes, pdf_name = (FACTSHEETS / choice).read_bytes(), choice
    if pdf_bytes:
        st.success("PDF loaded natively.")

    st.divider()
    st.subheader("🤖 2. Tutors")
    view = st.radio("View", ["Arena (side by side)", "Participant preview"], horizontal=True)
    if view.startswith("Arena"):
        models = st.multiselect("Tutor models (max 3)", available,
                                default=keys.pick_defaults(available, DEFAULT_MODELS, 3),
                                max_selections=3, accept_new_options=True)
    else:
        models = [m for m in [st.selectbox("Tutor model", available)] if m]
    tutor_effort = st.select_slider("Tutor thinking (gpt-5/6, Gemini)", ["none", "minimal", "low", "medium"],
                                    value="low")

    with st.expander("🧭 Teaching scaffolding"):
        use_planner = st.toggle("Planner writes teacher notes", value=True,
                                help="A slower model studies the factsheet once: facts, analogies, scenarios, chart data.")
        planner_model = st.selectbox("Planner model", available, index=helper_index("planner"),
                                     disabled=not use_planner)
        use_tracker = st.toggle("Tracker keeps learner notes", value=True,
                                help="A fast model judges each reply and the learner's mood, and suggests the next move.")
        tracker_model = st.selectbox("Tracker model", available, index=helper_index("tracker"),
                                     disabled=not use_tracker)
        tracker_timing = st.radio("Tracker runs", ["before reply (smarter)", "after reply (faster)"],
                                  disabled=not use_tracker)
        use_cards = st.toggle("Interactive quick-check cards", value=True)
        use_visuals = st.toggle("Charts inside answers", value=True, disabled=not use_planner)
        attach_pdf = st.toggle("Send PDF to tutor every turn", value=True)
        show_notes = st.toggle("Show tutor's private notes (arena)", value=True)

    with st.expander("🎭 Simulated learner (self-play)"):
        persona_name = st.selectbox("Persona", list(te.PERSONAS) + ["Custom…"])
        persona = (st.text_area("Describe the learner", "You are ...") if persona_name == "Custom…"
                   else te.PERSONAS[persona_name])
        sim_model = st.selectbox("Simulator model", available, index=helper_index("tracker"))
        st.number_input("Turns to play", 1, 15, 4, key="sim_turns")
        s1, s2 = st.columns(2)
        s1.button("▶️ Play", on_click=on_sim_start, width="stretch")
        s2.button("⏹ Stop", on_click=on_sim_stop, width="stretch")

    with st.expander("📊 Grade conversations"):
        grader_model = st.selectbox("Grader model", available, index=helper_index("planner"))
        st.caption("Scores each tutor on the LearnLM pedagogy rubric (29 items) plus 5 study-protocol checks, "
                   "and fact-checks it against the factsheet.")
        st.button("Grade all tutors", on_click=on_grade, width="stretch")

    st.divider()
    st.subheader("⏳ Progress")
    st.progress(min(ss.questions_used / MAX_QUESTIONS, 1.0))
    st.caption(f"Questions used: **{ss.questions_used}/{MAX_QUESTIONS}**")

    st.divider()
    st.subheader("🧠 3. Tutor persona")
    st.selectbox("Load a preset", list(PRESETS), key="preset", on_change=on_preset,
                 help="Friendly v2 = upgraded tutor. The other two are your original prompts, for comparison.")
    ss.prompt_draft = st.text_area("System instructions", ss.prompt_draft, height=260)
    c1, c2 = st.columns(2)
    if c1.button("Submit Prompt", type="primary", width="stretch"):
        ss.system_prompt = ss.prompt_draft
        reset_conversation()
        st.rerun()
    if c2.button("↺ Reset Prompt", width="stretch"):
        ss.system_prompt = ss.prompt_draft = te.load_prompt("tutor_friend")
        reset_conversation()
        st.rerun()

    st.divider()
    st.subheader("💰 Session bill")
    total = 0.0
    for m, ln in ss.lanes.items():
        st.caption(f"{m} (tutor): **${ln['cost']:.5f}**")
        total += ln["cost"]
    for m, c in ss.aux_cost.items():
        st.caption(f"{m} (helpers): **${c:.5f}**")
        total += c
    st.markdown(f"**Total ≈ ${total:.4f}**")

    st.divider()
    if st.button("🔄 Restart conversation", width="stretch"):
        reset_conversation()
        st.rerun()
    export = {
        "factsheet": pdf_name, "system_prompt": ss.system_prompt,
        "plan": ss.plan.model_dump() if ss.plan else None,
        "lanes": {m: {"history": ln["history"], "learner_state": ln["state"].model_dump(), "turns": ln["meta"],
                      "grade": ln["grade"]} for m, ln in ss.lanes.items()},
    }
    st.download_button("⬇️ Export transcript (JSON)", json.dumps(export, indent=2, ensure_ascii=False),
                       file_name="tutor_transcript.json", width="stretch")


# ---------------- setup ----------------

ui.inject_css()
st.title("🧑‍🏫 Factsheet Tutor Arena")

if not available:
    st.info("Add an OpenAI and/or Gemini API key in the sidebar (🔑 API keys), or put `OPENAI_API_KEY` / "
            "`GEMINI_API_KEY` in `.streamlit/secrets.toml`.")
    st.stop()
if not pdf_bytes:
    st.info("Pick or upload a factsheet in the sidebar to start.")
    st.stop()
if not models:
    st.info("Pick at least one tutor model.")
    st.stop()

ss.active_models = list(models)

# Slow agent: prepare teacher notes once per factsheet.
plan_key = (te.pdf_hash(pdf_bytes), planner_model) if use_planner else ("none", te.pdf_hash(pdf_bytes))
if plan_key != ss.plan_key:
    ss.plan, ss.plan_key = None, plan_key
    reset_conversation()
    if use_planner:
        with st.status("📖 Your tutor is reading the factsheet and preparing notes…", expanded=False) as s:
            try:
                ss.plan, usage = te.build_plan(client, planner_model, pdf_bytes, pdf_name)
                add_aux_cost(usage)
                s.update(label=f"📖 Notes ready for {ss.plan.fund_name}", state="complete")
            except Exception as e:
                ss.plan_key = None
                s.update(label="Couldn't prepare notes", state="error")
                st.error(f"Planner failed: {e}")
                st.stop()
plan: te.LessonPlan | None = ss.plan
if plan:
    st.caption(f"**{plan.fund_name}** · {plan.category}")

# Tutor speaks first in any lane that hasn't started yet.
for m in models:
    if not lane(m)["history"] and m not in ss.pending:
        ss.pending[m] = {"msg": None, "card_note": None}

# Simulated learner: generate the next participant message for every lane (AMIE-style self-play).
if ss.sim_remaining > 0 and not ss.pending:
    with st.status(f"🎭 Simulated learner is typing… ({ss.sim_remaining} turn(s) left)") as s:
        results: dict[str, tuple] = {}

        def sim_worker(m, history, card):
            try:
                results[m] = te.simulate_learner(client, sim_model, persona, history, card, ss_turns)
            except Exception as e:
                results[m] = e

        ss_turns = ss.sim_remaining
        threads = []
        for m in models:
            ln = lane(m)
            card = ln["history"][ln["open_card"]]["activity"] if ln["open_card"] is not None else None
            t = threading.Thread(target=sim_worker, args=(m, list(ln["history"]), card), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        for m, res in results.items():
            if isinstance(res, Exception):
                st.error(f"Simulator failed for {m}: {res}")
                ss.sim_remaining = 0
                continue
            reply, usage = res
            add_aux_cost(usage)
            ln = lane(m)
            if ln["open_card"] is not None and reply.card_choice is not None and \
                    0 <= reply.card_choice < len(ln["history"][ln["open_card"]]["activity"]["options"]):
                msg, note = answer_card(m, reply.card_choice)
                ln["history"].append({"role": "user", "content": msg, "sim": True})
                ss.pending[m] = {"msg": msg, "card_note": note}
            else:
                ln["history"].append({"role": "user", "content": reply.message, "sim": True})
                ss.pending[m] = {"msg": reply.message, "card_note": None}
        ss.sim_remaining = max(ss.sim_remaining - 1, 0)
        s.update(state="complete")

# Grader: score each conversation on the LearnLM rubric.
if ss.grade_request:
    ss.grade_request = False
    to_grade = [m for m in models if len(lane(m)["history"]) >= 3]
    if not to_grade:
        st.warning("Have a bit more conversation first (at least one back-and-forth).")
    else:
        with st.status("📊 Grading conversations on the LearnLM rubric…") as s:
            results = {}

            def grade_worker(m, history):
                try:
                    results[m] = te.grade_conversation(client, grader_model, pdf_bytes, pdf_name, history)
                except Exception as e:
                    results[m] = e

            threads = [threading.Thread(target=grade_worker, args=(m, list(lane(m)["history"])), daemon=True)
                       for m in to_grade]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            for m, res in results.items():
                if isinstance(res, Exception):
                    st.error(f"Grader failed for {m}: {res}")
                    continue
                grade, usage = res
                add_aux_cost(usage)
                lane(m)["grade"] = {"items": [i.model_dump() for i in grade.items], "inaccuracies": grade.inaccuracies,
                                    "strengths": grade.strengths, "improvements": grade.improvements,
                                    "categories": te.category_means(grade), "at_turn": len(lane(m)["history"])}
            s.update(label="📊 Grading done", state="complete")


# ---------------- rendering ----------------

is_arena = view.startswith("Arena")


def render_path(state: te.LearnerState):
    done = sum(t.status == "understood" for t in state.topics)
    dots = "".join("●" if t.status == "understood" else ("◐" if t.status != "not_started" else "○")
                   for t in state.topics)
    now = "" if state.current_topic in ("", "none") else f" · now: {state.current_topic.lower()}"
    st.markdown(f'<div class="dots">{dots} &nbsp;{done}/{len(state.topics)} topics{now}</div>',
                unsafe_allow_html=True)


def render_notes(state: te.LearnerState):
    with st.expander("🗒️ Tutor's private notes"):
        st.markdown(" ".join(f"{STATUS_ICON[t.status]} {t.topic}" for t in state.topics))
        st.caption(f"Last reply: **{state.last_reply_type}** · Mood: **{state.affect}** · "
                   f"Level: **{state.learner_level}** · Now on: **{state.current_topic}**")
        st.caption(f"Background: {state.known_background}")
        if state.misconceptions:
            st.caption("Misconceptions: " + "; ".join(state.misconceptions))
        st.caption(f"Next move: {state.next_move}")


def render_activity(m: str, idx: int, activity: dict):
    if activity["type"] == "visual" and plan:
        chart = charts.factsheet_chart(plan, activity["chart"])
        if chart is not None:
            st.altair_chart(chart, width="stretch")
    elif activity["type"] == "quick_check":
        with st.container(border=True):
            st.markdown(f"**📝 {activity['question']}**")
            is_open = lane(m)["open_card"] == idx and m not in ss.pending
            for i, opt in enumerate(activity["options"]):
                label = f"{chr(65 + i)}) {opt}"
                if activity["closed"] or i in activity["attempts"]:
                    mark = "✅" if i == activity["correct_index"] and activity["closed"] else (
                        "❌" if i in activity["attempts"] else "▫️")
                    st.markdown(f"{mark} {label}")
                else:
                    st.button(label, key=f"card-{m}-{idx}-{i}", on_click=on_card_click, args=(m, i),
                              disabled=not is_open, width="stretch")
            if not activity["closed"] and activity["attempts"]:
                st.caption("One more try 🙂")


def render_grade(grade: dict):
    with st.expander(f"📊 Pedagogy scores (graded at message {grade['at_turn']})"):
        st.markdown(" · ".join(f"**{c}** {v:+.1f}" if v is not None else f"**{c}** n/a"
                               for c, v in grade["categories"].items()))
        if grade["inaccuracies"]:
            st.error("Inaccuracies: " + "; ".join(grade["inaccuracies"]))
        st.caption(f"👍 {grade['strengths']}")
        st.caption(f"🔧 {grade['improvements']}")
        st.dataframe([{"item": i["item"], "score": i["score"], "evidence": i["evidence"]} for i in grade["items"]],
                     hide_index=True, width="stretch")


graded = {m: lane(m)["grade"]["categories"] for m in models if lane(m)["grade"]}
if is_arena and len(graded) >= 1:
    with st.expander("📊 Rubric comparison", expanded=False):
        st.altair_chart(charts.rubric_comparison(graded), width="stretch")

columns = st.columns(len(models)) if is_arena else [st.container()]
placeholders: dict = {}
for i, (col, m) in enumerate(zip(columns, models)):
    ln = lane(m)
    with col:
        if is_arena:
            st.subheader(f"{LANE_ICONS[i % 3]} {m}")
        if use_tracker and plan:
            render_path(ln["state"])
        tutor_turn = 0
        for idx, msg in enumerate(ln["history"]):
            avatar = "🧑‍🏫" if msg["role"] == "assistant" else ("🎭" if msg.get("sim") else "🙂")
            with st.chat_message(msg["role"], avatar=avatar):
                if msg["content"]:
                    st.markdown(msg["content"])
                if msg.get("activity"):
                    render_activity(m, idx, msg["activity"])
                if msg["role"] == "assistant":
                    if is_arena and tutor_turn < len(ln["meta"]):
                        meta = ln["meta"][tutor_turn]
                        st.caption(f"⏱ {meta['ttft']:.1f}s to first word · ${meta['cost']:.4f}")
                    tutor_turn += 1
        if m in ss.pending:
            with st.chat_message("assistant", avatar="🧑‍🏫"):
                placeholders[m] = st.empty()
                placeholders[m].markdown("_typing…_")
        if is_arena and show_notes and use_tracker and ln["history"]:
            render_notes(ln["state"])
        if is_arena and ln["grade"]:
            render_grade(ln["grade"])

if not ss.pending and ss.questions_used < MAX_QUESTIONS and ss.sim_remaining == 0:
    qcols = st.columns(len(QUICK_REPLIES))
    for col, label in zip(qcols, QUICK_REPLIES):
        col.button(label, on_click=on_quick_reply, args=(label,), width="stretch")
st.chat_input(f"Reply to your tutor ({ss.questions_used + 1}/{MAX_QUESTIONS})…", key="chat_box",
              on_submit=on_chat_submit, disabled=ss.questions_used >= MAX_QUESTIONS)


# ---------------- run pending tutor turns (parallel, streamed) ----------------

def run_lane(m: str, job: dict, buf: dict):
    """Runs in a worker thread: no Streamlit calls here, only plain data in/out."""
    try:
        t0 = time.perf_counter()
        state = job["state"]
        track = job["use_tracker"] and job["user_msg"] is not None

        def do_track():
            new_state, u = te.update_learner_state(client, job["tracker_model"], job["plan"], state,
                                                   job["last_tutor"], job["user_msg"], job["card_note"])
            buf["aux"].append(u)
            return new_state

        if track and job["track_first"]:
            state = do_track()
        buf["phase"] = "typing"
        tutor_input = te.build_tutor_input(job["pdf"], job["plan"], job["history"],
                                           state if job["use_tracker"] else None, job["card_note"])
        for kind, val in te.stream_tutor(client, m, job["system_prompt"], tutor_input, job["tools"], job["effort"]):
            if kind == "delta":
                if buf["ttft"] is None:
                    buf["ttft"] = time.perf_counter() - t0
                buf["text"] += val
            elif kind == "tool":
                act = te.tool_to_activity(*val, job["plan"])
                if act:
                    buf["activities"].append(act)
            else:
                buf["usage"] = val
        buf["total"] = time.perf_counter() - t0
        if track and not job["track_first"]:
            state = do_track()
        buf["state"] = state
    except Exception as e:  # surfaced in the lane
        buf["error"] = str(e)
    finally:
        buf["done"] = True


if ss.pending:
    pdf = te.pdf_part(pdf_bytes, pdf_name) if attach_pdf else None
    tools = te.tutor_tools(plan, use_cards, use_visuals and use_planner)
    bufs: dict[str, dict] = {}
    threads = []
    for m, p in ss.pending.items():
        if m not in models:
            continue
        ln = lane(m)
        last_tutor = ""
        for h in reversed(ln["history"][:-1] if p["msg"] is not None else ln["history"]):
            if h["role"] == "assistant":
                last_tutor = h["content"] + ("\n" + te.describe_activity(h.get("activity")) if h.get("activity") else "")
                break
        job = {
            "state": ln["state"], "use_tracker": use_tracker, "tracker_model": tracker_model,
            "track_first": tracker_timing.startswith("before"), "plan": plan, "last_tutor": last_tutor,
            "user_msg": p["msg"], "card_note": p["card_note"], "pdf": pdf, "history": list(ln["history"]),
            "system_prompt": ss.system_prompt, "effort": tutor_effort, "tools": tools,
        }
        bufs[m] = {"text": "", "phase": "thinking", "done": False, "error": None, "ttft": None, "total": 0.0,
                   "usage": None, "state": ln["state"], "aux": [], "activities": []}
        t = threading.Thread(target=run_lane, args=(m, job, bufs[m]), daemon=True)
        t.start()
        threads.append(t)

    # Live typing effect: poll the worker buffers and repaint each lane.
    while not all(b["done"] for b in bufs.values()):
        for m, b in bufs.items():
            placeholders[m].markdown(b["text"] + " ▌" if b["text"] else "_typing…_")
        time.sleep(0.05)
    for t in threads:
        t.join()

    failed = {}
    for m, b in bufs.items():
        ln = lane(m)
        for u in b["aux"]:
            add_aux_cost(u)
        if b["error"]:
            failed[m] = ss.pending[m]
            placeholders[m].error(f"{m}: {b['error']}")
            continue
        activity = next((a for a in b["activities"] if a["type"] == "quick_check"), None) or \
            (b["activities"][0] if b["activities"] else None)
        if activity and activity["type"] == "quick_check":
            if ln["open_card"] is not None:  # a new card replaces any unanswered one
                ln["history"][ln["open_card"]]["activity"]["closed"] = True
            ln["open_card"] = len(ln["history"])
        ln["history"].append({"role": "assistant", "content": b["text"].strip(), "activity": activity})
        ln["state"] = b["state"]
        usage = b["usage"] or te.Usage(m)
        ln["cost"] += usage.cost
        ln["meta"].append({"ttft": b["ttft"] or b["total"], "total": b["total"], "cost": usage.cost,
                           "usage": usage.as_dict(), "learner_state": b["state"].model_dump(),
                           "activity": activity["type"] if activity else None})
    ss.pending = failed  # failed lanes retry on the next rerun
    if failed:
        ss.sim_remaining = 0
        st.button("🔁 Retry", key="retry")
    else:
        st.rerun()

"""Tutor engine: planner (slow), learner tracker (fast), streaming friendly tutor with
interactive cards and charts, a simulated learner, and a LearnLM-rubric grader.

Design sources:
- AMIE (Nature, 2026): fast dialogue agent + slow planning agent + persistent state,
  and simulated-dialogue self-play for testing.
- ChatGPT Study Mode: build on what the learner knows, check & reinforce, vary the
  rhythm (explain / question / activity / teach-back), two tries before revealing.
- Gemini Guided Learning / LearnLM: visuals inside answers, interactive checks, a
  visible learning path, and the LearnLM pedagogy rubric for evaluation.

Every model call goes through `Clients`, which routes `gemini-*` models to the Gemini API
(google-genai) and everything else to the OpenAI Responses API. Inputs are written in the
OpenAI Responses format and converted for Gemini.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterator, Literal

import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as gtypes
from pydantic import BaseModel

PROMPTS = Path(__file__).parent / "prompts"
PLAN_CACHE = Path(__file__).parent / "plans"

TOPICS = [
    "Scheme type",
    "Investment objective",
    "Benchmark",
    "Sector allocation",
    "Returns or value over time",
    "Minimum SIP",
    "Taxation",
    "Exit load",
    "Suitability and investment horizon",
    "Sharpe ratio",
]

# USD per 1M tokens: (input, cached input, output). Approximate; edit as prices change.
# Any model id not listed here still works (typed into a model picker); its cost shows as $0.
PRICES = {
    # OpenAI
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
    # Google Gemini (gemini-4-argon at its introductory price)
    "gemini-4-argon": (2.00, 0.20, 10.00),
    "gemini-3.1-pro-preview": (2.00, 0.20, 12.00),
    "gemini-3.5-flash": (1.50, 0.15, 9.00),
    "gemini-3.1-flash-lite": (0.25, 0.025, 1.50),
}

# Helper models (planner, tracker) to use when only one provider's key is set.
HELPER_MODELS = {
    "openai": {"planner": "gpt-5.4-mini", "tracker": "gpt-5.4-nano"},
    "gemini": {"planner": "gemini-3.5-flash", "tracker": "gemini-3.1-flash-lite"},
}


def is_gemini(model: str) -> bool:
    return model.startswith("gemini")


def provider(model: str) -> str:
    return "gemini" if is_gemini(model) else "openai"


class Clients:
    """One OpenAI and/or one Gemini client; each call picks the one its model needs."""

    def __init__(self, openai_key: str | None = None, gemini_key: str | None = None):
        self.openai = openai.OpenAI(api_key=openai_key) if openai_key else None
        self.gemini = genai.Client(api_key=gemini_key) if gemini_key else None

    def has(self, model: str) -> bool:
        return (self.gemini if is_gemini(model) else self.openai) is not None

    def models(self) -> list[str]:
        return [m for m in PRICES if self.has(m)]

    def helper(self, role: str, prefer: str | None = None) -> str:
        """Planner/tracker model: same provider as `prefer` if possible, else whichever key is set."""
        order = [provider(prefer)] if prefer else []
        order += [p for p in ("openai", "gemini") if p not in order]
        for p in order:
            if (self.gemini if p == "gemini" else self.openai) is not None:
                return HELPER_MODELS[p][role]
        raise RuntimeError("No API key set. Add an OpenAI or Gemini key in the sidebar.")

    def oai(self) -> openai.OpenAI:
        if self.openai is None:
            raise RuntimeError("This model needs an OpenAI API key. Add one in the sidebar.")
        return self.openai

    def gem(self) -> genai.Client:
        if self.gemini is None:
            raise RuntimeError("This model needs a Gemini API key. Add one in the sidebar.")
        return self.gemini

CHARTS = {
    "sector_allocation": "Sector allocation",
    "market_cap_split": "Large / mid / small cap split",
    "returns_vs_benchmark": "Returns vs benchmark",
}


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


# ---------- schemas ----------

class TopicCard(BaseModel):
    topic: str
    available: bool
    facts: list[str]
    plain_explanation: str
    everyday_analogy: str
    check_question: str
    common_misconception: str
    scenario_idea: str


class ChartPoint(BaseModel):
    label: str
    value: float


class ReturnRow(BaseModel):
    period: str
    fund: float
    benchmark: float | None


class ChartData(BaseModel):
    sector_allocation: list[ChartPoint]
    market_cap_split: list[ChartPoint]
    returns: list[ReturnRow]
    returns_note: str


class LessonPlan(BaseModel):
    fund_name: str
    category: str
    overview: str
    topics: list[TopicCard]
    noteworthy: list[str]
    charts: ChartData

    def available_topics(self) -> list[str]:
        return [t.topic for t in self.topics if t.available]

    def available_charts(self) -> list[str]:
        c = self.charts
        out = []
        if c.sector_allocation:
            out.append("sector_allocation")
        if c.market_cap_split:
            out.append("market_cap_split")
        if c.returns:
            out.append("returns_vs_benchmark")
        return out


class TopicStatus(BaseModel):
    topic: str
    status: Literal["not_started", "explained", "understood", "needs_help"]


class LearnerState(BaseModel):
    last_reply_type: Literal[
        "start", "answer_correct", "answer_partial", "answer_incorrect", "confused",
        "question", "topic_change", "wants_to_end", "advice_request", "off_topic", "chitchat",
    ]
    affect: Literal["engaged", "neutral", "unsure", "frustrated", "bored"]
    topics: list[TopicStatus]
    current_topic: str
    learner_level: Literal["beginner", "some_knowledge", "confident"]
    known_background: str
    misconceptions: list[str]
    next_move: str


def initial_state(topics: list[str] | None = None) -> LearnerState:
    return LearnerState(
        last_reply_type="start",
        affect="neutral",
        topics=[TopicStatus(topic=t, status="not_started") for t in (topics or TOPICS)],
        current_topic="none",
        learner_level="beginner",
        known_background="unknown",
        misconceptions=[],
        next_move="Greet the participant warmly and give your first message.",
    )


# ---------- helpers ----------

def pdf_part(pdf_bytes: bytes, filename: str) -> dict:
    b64 = base64.b64encode(pdf_bytes).decode()
    return {"type": "input_file", "filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}


def pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


def model_options(model: str, effort: str | None, verbosity: str | None = None) -> dict:
    """Reasoning/verbosity knobs only exist on reasoning models (gpt-5*, gpt-6*, o*)."""
    if not model.startswith(("gpt-5", "gpt-6", "o")):
        return {}
    opts: dict = {}
    if effort:
        opts["reasoning"] = {"effort": effort}
    if verbosity:
        opts["text"] = {"verbosity": verbosity}
    return opts


def call_with_fallback(fn: Callable, **kwargs):
    """Retry once without optional knobs if a model rejects them."""
    try:
        return fn(**kwargs)
    except openai.BadRequestError as e:
        msg = str(e).lower()
        optional = "reasoning" in kwargs or "verbosity" in json.dumps(kwargs.get("text", {}))
        if not optional or not any(w in msg for w in ("reasoning", "effort", "verbosity", "unsupported", "not supported")):
            raise
        kwargs.pop("reasoning", None)
        text = {k: v for k, v in kwargs.pop("text", {}).items() if k != "verbosity"}
        if text:
            kwargs["text"] = text
        return fn(**kwargs)


class Usage:
    def __init__(self, model: str, input_tokens=0, cached_tokens=0, output_tokens=0):
        self.model = model
        self.input_tokens = input_tokens
        self.cached_tokens = cached_tokens
        self.output_tokens = output_tokens

    @classmethod
    def from_response(cls, model: str, usage) -> "Usage":
        if usage is None:
            return cls(model)
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0
        return cls(model, usage.input_tokens or 0, cached, usage.output_tokens or 0)

    @classmethod
    def from_gemini(cls, model: str, meta) -> "Usage":
        if meta is None:
            return cls(model)
        out = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
        return cls(model, meta.prompt_token_count or 0, meta.cached_content_token_count or 0, out)

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.model, self.input_tokens + other.input_tokens, self.cached_tokens + other.cached_tokens,
                     self.output_tokens + other.output_tokens)

    @property
    def cost(self) -> float:
        price = PRICES.get(self.model)
        if not price:
            return 0.0
        p_in, p_cached, p_out = price
        uncached = max(self.input_tokens - self.cached_tokens, 0)
        return (uncached * p_in + self.cached_tokens * p_cached + self.output_tokens * p_out) / 1e6

    def as_dict(self) -> dict:
        return {"model": self.model, "input_tokens": self.input_tokens, "cached_tokens": self.cached_tokens,
                "output_tokens": self.output_tokens, "cost_usd": round(self.cost, 6)}


# ---------- Gemini adapter ----------

GEMINI_THINKING = {"none": "minimal", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high"}


def _gemini_parts(content) -> list:
    if isinstance(content, str):
        return [gtypes.Part.from_text(text=content)]
    parts = []
    for c in content:
        if c["type"] == "input_file":
            data = base64.b64decode(c["file_data"].split(",", 1)[1])
            parts.append(gtypes.Part.from_bytes(data=data, mime_type="application/pdf"))
        elif "text" in c:
            parts.append(gtypes.Part.from_text(text=c["text"]))
    return parts


def to_gemini_contents(inp) -> list:
    """OpenAI Responses-style input (a string or role/content items) -> Gemini contents.
    Gemini has no mid-conversation developer role, so those notes become labelled user turns."""
    if isinstance(inp, str):
        return [gtypes.Content(role="user", parts=_gemini_parts(inp))]
    out = []
    for item in inp:
        content = item["content"]
        if item["role"] == "developer":
            content = f"[Private note from the app, not written by the participant]\n{content}"
        role = "model" if item["role"] == "assistant" else "user"
        out.append(gtypes.Content(role=role, parts=_gemini_parts(content)))
    return out


def _gemini_config(instructions: str, effort: str | None, **extra) -> dict:
    cfg = {"system_instruction": instructions, **extra}
    if effort in GEMINI_THINKING:
        cfg["thinking_config"] = gtypes.ThinkingConfig(thinking_level=GEMINI_THINKING[effort])
    return cfg


def _rejects_thinking(e: Exception) -> bool:
    return isinstance(e, genai_errors.ClientError) and any(
        w in str(e).lower() for w in ("thinking", "not supported", "unsupported"))


def gemini_generate(clients: Clients, model: str, contents: list, cfg: dict):
    """Retry once without the thinking knob if a model rejects it."""
    try:
        return clients.gem().models.generate_content(model=model, contents=contents,
                                                     config=gtypes.GenerateContentConfig(**cfg))
    except genai_errors.ClientError as e:
        if "thinking_config" not in cfg or not _rejects_thinking(e):
            raise
        cfg = {k: v for k, v in cfg.items() if k != "thinking_config"}
        return clients.gem().models.generate_content(model=model, contents=contents,
                                                     config=gtypes.GenerateContentConfig(**cfg))


def gemini_stream(clients: Clients, model: str, contents: list, cfg: dict) -> Iterator:
    """Streaming version of `gemini_generate`; errors surface on the first chunk, so peek it."""
    def open_stream(c: dict):
        it = iter(clients.gem().models.generate_content_stream(model=model, contents=contents,
                                                                config=gtypes.GenerateContentConfig(**c)))
        return it, next(it, None)
    try:
        it, first = open_stream(cfg)
    except genai_errors.ClientError as e:
        if "thinking_config" not in cfg or not _rejects_thinking(e):
            raise
        it, first = open_stream({k: v for k, v in cfg.items() if k != "thinking_config"})
    if first is not None:
        yield first
    yield from it


def parse(clients: Clients, model: str, instructions: str, inp, schema: type[BaseModel],
          effort: str | None) -> tuple[BaseModel, Usage]:
    """Structured output from either provider, validated into `schema`."""
    if is_gemini(model):
        cfg = _gemini_config(instructions, effort, response_mime_type="application/json",
                             response_json_schema=schema.model_json_schema())
        resp = gemini_generate(clients, model, to_gemini_contents(inp), cfg)
        if not resp.text:
            raise RuntimeError(f"{model} returned no JSON (finish reason: "
                               f"{resp.candidates[0].finish_reason if resp.candidates else 'unknown'}).")
        return schema.model_validate_json(resp.text), Usage.from_gemini(model, resp.usage_metadata)
    resp = call_with_fallback(clients.oai().responses.parse, model=model, instructions=instructions, input=inp,
                              text_format=schema, **model_options(model, effort))
    return resp.output_parsed, Usage.from_response(model, resp.usage)


def ping(clients: Clients, model: str, prompt: str, inp=None, effort: str | None = "low") -> tuple[str, Usage]:
    """One plain, non-streamed answer (used by the model check page)."""
    inp = inp if inp is not None else prompt
    if is_gemini(model):
        resp = gemini_generate(clients, model, to_gemini_contents(inp),
                               _gemini_config("You are a helpful assistant.", effort))
        return resp.text or "", Usage.from_gemini(model, resp.usage_metadata)
    resp = call_with_fallback(clients.oai().responses.create, model=model, input=inp, **model_options(model, effort))
    return resp.output_text, Usage.from_response(model, resp.usage)


# ---------- slow agent: planner ----------

def build_plan(client: Clients, model: str, pdf_bytes: bytes, filename: str,
               effort: str = "medium") -> tuple[LessonPlan, Usage]:
    cache = PLAN_CACHE / f"{pdf_hash(pdf_bytes)}_{model}_v2.json"
    if cache.exists():
        return LessonPlan.model_validate_json(cache.read_text()), Usage(model)
    plan, usage = parse(
        client, model, load_prompt("planner"),
        [{"role": "user", "content": [
            pdf_part(pdf_bytes, filename),
            {"type": "input_text", "text": "Topics to cover, in this order:\n" + "\n".join(TOPICS)},
        ]}],
        LessonPlan, effort,
    )
    PLAN_CACHE.mkdir(exist_ok=True)
    cache.write_text(plan.model_dump_json(indent=2))
    return plan, usage


# ---------- conversation formatting ----------

def describe_activity(activity: dict | None) -> str:
    if not activity:
        return ""
    if activity["type"] == "quick_check":
        opts = " ".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(activity["options"]))
        return (f"[I showed a quick-check card: {activity['question']} {opts} "
                f"(correct: {chr(65 + activity['correct_index'])})]")
    if activity["type"] == "visual":
        return f"[I showed a chart: {CHARTS.get(activity['chart'], activity['chart'])}]"
    return ""


def history_to_input(history: list[dict]) -> list[dict]:
    items = []
    for m in history:
        text = m["content"]
        extra = describe_activity(m.get("activity"))
        if extra:
            text = f"{text}\n\n{extra}" if text else extra
        items.append({"role": m["role"], "content": text or "(no text)"})
    return items


def transcript(history: list[dict], tutor="TUTOR", learner="PARTICIPANT") -> str:
    lines = []
    for m in history_to_input(history):
        who = tutor if m["role"] == "assistant" else learner
        lines.append(f"{who}: {m['content']}")
    return "\n\n".join(lines)


# ---------- fast agent: learner tracker ----------

def update_learner_state(client: Clients, model: str, plan: LessonPlan | None,
                         state: LearnerState, last_tutor: str, learner_msg: str,
                         card_note: str | None = None, effort: str = "low") -> tuple[LearnerState, Usage]:
    plan_text = plan.model_dump_json(exclude={"charts"}) if plan else json.dumps({"topics": TOPICS})
    payload = (
        f"LESSON PLAN:\n{plan_text}\n\n"
        f"PREVIOUS LEARNER NOTES:\n{state.model_dump_json()}\n\n"
        f"TUTOR'S LAST MESSAGE:\n{last_tutor or '(none)'}\n\n"
        f"PARTICIPANT'S REPLY:\n{learner_msg}"
    )
    if card_note:
        payload += f"\n\nQUICK-CHECK RESULT (computed by the app, reliable):\n{card_note}"
    return parse(client, model, load_prompt("tracker"), payload, LearnerState, effort)


# ---------- dialogue agent: friendly tutor ----------

def tutor_tools(plan: LessonPlan | None, cards: bool, visuals: bool) -> list[dict]:
    tools = []
    if cards:
        tools.append({
            "type": "function",
            "name": "quick_check",
            "description": (
                "Show the participant an interactive multiple-choice card to check understanding of something "
                "you have ALREADY explained. Use it occasionally to vary the rhythm (not every turn). When you use "
                "it, the card is your one question for this message: your text should just lead into it "
                "(e.g. 'Quick one 👇') and must not ask another question. They get two tries."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Short, friendly, applied question."},
                    "options": {"type": "array", "items": {"type": "string"},
                                "description": "3 short options, exactly one correct."},
                    "correct_index": {"type": "integer", "description": "0-based index of the correct option."},
                },
                "required": ["question", "options", "correct_index"],
                "additionalProperties": False,
            },
        })
    charts = plan.available_charts() if plan else []
    if visuals and charts:
        tools.append({
            "type": "function",
            "name": "show_visual",
            "description": (
                "Show a small chart built from the factsheet's own numbers inside your message, when seeing it "
                "would make the idea click (e.g. while explaining sector allocation or returns vs benchmark). "
                "Refer to it naturally in your text ('Have a look at this 👇'). At most one per message."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"chart": {"type": "string", "enum": charts}},
                "required": ["chart"],
                "additionalProperties": False,
            },
        })
    return tools


def build_tutor_input(pdf: dict | None, plan: LessonPlan | None, history: list[dict],
                      state: LearnerState | None, card_note: str | None = None) -> list[dict]:
    """Static context first (PDF + plan) so OpenAI's automatic prompt caching hits;
    the per-turn notes go last."""
    context: list[dict] = []
    if pdf:
        context.append(pdf)
    context.append({"type": "input_text", "text": "This is the factsheet we are going through together."})
    items: list[dict] = [{"role": "user", "content": context}]
    if plan:
        items.append({"role": "developer", "content": "LESSON PLAN (private):\n" + plan.model_dump_json()})
    if not history:
        items.append({"role": "developer", "content": "The participant has just opened the chat. Send your first message now."})
    items.extend(history_to_input(history))
    notes = []
    if state and history:
        notes.append("LEARNER NOTES (private):\n" + state.model_dump_json())
    if card_note:
        notes.append("QUICK-CHECK RESULT (computed by the app, reliable):\n" + card_note)
    if notes:
        items.append({"role": "developer", "content": "\n\n".join(notes)})
    return items


TOOL_ACK = {
    "quick_check": "The card is now shown below your message; the participant will answer on the card. "
                   "Write one short friendly lead-in line for it. Do not ask any other question.",
    "show_visual": "The chart is now shown in your message. Point out what "
                   "it shows using the factsheet's numbers, in one or two short texty bubbles, then ask one question in its own bubble.",
}


def _run_stream(stream, model: str, calls: list, meta: dict) -> Iterator[tuple[str, object]]:
    for event in stream:
        if event.type == "response.output_text.delta":
            meta["text"] = True
            yield "delta", event.delta
        elif event.type == "response.output_item.done" and getattr(event.item, "type", "") == "function_call":
            try:
                args = json.loads(event.item.arguments or "{}")
            except json.JSONDecodeError:
                continue
            calls.append((event.item.name, args, event.item.call_id))
            yield "tool", (event.item.name, args)
        elif event.type == "response.completed":
            meta["id"] = event.response.id
            meta["usage"] = Usage.from_response(model, event.response.usage)
        elif event.type in ("response.failed", "error"):
            err = getattr(getattr(event, "response", None), "error", None) or getattr(event, "message", "")
            raise RuntimeError(f"Model error: {err}")


def stream_tutor(client: Clients, model: str, system_prompt: str, tutor_input: list[dict],
                 tools: list[dict], effort: str | None = "low") -> Iterator[tuple[str, object]]:
    """Yields ("delta", text), ("tool", (name, args)) and finally ("done", Usage).

    If the model calls a tool without writing any text, we acknowledge the call and let
    it continue (tools off) so a card or chart always comes with a friendly line."""
    if is_gemini(model):
        yield from _stream_tutor_gemini(client, model, system_prompt, tutor_input, tools, effort)
        return
    oai = client.oai()
    opts = model_options(model, effort, verbosity="low")
    kwargs = dict(model=model, instructions=system_prompt, input=tutor_input, stream=True, **opts)
    if tools:
        kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
    calls: list = []
    meta: dict = {"text": False}
    yield from _run_stream(call_with_fallback(oai.responses.create, **kwargs), model, calls, meta)
    total = meta.get("usage") or Usage(model)

    if calls and not meta["text"] and meta.get("id"):
        outputs = [{"type": "function_call_output", "call_id": cid, "output": TOOL_ACK.get(name, "Done.")}
                   for name, _, cid in calls]
        meta2: dict = {"text": False}
        follow = call_with_fallback(
            oai.responses.create, model=model, instructions=system_prompt, previous_response_id=meta["id"],
            input=outputs, tools=tools, tool_choice="none", stream=True, **opts,
        )
        for kind, val in _run_stream(follow, model, [], meta2):
            if kind == "delta":
                yield kind, val
        u2 = meta2.get("usage")
        if u2:
            total = total + u2
    yield "done", total


def _run_gemini_stream(stream, model: str, calls: list, parts: list, meta: dict) -> Iterator[tuple[str, object]]:
    for chunk in stream:
        if chunk.usage_metadata:
            meta["usage"] = Usage.from_gemini(model, chunk.usage_metadata)
        cand = chunk.candidates[0] if chunk.candidates else None
        if not cand or not cand.content or not cand.content.parts:
            continue
        for p in cand.content.parts:
            parts.append(p)  # kept whole (thought signatures included) for the follow-up turn
            if p.function_call:
                args = dict(p.function_call.args or {})
                calls.append((p.function_call.name, args))
                yield "tool", (p.function_call.name, args)
            elif p.text and not p.thought:
                meta["text"] = True
                yield "delta", p.text


def _stream_tutor_gemini(client: Clients, model: str, system_prompt: str, tutor_input: list[dict],
                         tools: list[dict], effort: str | None) -> Iterator[tuple[str, object]]:
    contents = to_gemini_contents(tutor_input)
    cfg = _gemini_config(system_prompt, effort)
    if tools:
        cfg["tools"] = [gtypes.Tool(function_declarations=[
            gtypes.FunctionDeclaration(name=t["name"], description=t["description"],
                                       parameters_json_schema=t["parameters"]) for t in tools])]
        cfg["automatic_function_calling"] = gtypes.AutomaticFunctionCallingConfig(disable=True)
    calls: list = []
    parts: list = []
    meta: dict = {"text": False}
    yield from _run_gemini_stream(gemini_stream(client, model, contents, cfg), model, calls, parts, meta)
    total = meta.get("usage") or Usage(model)

    if calls and not meta["text"]:
        follow = contents + [
            gtypes.Content(role="model", parts=parts),
            gtypes.Content(role="user", parts=[
                gtypes.Part.from_function_response(name=name, response={"result": TOOL_ACK.get(name, "Done.")})
                for name, _ in calls]),
        ]
        cfg2 = {**cfg, "tool_config": gtypes.ToolConfig(
            function_calling_config=gtypes.FunctionCallingConfig(mode="NONE"))}
        meta2: dict = {"text": False}
        for kind, val in _run_gemini_stream(gemini_stream(client, model, follow, cfg2), model, [], [], meta2):
            if kind == "delta":
                yield kind, val
        if meta2.get("usage"):
            total = total + meta2["usage"]
    yield "done", total


def tool_to_activity(name: str, args: dict, plan: LessonPlan | None) -> dict | None:
    if name == "quick_check":
        opts = [str(o) for o in args.get("options", [])][:4]
        try:
            idx = int(args.get("correct_index", -1))  # Gemini sends JSON numbers as floats
        except (TypeError, ValueError):
            return None
        if len(opts) < 2 or not (0 <= idx < len(opts)):
            return None
        return {"type": "quick_check", "question": args.get("question", ""), "options": opts,
                "correct_index": idx, "attempts": [], "closed": False}
    if name == "show_visual" and plan and args.get("chart") in plan.available_charts():
        return {"type": "visual", "chart": args["chart"]}
    return None


# ---------- simulated learner (AMIE-style self-play) ----------

PERSONAS = {
    "Priya — nervous first-timer": (
        "You are Priya, 24, in your first job in Pune. You have never invested; your money sits in a savings "
        "account. You're a bit anxious about losing money and worry you'll look silly. You reply briefly, "
        "sometimes say 'not sure' or 'I don't know', and occasionally ask what a word means."
    ),
    "Rahul — overconfident": (
        "You are Rahul, 35, IT professional in Bengaluru with FDs and some stock tips from colleagues. You're "
        "confident and answer quickly, but you believe past returns are basically guaranteed, mix up NAV with a "
        "share price, and think the benchmark is a minimum return the fund promises. You sometimes ask "
        "'so should I invest in this or not?'"
    ),
    "Meena — careful & practical": (
        "You are Meena, 52, a school administrator in Chennai who saves carefully. You care about practical "
        "things: how much you need to start, what happens if you take money out early, and tax. You prefer "
        "very simple language and ask the tutor to repeat things more simply when there's jargon."
    ),
}


class SimReply(BaseModel):
    message: str
    card_choice: int | None


def simulate_learner(client: Clients, model: str, persona: str, history: list[dict],
                     open_card: dict | None, turns_left: int) -> tuple[SimReply, Usage]:
    payload = f"YOUR PERSONA:\n{persona}\n\nCONVERSATION SO FAR:\n{transcript(history, 'TUTOR', 'YOU')}"
    if open_card:
        opts = " ".join(f"{i}) {o}" for i, o in enumerate(open_card["options"]))
        payload += f"\n\nA quick-check card is open: {open_card['question']} Options: {opts}"
    if turns_left <= 1:
        payload += "\n\nThis is your last message: wrap up and say you're done for today."
    return parse(client, model, load_prompt("learner_sim"), payload, SimReply, "low")


# ---------- grader (LearnLM pedagogy rubric + study protocol) ----------

RUBRIC = {
    "Cognitive load": [
        ("Appropriate length", "The tutor's responses are an appropriate length for the student."),
        ("Manageable chunks", "The tutor breaks information down into smaller, manageable chunks."),
        ("Straightforward", "The tutor's responses are clear and easy to follow."),
        ("No irrelevant info", "The tutor avoids irrelevant information."),
        ("Analogies", "The tutor's use of narratives, case studies, or analogies effectively illustrates key concepts."),
        ("Info presentation", "The tutor presents information in an appropriate style and structure."),
        ("Info order", "The tutor develops explanations in a logical order, building on previous concepts."),
        ("No repetition", "The tutor avoids repeating information unnecessarily."),
        ("No contradiction", "The tutor avoids contradicting information from earlier parts of the conversation."),
    ],
    "Active learning": [
        ("Openings for engagement", "The tutor provides opportunities for engagement from the student."),
        ("Asks questions", "The tutor asks questions to encourage the student to think."),
        ("Guides to answer", "The tutor does not give away answers too quickly."),
        ("Active engagement", "The tutor promotes active engagement with the material."),
    ],
    "Metacognition": [
        ("Guides mistake discovery", "The tutor guides the student to discover their own mistakes."),
        ("Constructive feedback", "The tutor provides clear, constructive feedback (whether positive or negative) to the student."),
        ("Acknowledges correctness", "The tutor acknowledges when part or all of the student's response is correct."),
        ("Communicates plan", "The tutor communicates a clear plan or objective for the conversation."),
    ],
    "Curiosity": [
        ("Stimulates interest", "The tutor tries to stimulate the student's interest and curiosity."),
        ("Adapts to affect", "The tutor responds effectively if the student becomes frustrated or discouraged."),
        ("Encouraging feedback", "The tutor delivers feedback (whether positive or negative) in an encouraging way."),
    ],
    "Adaptivity": [
        ("Leveling", "The tutor's explanations are appropriate for the level of the student."),
        ("Unstuck", "The tutor effectively adapts its approach to help the student when they are stuck."),
        ("Adapts to needs", "Overall, the tutor adapts to the student's needs."),
        ("Proactive", "The tutor proactively guides the conversation when appropriate."),
        ("Guides appropriately", "The tutor does not withhold information unproductively."),
    ],
    "Overall": [
        ("No inaccuracies", "There are no inaccuracies in the statements made by the tutor, checked against the factsheet."),
        ("Expresses uncertainty", "The tutor expresses uncertainty when appropriate."),
        ("No refusals", "The tutor does not refuse to answer any reasonable questions from the student."),
        ("Overall quality", "The tutor is as good as a very good human tutor."),
    ],
    "Study protocol": [
        ("One question per turn", "Every tutor message asks at most one main question and stops after asking it."),
        ("Explains before testing", "The tutor never tests something before explaining it."),
        ("Factsheet only", "The tutor uses only the factsheet; no invented figures or outside facts."),
        ("No advice", "The tutor never recommends buying, selling or holding, never judges personal suitability, and never predicts returns."),
        ("Friendly tone", "The tutor sounds like a warm, patient friend rather than a textbook or customer support."),
    ],
}


class ItemScore(BaseModel):
    item: str
    score: int | None
    evidence: str


class Grade(BaseModel):
    items: list[ItemScore]
    inaccuracies: list[str]
    strengths: str
    improvements: str


def grade_conversation(client: Clients, model: str, pdf_bytes: bytes, filename: str,
                       history: list[dict], effort: str = "medium") -> tuple[Grade, Usage]:
    rubric_text = "\n".join(f"- [{cat}] {name}: {q}" for cat, items in RUBRIC.items() for name, q in items)
    return parse(
        client, model, load_prompt("grader").replace("{rubric}", rubric_text),
        [{"role": "user", "content": [
            pdf_part(pdf_bytes, filename),
            {"type": "input_text", "text": "TRANSCRIPT:\n\n" + transcript(history)},
        ]}],
        Grade, effort,
    )


def category_means(grade: Grade) -> dict[str, float | None]:
    by_name = {s.item: s.score for s in grade.items}
    out = {}
    for cat, items in RUBRIC.items():
        vals = [by_name.get(name) for name, _ in items]
        vals = [v for v in vals if v is not None]
        out[cat] = round(sum(vals) / len(vals), 2) if vals else None
    return out


# ---------- study conditions 1 & 2: FAQ answers and plain chat ----------

def fund_name_from_pdf(pdf_bytes: bytes) -> str:
    """First line of the factsheet, e.g. 'KOTAK LARGE CAP FUND' -> 'Kotak Large Cap Fund'."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_bytes)
    first = doc[0].get_textpage().get_text_range().strip().splitlines()[0]
    return " ".join(w.capitalize() if w.isupper() else w for w in first.split())


def stream_text(client: Clients, model: str, instructions: str, inp, effort: str | None = "low"
                ) -> Iterator[tuple[str, object]]:
    """Plain streamed answer: yields ("delta", text) then ("done", Usage)."""
    yield from stream_tutor(client, model, instructions, inp, [], effort)


def faq_cache_path(pdf_bytes: bytes, model: str) -> Path:
    return PLAN_CACHE / f"faq_{pdf_hash(pdf_bytes)}_{model}.json"


def load_faq_cache(pdf_bytes: bytes, model: str) -> dict:
    p = faq_cache_path(pdf_bytes, model)
    return json.loads(p.read_text()) if p.exists() else {}


def save_faq_answer(pdf_bytes: bytes, model: str, question: str, answer: str):
    cache = load_faq_cache(pdf_bytes, model)
    cache[question] = answer
    PLAN_CACHE.mkdir(exist_ok=True)
    faq_cache_path(pdf_bytes, model).write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def faq_input(pdf: dict, question: str) -> list[dict]:
    return [{"role": "user", "content": [pdf, {"type": "input_text", "text": f"FAQ question: {question}"}]}]

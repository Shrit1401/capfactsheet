# capfactsheet — Factsheet Tutor Arena

A Streamlit workbench for AI tutors that teach a mutual-fund factsheet, running on **OpenAI and Google Gemini**
models side by side (GPT-6 Astra/Sol/Luna, GPT-5.x, GPT-4.1, Gemini 4 Argon, Gemini 3.x Pro/Flash).

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```
Paste your **OpenAI** and/or **Gemini** API key in the sidebar (🔑 API keys). Or put them in
`.streamlit/secrets.toml` (see `secrets.toml.example`), or set `OPENAI_API_KEY` / `GEMINI_API_KEY`.
Model pickers only list models your keys unlock. You can also type any other model id.

## Pages
- **Study**: a factsheet viewer plus one of three study conditions (guided questions, hybrid FAQ, tutor)
- **Tutor Arena**: up to 3 tutor models side by side, with a planner, learner tracker, quick-check cards,
  charts, a simulated learner, and a LearnLM-rubric grader
- **Model check**: one prompt (optionally with the factsheet PDF) sent to many models at once, with replies,
  latency, tokens and cost
- **How we built it**: design notes and live charts

## Files
- `app.py`: navigation and API keys · `keys.py`: key handling · `model_check.py`: model check page
- `tutor_engine.py`: one `Clients` object routes `gemini-*` models to the Gemini API (google-genai) and others to
  the OpenAI Responses API. Also holds the planner, tracker, streaming tutor and tools, simulated learner, and
  grader. `PRICES` holds the model list and approximate prices.
- `arena.py`, `study.py`, `about.py`, `charts.py`, `ui.py`, `study_config.py`
- `prompts/` · `factsheets/` · `plans/` (local cache, not committed)

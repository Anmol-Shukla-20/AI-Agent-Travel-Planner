# Agentic AI Trip Planner

**Agentic AI Trip Planner — an experimental agent-driven travel planning toolkit**

Overview
--------
This repository contains a small agentic system for planning trips using modular tools (place search, weather, currency conversion, expense estimation). It provides:

- A Streamlit UI (`streamlit_app.py`) for interactive planning and demoing the agent.
- A lightweight programmatic interface in `main.py` and the `agent/` package for building agent workflows.
- Reusable tools under `tools/` and helpers under `utils/`.

Key Features
------------

- Multi-tool agent workflow for trip generation and budgeting
- Streamlit demo to interactively build an itinerary
- Modular tools: place search, weather lookups, currency conversion, expense calculation
- Clear separation between agent logic (`agent/`) and utility functions (`utils/`, `tools/`)

Quick Start (Windows)
----------------------

1. Create and activate a virtual environment (example using Python 3.10+):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the uvicorn app locally:

```powershell
uvicorn main:app --reload --port 8000
```

4. Run the Streamlit app for testing the Agent (browser UI):

```powershell
streamlit run streamlit_app.py
```


Project Structure
-----------------

- `main.py` — optional API entrypoint / programmatic runner
- `streamlit_app.py` — Streamlit demo UI
- `agent/` — core agent workflows (e.g., `agentic_workflow.py`)
- `tools/` — small tool modules (place search, weather, currency, expense)
- `utils/` — helper utilities (config loader, model loader, save helpers)
- `config/` — configuration and `config.yaml`
- `logger/`, `exception/` — logging and error handling helpers

How the project works (high level)
---------------------------------

1. The agent orchestrates a sequence of tool calls depending on user input or a planning prompt.
2. Tools are small, focused functions that retrieve or compute data (e.g., search places, fetch weather, convert currency).
3. The agent composes tool outputs into a plan (itinerary, budget, recommendations) and returns results to the UI or API caller.
4. The Streamlit app demonstrates how a user can provide preferences and receive an agentic itinerary.


Contact & License
-----------------

If you need help, open an issue then contact the project owner. This project is licensed under the MIT License — see the `LICENSE` file for details and the full text.

---

© 2026 All Rights Reserved by Anmol Shukla.

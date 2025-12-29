# Prototype

This folder is a clean-slate workspace for a negotiation prototype.


When the prototype stabilizes, we can promote pieces into `src/` or a dedicated
package.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

Open `http://localhost:8000/ui` in a browser.

The backend auto-loads `prototype/.env` on startup (via python-dotenv).

## LLM (OpenRouter)

Set these environment variables to enable LLM-backed agents:

```bash
export NEGOT_ENABLE_LLM=true
export OPENROUTER_API_KEY=your_key
export OPENROUTER_MODEL=openai/gpt-4o-mini
```

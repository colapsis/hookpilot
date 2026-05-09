"""
AI-powered webhook analysis via LiteLLM.

Supports any provider LiteLLM understands — set AI_MODEL in .env and
the corresponding provider API key. Examples:

  OpenAI:     AI_MODEL=gpt-4o-mini          + OPENAI_API_KEY
  Anthropic:  AI_MODEL=claude-haiku-3-5-20251001 + ANTHROPIC_API_KEY
  Gemini:     AI_MODEL=gemini/gemini-2.0-flash   + GEMINI_API_KEY
  Groq:       AI_MODEL=groq/llama-3.1-8b-instant + GROQ_API_KEY
  Mistral:    AI_MODEL=mistral/mistral-small-latest + MISTRAL_API_KEY
  Ollama:     AI_MODEL=ollama/llama3         (no key — runs locally)
  Azure:      AI_MODEL=azure/gpt-4o          + AZURE_API_KEY + AZURE_API_BASE
"""
import json
import re
from app.config import AI_MODEL


def ai_enabled() -> bool:
    return bool(AI_MODEL)


def _extract_json(text: str) -> str:
    """Strip markdown fences and return raw JSON."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        return match.group(1).strip()
    return text


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:\w+)?\s*([\s\S]+?)```", text)
    if match:
        return match.group(1).strip()
    return text


async def analyze_webhook(
    method: str,
    path: str,
    headers: dict,
    body: str,
    content_type: str,
) -> dict:
    """
    Return a structured analysis of the webhook:
      summary, source, event_type, key_fields
    """
    if not ai_enabled():
        return {"error": "AI not configured — set AI_MODEL in .env"}

    from litellm import acompletion

    # Keep prompts within token budget
    body_preview = body[:3000] if len(body) > 3000 else body
    header_preview = dict(list(headers.items())[:12])

    prompt = f"""You are a webhook payload analyzer. Analyze this HTTP request and respond with JSON ONLY — no explanation, no markdown, just raw JSON.

Method: {method}
Path: {path}
Content-Type: {content_type or "unknown"}
Headers (sample): {json.dumps(header_preview)}
Body:
{body_preview}

Respond with exactly this structure:
{{
  "summary": "One-sentence plain English description of what happened (e.g. 'Stripe payment of $99.00 succeeded for customer john@example.com')",
  "source": "Service that sent this (e.g. Stripe, GitHub, Shopify, Twilio, or Unknown)",
  "event_type": "Event type string if identifiable (e.g. payment.succeeded) or null",
  "key_fields": [
    {{"name": "human-readable field name", "value": "its value as string"}}
  ]
}}

key_fields: pick the 4–6 most important/interesting fields. Flatten nested paths if helpful (e.g. 'customer.email' rather than the full nested object)."""

    try:
        resp = await acompletion(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or ""
        return json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {"error": "AI returned non-JSON response", "raw": raw[:300]}
    except Exception as exc:
        return {"error": str(exc)}


_LANG_HINTS = {
    "python":     "Python 3.10+, FastAPI or Flask style, use type hints and dataclasses/TypedDict",
    "javascript": "Node.js with async/await, Express-style handler, modern ES2022",
    "typescript": "TypeScript with strict types, define interfaces for the payload",
    "go":         "Go with struct definitions and proper error handling",
    "php":        "PHP 8.1+ with type hints and named arguments",
    "ruby":       "Ruby 3 / Rails style",
    "java":       "Java 17 with records and Jackson annotations",
    "csharp":     "C# with records and System.Text.Json",
}


async def generate_handler(
    method: str,
    path: str,
    body: str,
    language: str,
) -> str:
    """Return idiomatic handler code for the given language."""
    if not ai_enabled():
        return "# AI not configured — set AI_MODEL in .env"

    from litellm import acompletion

    body_preview = body[:3000] if len(body) > 3000 else body
    hint = _LANG_HINTS.get(language.lower(), language)

    prompt = f"""Generate a webhook handler in {language} for this HTTP request payload.

Method: {method}
Path: {path}
Payload:
{body_preview}

Requirements:
- {hint}
- Define a type / struct / interface for the payload where idiomatic
- Extract and use the most important fields by name
- Add a one-line comment explaining what the webhook represents
- Leave a clear TODO where the developer adds their business logic
- Keep it concise and production-ready

Return ONLY the code. No introduction, no explanation, no markdown fences."""

    try:
        resp = await acompletion(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.2,
        )
        code = resp.choices[0].message.content or ""
        return _strip_code_fences(code)
    except Exception as exc:
        return f"# Error generating handler: {exc}"

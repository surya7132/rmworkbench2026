"""Optional AI help. Off unless ANTHROPIC_API_KEY is set. Nothing else in the tool depends on it.

Two uses, both on the meeting screen:
  tidy(notes)     turn rough dictated notes into clean, short notes (no new facts)
  rewrite(points) turn the rule-based talking points into a short written brief (only those facts)
Uses the standard library only, so there is nothing extra to install.
"""
import json
import os
import urllib.request

MODEL = os.environ.get("COMPASS_AI_MODEL", "claude-sonnet-5-5")
URL = "https://api.anthropic.com/v1/messages"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _call(system, user):
    body = json.dumps({"model": MODEL, "max_tokens": 700, "system": system, "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def tidy(notes):
    return _call("You tidy a relationship manager's rough meeting notes for a bank. Fix spelling and punctuation, split into short sentences, keep every fact and number exactly as given. "
                 "Never add facts, names or numbers that are not in the notes. Return plain text only.", notes)


def rewrite(points_text):
    return _call("You write a five-line meeting brief for a bank relationship manager from the facts given. Use only those facts. Keep numbers exact. Plain text, no headings.", points_text)

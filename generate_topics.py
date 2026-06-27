#!/usr/bin/env python3
"""Doplni banku tem cez GitHub Models (zadarmo). Nika: MOTIVACIA / disciplina / stoicizmus."""
import json
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

SYSTEM = ("You are a scriptwriter for a motivation & self-discipline brand whose MISSION is to genuinely "
          "HELP and inspire people to build a better life. You craft powerful short scripts around REAL, "
          "well-known quotes from famous people (philosophers, athletes, founders, leaders) - always "
          "CORRECTLY attributed - and short TRUE stories of real people who overcame real hardship. "
          "ACCURACY IS SACRED: only use a quote or story if you are confident it is GENUINE and correctly "
          "attributed. NEVER invent a quote, NEVER misattribute, NEVER fabricate facts or statistics. "
          "If you are not certain a quote is real, deliver the wisdom in your own words WITHOUT attribution. "
          "You output strict JSON, nothing else.")

EXAMPLE = {
    "title": "What Marcus Aurelius Knew About Discipline",
    "segments": [
        {"text": "\"You have power over your mind, not outside events. Realize this, and you will find strength.\"", "keywords": "ancient roman statue marble"},
        {"text": "Marcus Aurelius wrote that almost 2000 years ago, and it still hits today.", "keywords": "old book candlelight"},
        {"text": "Most of your stress comes from things you cannot control.", "keywords": "man stressed window rain"},
        {"text": "Discipline is mastering the one thing you can: your own response.", "keywords": "man meditating calm"},
        {"text": "Every time you act instead of react, you grow stronger.", "keywords": "person training gym focused"},
        {"text": "So master your mind, and the world loses its grip on you.", "keywords": "man standing mountain sunrise"},
        {"text": "Follow for your daily dose of discipline.", "keywords": "lone figure city"},
    ],
    "description": "Marcus Aurelius said you have power over your mind, not outside events. Follow for daily discipline!",
    "hashtags": ["#motivation", "#discipline", "#stoicism", "#marcusaurelius", "#mindset", "#shorts", "#fyp", "#selfimprovement"],
}


def build_prompt(n, existing_titles):
    return (
        f"Generate {n} NEW faceless short-form video topics for a MOTIVATION & SELF-DISCIPLINE brand "
        "(TikTok / Reels / YouTube Shorts) whose mission is to genuinely HELP people improve their lives.\n"
        "Return ONLY a JSON array (no markdown). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "VARY the format across the batch - roughly a third of each:\n"
        "  (A) QUOTE VIDEO: built around ONE real, famous, correctly-attributed quote (e.g. Marcus Aurelius, "
        "Seneca, Epictetus, David Goggins, Kobe Bryant, Jocko Willink, Theodore Roosevelt, Bruce Lee). "
        "The hook is the quote itself; then unpack what it really means and how to live it.\n"
        "  (B) STORY VIDEO: a SHORT TRUE story of a real, well-known person who overcame real hardship "
        "(e.g. how a famous athlete/founder failed before they succeeded). State only widely-documented facts.\n"
        "  (C) WISDOM VIDEO: hard-hitting, actionable self-discipline advice in YOUR OWN words (no attribution).\n"
        "ACCURACY IS SACRED: only use a quote or story if you are CONFIDENT it is genuine and correctly "
        "attributed. If unsure, fall back to format (C) and write it as your own wisdom. NEVER invent or "
        "misattribute a quote, NEVER fabricate statistics.\n\n"
        "Rules (make it feel PRO, VIRAL and genuinely HELPFUL):\n"
        "- title: punchy and curiosity-driven, e.g. 'What Marcus Aurelius Knew About Discipline', "
        "'The Mindset That Built David Goggins', 'Why Discipline Beats Motivation'.\n"
        "- 6 to 9 segments. Segment 1 is THE HOOK: under 14 words, stops the scroll (the quote, or the most "
        "gripping line of the story). Never start with 'Did you know'.\n"
        "- segment 2 keeps them watching. Build intensity line by line; write for a deep, powerful SPOKEN "
        "voiceover: short, punchy sentences. End on an empowering, useful takeaway people can apply today.\n"
        "- empowering, never hateful, demeaning or toxic.\n"
        "- each segment 'keywords': 1-3 ENGLISH words for real Pexels footage that VISUALLY MATCHES the line "
        "(e.g. 'ancient roman statue', 'boxer training gym', 'sunrise mountain', 'man walking rain'). "
        "Cinematic and concrete, never abstract.\n"
        "- the SECOND-TO-LAST segment should loop back to the opening hook/quote so a rewatch feels seamless.\n"
        "- the LAST segment text MUST be exactly: 'Follow for your daily dose of discipline.'\n"
        "- description: one punchy sentence ending with 'Follow for daily discipline!'.\n"
        "- About half the time, add ONE fitting emoji at the very END of the description (e.g. 🔥, 💪, 🧠, ⚡). "
        "Emoji ONLY in the description text, NEVER inside any segment 'text' (spoken captions).\n"
        "- hashtags: 6-8 tags including #motivation #discipline #shorts #fyp.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "Return ONLY the JSON array."
    )


def call_model(user_text):
    r = requests.post(
        BASE.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.95,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user_text}]},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Models API {r.status_code}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def extract_json(s):
    s = s.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    a, b = s.find("["), s.rfind("]")
    if a != -1 and b != -1:
        s = s[a:b + 1]
    return json.loads(s)


def valid(t):
    if not isinstance(t, dict) or "title" not in t or "segments" not in t:
        return False
    if not isinstance(t["segments"], list) or len(t["segments"]) < 4:
        return False
    for seg in t["segments"]:
        if "text" not in seg or "keywords" not in seg:
            return False
    t.setdefault("description", t["title"] + " Follow for daily discipline!")
    t.setdefault("hashtags", ["#motivation", "#discipline", "#shorts", "#fyp"])
    return True


def main():
    if not TOKEN:
        print("CHYBA: chyba MODELS_TOKEN/GITHUB_TOKEN"); sys.exit(1)
    bank = json.load(open(BANK, encoding="utf-8"))
    used = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else []
    titles = {t["title"] for t in bank}
    unused = [t for t in bank if t["title"] not in used]
    need = TARGET - len(unused)
    if need <= 0:
        print(f"Banka OK: {len(unused)} nepouzitych tem."); return
    print(f"Generujem ~{need} novych tem cez {MODEL}...")
    items = extract_json(call_model(build_prompt(need + 3, sorted(titles))))
    added = 0
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        bank.append(t); titles.add(t["title"]); added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} tem. Banka ma {len(bank)} tem.")


if __name__ == "__main__":
    main()

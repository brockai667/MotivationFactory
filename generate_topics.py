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

SYSTEM = ("You are a viral short-form scriptwriter for a motivation & discipline (stoic mindset) brand. "
          "You write hard-hitting, universal wisdom in your own words. No fake quotes attributed to real "
          "people, no invented statistics. You output strict JSON, nothing else.")

EXAMPLE = {
    "title": "3 Hard Truths You Need to Hear",
    "segments": [
        {"text": "No one is coming to save you. That is the truth.", "keywords": "lone man city night"},
        {"text": "And once you accept it, everything changes.", "keywords": "man walking rain"},
        {"text": "Discipline beats motivation, because motivation always fades.", "keywords": "person gym training"},
        {"text": "You don't rise to your goals, you fall to your habits.", "keywords": "stairs climbing"},
        {"text": "Comfort is the enemy that smiles at you.", "keywords": "man thinking window"},
        {"text": "So the only person to beat is who you were yesterday.", "keywords": "sunrise mountain"},
        {"text": "Follow for your daily dose of discipline.", "keywords": "lone figure city"},
    ],
    "description": "No one is coming to save you — discipline is everything. Follow for daily discipline!",
    "hashtags": ["#motivation", "#discipline", "#stoicism", "#mindset", "#success", "#shorts", "#fyp", "#selfimprovement"],
}


def build_prompt(n, existing_titles):
    return (
        f"Generate {n} NEW faceless short-form video topics for a MOTIVATION & DISCIPLINE (stoic mindset) brand "
        "(TikTok / Reels / YouTube Shorts).\n"
        "Niche: hard truths, self-discipline, stoic mindset, beating laziness/comfort, building yourself.\n"
        "Return ONLY a JSON array (no markdown). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules (make it feel PRO and VIRAL):\n"
        "- title: punchy, like '3 Hard Truths You Need to Hear' or 'Why Discipline Beats Motivation'.\n"
        "- 6 to 9 segments. Segment 1 is THE HOOK: a hard-hitting truth under 12 words that stops the scroll. "
        "Never start with 'Did you know'.\n"
        "- segment 2 keeps them watching (e.g. 'And once you accept it, everything changes.').\n"
        "- build intensity line by line; write for a deep, powerful SPOKEN voiceover: short, punchy sentences.\n"
        "- universal wisdom only. NO fake quotes attributed to real people, NO invented statistics, "
        "nothing hateful or demeaning. Empowering, not toxic.\n"
        "- each segment 'keywords': 1-3 ENGLISH words for real Pexels footage that VISUALLY MATCHES the line "
        "(e.g. 'lone man city night', 'person gym training', 'sunrise mountain', 'man walking rain'). "
        "Cinematic and concrete, never abstract.\n"
        "- the SECOND-TO-LAST segment should loop back to the opening hook so a rewatch feels seamless.\n"
        "- the LAST segment text MUST be exactly: 'Follow for your daily dose of discipline.'\n"
        "- description: one punchy sentence ending with 'Follow for daily discipline!'.\n"
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

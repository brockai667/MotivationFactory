# BrainHeist (ex-MotivationFactory / DisciplineDaily)

Solve the riddle. Steal the million. 3D-cartoon riddle explainery:
cena + smrtelna hadanka s presnou matematikou + genialne riesenie.

## Architektura
- **Vyroba**: lokalny RiddleFactory builder (C:\Users\damia\RiddleFactory —
  STYLE.md formula, Gemini Nano Banana keyframy, kokoro VO, PIL/ffmpeg engine).
  Denna scheduled uloha vyrobi video + .txt metadata a pushne do `output/`.
- **Publikacia**: tento repo — workflow "BrainHeist Publish" (cron 11:00 UTC +
  push-trigger na output/*.mp4) posle videa cez Buffer na YT + IG + TikTok.
- `output/<nazov>.txt`: 1. riadok = title, zvysok = caption s hashtagmi.

Stare motivacne generovanie (make_video/pro_engine/motion/generate_*) je
odstavene z cronu; subory ostavaju len ako archiv.

Hudba: Sneaky Snitch – Kevin MacLeod (incompetech.com), CC BY 4.0 — kredit
je automaticky v kazdom captione.

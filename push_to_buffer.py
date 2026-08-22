#!/usr/bin/env python3
"""
Auto-poster (beží aj bezo mňa, cez buffer_token): hotove videa z output/ -> Buffer fronta.

Tok:
  1) video MP4 -> Cloudinary (verejna HTTPS URL; Buffer API nezvlada upload suboru)
  2) Buffer createPost (mode customScheduled na presny cas 08:00/15:00/20:00) na vsetky kanaly
     s per-platform metadatami (IG reel, YT title+categoryId, TikTok title)
  3) pamata si odoslane videa v pushed.json (ziadne duplicity)

Pouzitie:
  python push_to_buffer.py            # posle 3 najstarsie nezaradene videa
  python push_to_buffer.py 3          # posle 3
  python push_to_buffer.py --dry-run  # iba overi token + kanaly, nic neposle
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import random
import sys
import time

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
BUFFER_API = "https://api.buffer.com"
PUSHED = os.path.join(ROOT, "pushed.json")
WANT_SERVICES = {"instagram", "tiktok", "youtube"}
YT_CATEGORY = "24"  # Entertainment (riddle/brain-teaser obsah)
SLOT_HOURS = [15, 20, 8]  # preferovane poradie slotov (Europe/Bratislava);
#   15:00 = 3 z 5 najuspesnejsich videi kanala, ostatne su zaloha pri dobiehani fronty
MIN_GAP_HOURS = int(os.environ.get("MIN_GAP_HOURS", "20"))  # min. odstup medzi dvoma postami
SCHEDULE_STATE = os.path.join(ROOT, "schedule_state.json")


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Bratislava")
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=2))


def _last_scheduled(tz):
    """Posledny UZ naplanovany cas (drzi sa medzi behmi v schedule_state.json)."""
    try:
        s = json.load(open(SCHEDULE_STATE, encoding="utf-8")).get("last_scheduled")
        if s:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz)
    except Exception:
        pass
    return None


def _save_scheduled(dt):
    try:
        with open(SCHEDULE_STATE, "w", encoding="utf-8") as f:
            json.dump({"last_scheduled": dt.astimezone(datetime.timezone.utc).isoformat()}, f)
    except Exception as e:
        print(f"  (pozor) stav planovania sa neulozil: {e}")


def next_slots(n):
    """n casov publikovania: KAZDE video do ineho slotu a min. MIN_GAP_HOURS od predosleho.
    Preco: ked dva shorts vyjdu par minut po sebe, YouTube pretlaci jeden a druhy vyhladuje
    (overene na kanali: 0-20 zhliadnuti vs 111-671 pri videach z rovnakeho slotu)."""
    tz = _tz()
    now = datetime.datetime.now(tz)
    last = _last_scheduled(tz)
    cursor = now if last is None else max(now, last + datetime.timedelta(hours=MIN_GAP_HOURS))
    out = []
    day = cursor.date()
    for _ in range(200):
        if len(out) >= n:
            break
        for h in SLOT_HOURS:
            t = datetime.datetime.combine(day, datetime.time(h), tzinfo=tz)
            t += datetime.timedelta(minutes=random.randint(2, 27), seconds=random.randint(0, 59))
            if t > cursor:
                out.append(t)
                cursor = t + datetime.timedelta(hours=MIN_GAP_HOURS)
                break
        day += datetime.timedelta(days=1)
    if out:
        _save_scheduled(out[-1])
    return [t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") for t in out]


def load_cfg():
    import appconfig
    return appconfig.load()


def gql(token, query, variables=None):
    r = requests.post(
        BUFFER_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )
    data = r.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def get_channels(token):
    q = """
    query { account { organizations { id channels { id name service } } } }"""
    data = gql(token, q)
    chans = []
    for org in data["account"]["organizations"]:
        chans.extend(org.get("channels", []))
    return chans


def upload_cloudinary(cfg, path):
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=cfg["cloudinary_cloud_name"],
        api_key=cfg["cloudinary_api_key"],
        api_secret=cfg["cloudinary_api_secret"],
        secure=True,
    )
    public_id = os.path.splitext(os.path.basename(path))[0]
    res = cloudinary.uploader.upload_large(
        path, resource_type="video", folder="facelessfactory",
        public_id=public_id, use_filename=True, unique_filename=False, overwrite=True,
    )
    return res["secure_url"]


def build_mutation(service):
    """Vrati (query, pouziva_title). Metadata su inline. Planuje na presny cas cez dueAt + customScheduled."""
    base = "$channelId: ChannelId!, $text: String!, $url: String!, $dueAt: DateTime!"
    if service == "instagram":
        meta = "metadata: { instagram: { type: reel, shouldShareToFeed: true } }"
        decl = base
        use_title = False
    elif service == "youtube":
        meta = f'metadata: {{ youtube: {{ title: $title, categoryId: "{YT_CATEGORY}", privacy: public }} }}'
        decl = base + ", $title: String!"
        use_title = True
    elif service == "tiktok":
        meta = "metadata: { tiktok: { title: $title } }"
        decl = base + ", $title: String!"
        use_title = True
    else:
        meta = ""
        decl = base
        use_title = False
    q = f"""
    mutation({decl}) {{
      createPost(input: {{
        channelId: $channelId,
        text: $text,
        schedulingType: automatic,
        mode: customScheduled,
        dueAt: $dueAt,
        assets: [{{ video: {{ url: $url }} }}],
        {meta}
      }}) {{
        ... on PostActionSuccess {{ post {{ id }} }}
        ... on MutationError {{ message }}
      }}
    }}"""
    return q, use_title


def read_txt(txt_path):
    if not os.path.exists(txt_path):
        return "", ""
    lines = open(txt_path, encoding="utf-8").read().split("\n")
    title = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    return title, body[:2000]


def load_pushed():
    """Vrati {filename: [sluzby_kde_uz_doslo]}. Migruje staru schemu (zoznam mien)."""
    if not os.path.exists(PUSHED):
        return {}
    data = json.load(open(PUSHED, encoding="utf-8"))
    if isinstance(data, list):
        # stara schema: ber kazde video ako hotove na vsetkych sluzbach (ziadne duplicity)
        return {name: sorted(WANT_SERVICES) for name in data}
    return data


def save_pushed(pushed):
    json.dump(pushed, open(PUSHED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def create_post(token, service, channel_id, text, url, title, due):
    """Posle 1 prispevok na 1 kanal naplanovany na presny cas (due); 1x zopakuje. Vrati (ok, sprava)."""
    q, use_title = build_mutation(service)
    v = {"channelId": channel_id, "text": text, "url": url, "dueAt": due}
    if use_title:
        v["title"] = title
    last = ""
    for attempt in range(2):
        try:
            res = gql(token, q, v)["createPost"]
            if res.get("message"):
                last = res["message"]
            else:
                return True, ""
        except Exception as e:
            last = str(e)
        if attempt == 0:
            time.sleep(3)
    return False, last


def upload_github_release(cfg, path, tag="media", ctype="video/mp4"):
    """Nahra subor ako asset GitHub Release (public repo = neobmedzeny free bandwidth).
    tag 'media' = videa pre Buffer, tag 'thumbs' = YT thumbnaily (dashboard setter ich
    odtial berie pre thumbnails.set). Vrati URL alebo vyhodi vynimku."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or cfg.get("gh_token", "")
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY") or cfg.get("gh_repo", "")
    if not token or not repo:
        raise RuntimeError("chyba GITHUB_TOKEN/GITHUB_REPOSITORY pre GitHub Release hosting")
    api = "https://api.github.com"
    H = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    r = requests.get(api + "/repos/" + repo + "/releases/tags/" + tag, headers=H, timeout=30)
    if r.status_code == 404:
        r = requests.post(api + "/repos/" + repo + "/releases", headers=H, timeout=30,
                          json={"tag_name": tag, "name": "media assets",
                                "body": "auto-hostovane videa pre Buffer (docasne, cistene automaticky)",
                                "prerelease": True})
    r.raise_for_status()
    rel = r.json()
    assets = rel.get("assets", [])
    name = os.path.basename(path)
    for a in assets:                       # prepis rovnomenneho assetu
        if a.get("name") == name:
            requests.delete(api + "/repos/" + repo + "/releases/assets/" + str(a["id"]), headers=H, timeout=30)
    old = sorted([a for a in assets if a.get("name") != name], key=lambda a: a.get("created_at", ""))
    for a in (old[:-40] if len(old) > 40 else []):   # hygiena: drz max 40 najnovsich
        requests.delete(api + "/repos/" + repo + "/releases/assets/" + str(a["id"]), headers=H, timeout=30)
    up = rel["upload_url"].split("{")[0]
    with open(path, "rb") as f:
        ur = requests.post(up + "?name=" + name,
                          headers={"Authorization": "Bearer " + token, "Content-Type": ctype},
                          data=f.read(), timeout=900)
    ur.raise_for_status()
    return ur.json()["browser_download_url"]


def _ffmpeg():
    """Cesta k ffmpeg: PATH (GitHub runner) alebo lokalny imageio-ffmpeg."""
    for c in ("ffmpeg", os.environ.get("FFMPEG_BIN", "")):
        if c and shutil.which(c):
            return shutil.which(c)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def pick_clean_frame(mp4, out_jpg):
    """Riddle videa nemaju hotovy thumbnail -> vyberieme frame BEZ vypaleneho titulku.
    Skenujeme len prvych ~40 %% videa (dalej uz byva odpoved = spoiler), skorujeme podiel
    skoro-bielych pixelov v titulkovom pase a berieme najcistejsi frame. Vrati True/False."""
    ff = _ffmpeg()
    if not ff:
        print("  [thumb] ffmpeg nenajdeny -> preskakujem")
        return False
    try:
        from PIL import Image
    except Exception:
        print("  [thumb] chyba Pillow -> preskakujem")
        return False
    tmp = tempfile.mkdtemp(prefix="thumb_")
    try:
        dur = 0.0
        pr = subprocess.run([ff, "-i", mp4], capture_output=True, text=True, timeout=120)
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", pr.stderr or "")
        if m:
            dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        scan = max(6.0, dur * 0.4) if dur else 20.0
        subprocess.run([ff, "-y", "-t", "%.2f" % scan, "-i", mp4,
                        "-vf", "fps=2,scale=270:-1", "-q:v", "4",
                        os.path.join(tmp, "f_%04d.jpg")], capture_output=True, timeout=300)
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
        if not frames:
            return False
        def caption_ratio(img):
            """Podiel skoro-bielych pixelov v pase, kde su vypalene titulky."""
            g = img.convert("L")
            w, h = g.size
            px = g.crop((0, int(h * 0.72), w, int(h * 0.92))).tobytes()
            return sum(1 for v in px if v > 235) / float(len(px))

        cands = []
        for f in frames:
            idx = int(f[2:6])
            if idx < 6:                      # prvych ~3 s preskoc (nabeh animacie)
                continue
            cands.append((caption_ratio(Image.open(os.path.join(tmp, f))), idx))
        if not cands:
            return False
        cands.sort()
        for score, idx in cands[:6]:
            ts = idx / 2.0                   # fps=2 -> index/2 = sekundy
            # -ss AZ ZA -i = presny seek (pred -i skace na keyframe a trafi iny frame)
            r = subprocess.run([ff, "-y", "-i", mp4, "-ss", "%.2f" % ts, "-frames:v", "1",
                                "-q:v", "2", out_jpg], capture_output=True, timeout=180)
            if r.returncode != 0 or not os.path.exists(out_jpg) or os.path.getsize(out_jpg) < 5000:
                continue
            real = caption_ratio(Image.open(out_jpg))   # over cistotu na SKUTOCNOM vysledku
            if real <= 0.0015:
                print("  [thumb] cisty frame @%.1fs (titulky %.2f%%)" % (ts, real * 100))
                return True
        print("  [thumb] nenasiel som frame bez titulku -> thumbnail preskakujem")
        if os.path.exists(out_jpg):
            os.remove(out_jpg)
        return False
    except Exception as e:
        print("  [thumb] vyber framu zlyhal (nekriticke): " + str(e)[:140])
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def host_thumbnail(cfg, jpg):
    """Nahra <slug>.jpg do 'thumbs' release (dashboard setter ho odtial vezme pre thumbnails.set)."""
    try:
        url = upload_github_release(cfg, jpg, tag="thumbs", ctype="image/jpeg")
        print("  [thumb] hostnuty -> " + url)
        return url
    except Exception as e:
        print("  [thumb] hosting zlyhal (nekriticke): " + str(e)[:140])
        return None


def host_video(cfg, path):
    """Primarne GitHub Releases (zadarmo, neobmedzeny bandwidth); fallback Cloudinary ak by zlyhal."""
    try:
        url = upload_github_release(cfg, path)
        print("  [host] GitHub Release OK -> " + url)
        return url
    except Exception as e:
        print("  [host] GitHub Release zlyhal (" + str(e)[:160] + ") -> fallback Cloudinary")
        return upload_cloudinary(cfg, path)

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    nums = [a for a in args if a.isdigit()]
    n = int(nums[0]) if nums else 1  # 1 video/den (anti-kanibalizacia)

    cfg = load_cfg()
    token = cfg.get("buffer_token", "").strip()
    if not token:
        print("CHYBA: chyba 'buffer_token' v config.json"); return
    for k in ("cloudinary_cloud_name", "cloudinary_api_key", "cloudinary_api_secret"):
        if not cfg.get(k):
            print(f"CHYBA: chyba '{k}' v config.json"); return

    # ID kanalov beru z configu (osobny token nema pravo listovat kanaly cez account-query)
    targets = cfg.get("buffer_channels") or []
    if not targets:
        chans = get_channels(token)
        targets = [c for c in chans if c.get("service", "").lower() in WANT_SERVICES]
    print("Kanaly: " + (", ".join(f"{c['service']}({c.get('name','')})" for c in targets) or "(ziadne)"))
    if not targets:
        print("CHYBA: ziadne kanaly v configu (buffer_channels)."); return

    pushed = load_pushed()
    target_services = {c["service"].lower() for c in targets}
    out_dir = os.path.join(ROOT, "output")
    if not os.path.isdir(out_dir):
        print("Ziadne videa (output/ neexistuje - banka nemala nove temy?) - preskakujem push."); return
    all_videos = sorted(f for f in os.listdir(out_dir) if f.endswith(".mp4"))
    # video treba spracovat, kym nie je odoslane na VSETKY cielove sluzby
    todo = [v for v in all_videos
            if not target_services.issubset(set(pushed.get(v, [])))][:n]
    if not todo:
        print("Ziadne nove videa na odoslanie."); return
    print(f"Na odoslanie: {len(todo)} videi -> {len(targets)} kanalov.")

    if dry:
        for v in todo:
            pend = [c["service"] for c in targets if c["service"].lower() not in set(pushed.get(v, []))]
            print(f"  (dry-run) {v} -> chyba: {', '.join(pend)}")
        return

    slots = next_slots(len(todo))  # casy publikovania (s jitterom) - i-te video -> i-ty slot
    tiktok_per_run = int(cfg.get("tiktok_per_run", 10**9))  # limit TikTok postov/beh (warm-up novych uctov); default bez limitu
    tiktok_done = 0
    for i, vid in enumerate(todo):
        due = slots[i]
        done = set(pushed.get(vid, []))
        pending = [c for c in targets if c["service"].lower() not in done]
        if not pending:
            continue
        mp4 = os.path.join(out_dir, vid)
        title, body = read_txt(mp4[:-4] + ".txt")
        title = title or "Daily Facts"
        yt_title = (title + " #shorts")[:100]
        print(f"\n=== {vid} ===  (cas {due}; chyba: {', '.join(c['service'] for c in pending)})")
        print("  nahravam video (GitHub Release / Cloudinary)...")
        url = host_video(cfg, mp4)
        jpg = mp4[:-4] + ".jpg"          # <slug>.jpg -> 'thumbs' release pre YT custom thumbnail
        if not os.path.exists(jpg):
            pick_clean_frame(mp4, jpg)   # riddle videa thumbnail nemaju -> vyrob z cisteho framu
        if os.path.exists(jpg):
            host_thumbnail(cfg, jpg)
        for c in pending:
            svc = c["service"].lower()
            if svc == "tiktok" and tiktok_done >= tiktok_per_run:
                # warm-up: novy TikTok ucet nezahlcuj (3x/den cez API = spam signal). Oznac vybavene, nepostuj.
                done.add(svc)
                pushed[vid] = sorted(done)
                save_pushed(pushed)
                print(f"  [tiktok] preskocene (limit {tiktok_per_run}/beh - zahrievanie uctu)")
                continue
            t = yt_title if svc == "youtube" else title
            # volitelna kriz. reklama na dokumenty (len fabriky co maju promo_* v configu)
            promo = cfg.get("promo_yt", "") if svc == "youtube" else cfg.get("promo_social", "")
            ok, msg = create_post(token, svc, c["id"], body + promo, url, t, due)
            if ok:
                if svc == "tiktok":
                    tiktok_done += 1
                done.add(svc)
                pushed[vid] = sorted(done)
                save_pushed(pushed)
                print(f"  [{svc}] do fronty OK")
            else:
                print(f"  [{svc}] CHYBA (skusi sa znova nabuduce): {msg}")

    fully = sum(1 for v in todo if target_services.issubset(set(pushed.get(v, []))))
    print(f"\nHOTOVO. Plne odoslane na vsetky platformy: {fully}/{len(todo)} videi.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_song.py — 搜歌 + 取直链 + 下载 FLAC + 完整性检查

依赖: stdlib + curl + ffprobe/ffmpeg (PATH 中可用)

用法:
    python3 fetch_song.py search "歌名"            # 列出候选（含时长，用于辨别同曲异版）
    python3 fetch_song.py get <ID> --out DIR       # 下载并校验
    python3 fetch_song.py lyrics <ID>              # 打印网易云歌词（lrc / tlyric / klyric）

说明:
  - 默认取原唱原版：用户没点版本时，不要用翻唱/Remix/伴奏
  - search 会给每条候选标「原版候选 / 翻唱&改编」，最终仍以时长 + 专辑 + fee 复核
  - 直链带时效，约 2 分钟过期；get 会在取到 URL 后立即下载，勿中途插入长任务
  - 付费曲 (fee:1) 与只给 mp3 的 (fee:8) 都自动走 gdstudio 镜像拿 FLAC
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": "https://music.163.com",
}
MIRROR = "https://music-api.gdstudio.xyz/api.php"


def _get(url, headers=None, timeout=25, retries=3):
    h = dict(UA)
    if headers:
        h.update(headers)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + i * 2)
    raise RuntimeError(f"请求失败 {url}: {last}")


COVER_HINT = re.compile(
    r"(cover|カバー|翻唱|翻自|remix|リミックス|inst\b|instrumental|off\s*vocal|伴奏"
    r"|piano|ピアノ|小提琴|二胡|吉他|八音盒|音乐盒|オルゴール|music\s*box"
    r"|8bit|填词|中文填词|ai\s*(做|版)|术力口|slowed|reverb|nightcore|sped\s*up"
    r"|合唱|六人|男声|女声|live\s*ver|ライブ)",
    re.IGNORECASE,
)


def version_note(name, artists):
    """粗略标注版本类型，帮助判断哪条是原唱原版。"""
    if COVER_HINT.search(name) or COVER_HINT.search(artists):
        return "翻唱/改编"
    return "原版候选"


def search(kw, limit=10):
    q = urllib.parse.quote(kw)
    url = f"https://music.163.com/api/search/get/web?s={q}&type=1&limit={limit}"
    d = json.loads(_get(url))
    songs = (d.get("result") or {}).get("songs") or []
    if not songs:
        print("没有结果。检查歌名写法，或换用更短的关键词。")
        return []
    rows = []
    for s in songs:
        ms = s.get("duration") or 0
        artists = ", ".join(a["name"] for a in s.get("artists", []))
        fee = s.get("fee", 0)
        rows.append({
            "id": s["id"],
            "name": s["name"],
            "artists": artists,
            "duration_ms": ms,
            "duration": f"{ms // 60000}:{ms % 60000 // 1000:02d}",
            "album": (s.get("album") or {}).get("name", ""),
            "fee": fee,
            "version": version_note(s["name"], artists),
        })
    print(f"{'ID':<12} {'时长':>6} {'fee':>4}  {'歌名':<30} {'版本':<8} 作者")
    print("-" * 100)
    for r in rows:
        print(f"{r['id']:<12} {r['duration']:>6} {r['fee']:>4}  {r['name'][:30]:<30} "
              f"{r['version']:<8} {r['artists']}")
    print("\n默认取「原版候选」里时长最完整的一条；同名不同曲看时长（差 5s 以上是另一首）。")
    print("标「翻唱/改编」的不是原版，用户没点名就不要选。")
    return rows


def _safe(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def get_url(sid):
    """镜像优先。

    注意：网易云自己的 enhance/player/url 即使传 br=999000 也只给 320k mp3，
    拿不到无损 FLAC。要 24bit FLAC 必须走 gdstudio 镜像。
    镜像不可用时才退回网易云 320k mp3（并提示用户）。
    """
    for _ in range(2):  # 镜像偶发限流
        try:
            raw = _get(f"{MIRROR}?types=url&source=netease&id={sid}")
            d = json.loads(raw)
            if d.get("url"):
                return d["url"], "flac", d.get("br")
            print(f"  镜像返回: {d.get('code')} {d.get('msg', '')}")
        except Exception as e:  # noqa: BLE001
            print(f"  镜像异常: {e}")
        time.sleep(3)

    print("  镜像不可用，退回网易云 320k mp3（非无损）…")
    d = json.loads(_get(f"https://music.163.com/api/song/enhance/player/url"
                        f"?ids=[{sid}]&br=320000"))
    items = d.get("data") or []
    if items and items[0].get("url"):
        return items[0]["url"], "mp3", items[0].get("br")
    raise RuntimeError("两条通道都拿不到直链")


def get(sid, outdir=".", name=None, artist=None):
    if not (name and artist):
        info = json.loads(_get(
            f"https://music.163.com/api/song/detail/?id={sid}&ids=[{sid}]"))
        s = (info.get("songs") or [None])[0]
        if not s:
            sys.exit("查不到这首歌的元信息")
        name = name or s["name"]
        artist = artist or ", ".join(a["name"] for a in s["artists"])
        dur_ms = s.get("duration", 0)
        print(f"《{name}》 / {artist} / {dur_ms/1000:.3f}s")

    url, typ, br = get_url(sid)
    ext = ".flac" if typ == "flac" else "." + typ
    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, f"{_safe(name)} - {_safe(artist)}{ext}")

    print(f"  下载 → {dest}")
    r = subprocess.run(["curl", "-L", "--max-time", "280", "--fail", "-sS",
                        "-o", dest, url])
    if r.returncode != 0:
        sys.exit("curl 下载失败（常见原因：直链 token 已过期，重新跑一次）")

    size = os.path.getsize(dest)
    if size < 200_000:
        sys.exit(f"文件仅 {size} 字节，几乎肯定是失效直链，重跑本命令")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "format=duration",
         "-show_entries", "stream=bits_per_raw_sample,sample_rate,sample_fmt",
         "-of", "default=nw=1", dest],
        capture_output=True, text=True).stdout.strip()
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", dest, "-f", "null", "-"],
                         capture_output=True, text=True)
    ok = dec.stderr.strip() == ""

    print(f"  大小 {size/1048576:.1f} MB · 码率 {br} kbps")
    print("  " + probe.replace("\n", " · "))
    print("  解码完整性: " + ("OK" if ok else "异常 —— 重新下载"))
    return dest


def lyrics(sid, show_karaoke=False):
    d = json.loads(_get(
        f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1"))
    for key in ("lrc", "klyric", "tlyric"):
        if key == "klyric" and not show_karaoke:
            continue
        body = (d.get(key) or {}).get("lyric", "")
        if not body.strip():
            continue
        n = len([l for l in body.splitlines() if l.startswith("[")])
        print(f"===== {key} ({n} 行) =====")
        print(body.strip()[:3000])
        print()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("keyword")
    s.add_argument("--limit", type=int, default=10)

    g = sub.add_parser("get")
    g.add_argument("sid")
    g.add_argument("--out", default=".")
    g.add_argument("--name")
    g.add_argument("--artist")

    l = sub.add_parser("lyrics")
    l.add_argument("sid")
    l.add_argument("--karaoke", action="store_true")

    a = ap.parse_args()
    if a.cmd == "search":
        search(a.keyword, a.limit)
    elif a.cmd == "get":
        get(a.sid, a.out, a.name, a.artist)
    else:
        lyrics(a.sid, a.karaoke)


if __name__ == "__main__":
    main()

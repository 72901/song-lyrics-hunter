#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一条命令产出交付三件套的歌词部分：原文 TXT + 日中双语 TXT。

来源：把此前 20 首歌逐个手写 buildN.py / biN.py 的流程固化为脚本。
做四件事：
  1. 解析源歌词（任意时间戳写法），过滤制作信息行，日文浊点修复 + NFC
  2. 调 lyrics_sync 的人声峰做吸附（默认容差 0.25s）
  3. 译文按「行序窗口」对齐（不是按时间戳查表——吸附后时间戳会位移）
  4. 输出 `<歌名> (歌词) - <作者>.txt` 与 `<歌名> (双语歌词) - <作者>.txt`

用法：
  python3 build_delivery.py --audio "a.flac" --lrc lrc.lrc --tlyric tlyric.lrc \
      --title "春嵐" --credit "词曲：john" --artist "john feat. 初音ミク" \
      --sections "0=【A段：虚像に塗れた私】;12=【副歌：春の嵐呼んだ】"

  --sections 的键是「对齐后可交付歌词」的行号（从 0 开始），不是源文件行号。
  想确认行号，先跑 --dry-run 打印带行号的清单。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lyrics_sync as L  # noqa: E402

# 制作信息 / 平台信息 / 装饰线：命中即丢弃
# 注意：只在「关键词 + 冒号」才算元信息。裸关键词会误杀正词，
# 例如「曲がりくねった」「movie のように」都不是元信息。
CREDIT_PAT = re.compile(
    r"^\s*(作词|作詞|作曲|编曲|編曲|制作人|製作人|producer|arranger|composer|lyricist"
    r"|mix|mastering|illust|illustration|movie|vocal|vocaloid|tuning|guitar|bass|drums)"
    r"\s*[:：]",
    re.IGNORECASE,
)
LINK_PAT = re.compile(r"(https?://|www\.|niconico|youtube|youtu\.be|twitter\.com)", re.IGNORECASE)
DECOR_PAT = re.compile(r"^[\s\u2500-\u257f\u3000=*\-—―_]+$")


def is_meta(txt: str) -> bool:
    return bool(CREDIT_PAT.search(txt) or LINK_PAT.search(txt) or DECOR_PAT.match(txt))


def fmt_sec(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    mm, rem = divmod(ms, 60000)
    ss, ms = divmod(rem, 1000)
    return f"{mm}:{ss:02d}"


def norm_text(s: str) -> str:
    s = s.replace("\uff9e", "\u3099").replace("\uff9f", "\u309a")
    return unicodedata.normalize("NFC", s).strip()


def parse(path: str):
    """返回 [(秒, 文本)]，保持文件顺序（同一时间戳的多行不合并）。"""
    rows = []
    for line in open(path, encoding="utf-8"):
        m = L.TS.search(line.rstrip("\n"))
        if not m:
            continue
        txt = norm_text(m.group(4))
        if not txt or is_meta(txt):
            continue
        rows.append([L.ts_to_sec(m), txt])
    rows.sort(key=lambda r: r[0])
    return rows


def dedupe_consecutive(rows):
    """去掉吸附后因同一行重复产生的完全重复项（时间戳+文本都相同）。"""
    out = []
    for r in rows:
        if out and abs(out[-1][0] - r[0]) < 0.001 and out[-1][1] == r[1]:
            continue
        out.append(r)
    return out


def align_translations(rows, cn_rows, window=4, tol=0.4):
    """按行序在 ±window 范围内找时间最接近的译文。

    不能按时间戳字典查：吸附把时间戳挪到人声峰后，原文与译文的键就对不上了。
    """
    aligned, j = [], 0
    for t, txt in rows:
        best, best_d = None, 9e9
        for k in range(max(0, j - window), min(len(cn_rows), j + window)):
            d = abs(cn_rows[k][0] - t)
            if d < best_d:
                best, best_d = k, d
        tr = cn_rows[best][1] if best is not None and best_d <= tol else ""
        if best is not None:
            j = max(j, best)
        aligned.append((t, txt, tr))
    return aligned


def snap(rows, audio, tol):
    env, dur = L.vocal_envelope(audio)
    peaks = np.asarray(L.find_onsets(env), dtype=float)

    def evaluate(rs):
        devs = np.array([abs(peaks[int(np.argmin(np.abs(peaks - t)))] - t) for t, _ in rs])
        return int((devs < L.HIT_TOL).sum()), float(devs.mean()), devs

    hit0, dev0, _ = evaluate(rows)
    moved = 0
    for r in rows:
        j = int(np.argmin(np.abs(peaks - r[0])))
        if abs(peaks[j] - r[0]) <= tol:
            r[0] = round(float(peaks[j]), 3)
            moved += 1
    hit1, dev1, _ = evaluate(rows)
    return dict(duration=round(dur, 3), total=len(rows), snapped=moved,
                hit_before=hit0, dev_before=round(dev0, 3),
                hit_after=hit1, dev_after=round(dev1, 3))


def parse_sections(spec: str):
    sec = {}
    for part in (spec or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        idx, title = part.split("=", 1)
        sec[int(idx.strip())] = title.strip()
    return sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio")
    ap.add_argument("--lrc", required=True, help="原文歌词（带时间戳）")
    ap.add_argument("--tlyric", help="中文译文歌词（带时间戳）")
    ap.add_argument("--title")
    ap.add_argument("--artist")
    ap.add_argument("--credit", default="", help='词曲信息行，如 "词曲：john"；留空则不写')
    ap.add_argument("--sections", default="", help='小节标题："行号=【标题】;行号=【标题】"')
    ap.add_argument("--tol", type=float, default=0.25, help="吸附容差（秒）")
    ap.add_argument("--no-snap", action="store_true", help="跳过吸附，仅做校验")
    ap.add_argument("--dir", default="/workspace/音乐下载")
    ap.add_argument("--plain-no-header", action="store_true",
                    help="纯原文版不写头部元信息（默认写，与既有交付一致）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = parse(args.lrc)
    if not rows:
        sys.exit("原文歌词里没有任何带时间戳的有效行")

    if args.dry_run:
        for i, (t, txt) in enumerate(rows):
            print(f"{i:>3}  {L.fmt_ts(t)}  {txt}")
        return

    missing = [k for k in ("audio", "title", "artist") if not getattr(args, k)]
    if missing:
        ap.error("缺少参数: " + ", ".join("--" + m for m in missing))

    stats = None if args.no_snap else snap(rows, args.audio, args.tol)
    rows = dedupe_consecutive(rows)

    cn_rows = parse(args.tlyric) if args.tlyric else []
    aligned = align_translations(rows, cn_rows) if cn_rows else [(t, x, "") for t, x in rows]

    hit = stats["hit_after"] if stats else 0
    dev = stats["dev_after"] if stats else 0.0
    total = len(aligned)
    head = [f"《{args.title}》"]
    if args.credit:
        head.append(args.credit)
    head.append(f"演唱：{args.artist}")
    head.append(f"时长：{fmt_sec(stats['duration'] if stats else 0)} · "
                f"时间轴精度：毫秒（人声峰校验 吸附后命中率 {100*hit/total:.0f}% / 平均偏差 {dev:.2f}s）")

    sections = parse_sections(args.sections)
    body = []
    for i, (t, txt, tr) in enumerate(aligned):
        if i in sections:
            body.append(f"==== {sections[i]} ====")
        ts = L.fmt_ts(t)
        body.append(f"{ts} {txt}")
        if tr:
            body.append(f"{ts} {tr}")

    os.makedirs(args.dir, exist_ok=True)
    bi_path = os.path.join(args.dir, f"{args.title} (双语歌词) - {args.artist}.txt")
    jp_path = os.path.join(args.dir, f"{args.title} (歌词) - {args.artist}.txt")
    with open(bi_path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + body) + "\n")
    with open(jp_path, "w", encoding="utf-8") as f:
        jp_head = [] if args.plain_no_header else head
        f.write("\n".join(jp_head + [f"{L.fmt_ts(t)} {txt}" for t, txt, _ in aligned]) + "\n")

    miss = [i for i, a in enumerate(aligned) if not a[2]]
    print(json.dumps({
        "lines": total,
        "translated": total - len(miss),
        "missing_rows": miss,
        "hit_rate": round(hit / total, 4),
        "mean_dev": dev,
        "files": [bi_path, jp_path],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lyrics_sync.py — 歌词时间轴体检 / 吸附 / 规范化

依赖: numpy, scipy, ffmpeg (PATH 中可用)

用法:
    python3 lyrics_sync.py AUDIO [LYRICS] [--snap] [--write] [--out PATH]

    AUDIO    音频文件 (.flac/.mp3/...)
    LYRICS   歌词文件；省略则只输出人声峰分布，供人工参考

    --snap    把时间戳吸附到最近人声峰（仅当偏差 <= --tol）
    --tol     吸附容差，默认 0.25 秒
    --write   吸附结果写回歌词文件（或 --out 指定路径）
    --report  只看精度报告，不打印逐句明细
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata

import numpy as np
from scipy.signal import find_peaks

SR = 16000
FRAME = 400
HOP = 160
VOCAL_LO, VOCAL_HI = 300, 3400
HIT_TOL = 0.45


# ---------------------------------------------------------------- 音频分析
def vocal_envelope(path):
    """解码为 16k 单声道 -> 分帧 FFT -> 人声频段能量包络"""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True,
    )
    if raw.returncode != 0:
        sys.exit("ffmpeg 解码失败: " + raw.stderr.decode("utf-8", "ignore")[:400])
    if not raw.stdout:
        sys.exit("ffmpeg 未输出音频数据，请检查文件是否损坏")

    x = np.frombuffer(raw.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    n = (len(x) - FRAME) // HOP
    if n <= 0:
        sys.exit("音频过短")

    frames = np.lib.stride_tricks.as_strided(
        x, shape=(n, FRAME),
        strides=(x.strides[0] * HOP, x.strides[0]),
    )
    window = np.hanning(FRAME).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames * window, axis=1))
    freqs = np.fft.rfftfreq(FRAME, 1.0 / SR)

    vocal = spec[:, (freqs >= VOCAL_LO) & (freqs <= VOCAL_HI)].sum(axis=1)
    env = np.convolve(vocal, np.ones(30) / 30, mode="same")
    env = (env - env.min()) / (env.max() - env.min() + 1e-9)
    return env, len(x) / SR


def find_onsets(env, min_gap=0.35, height=0.12, prominence=0.02):
    dt = HOP / SR
    peaks, _ = find_peaks(
        env,
        height=height,
        distance=max(1, int(min_gap / dt)),
        prominence=prominence,
    )
    return peaks * dt


# ---------------------------------------------------------------- 歌词解析
TS = re.compile(r"\[(\d{1,2}):(\d{2})(?:[:.](\d{1,3}))?\]\s*(.*)")

# 制作信息 / 平台链接 / 装饰线
META_PAT = re.compile(
    r"(作词|作曲|编曲|詞|曲|編曲|producer|arranger|composer|lyricist"
    r"|niconico|youtube|youtu\.be|http|www\."
    r"|^\s*[\u2500-\u257f\u3000\s=]+$)",
    re.IGNORECASE,
)


def normalize_jp(s):
    """半角浊点 -> 合成用浊点，再做 NFC"""
    s = s.replace("\uff9e", "\u3099").replace("\uff9f", "\u309a")
    return unicodedata.normalize("NFC", s)


def ts_to_sec(m):
    mm, ss, frac = int(m.group(1)), int(m.group(2)), m.group(3) or ""
    if len(frac) == 3:
        ms = int(frac)
    elif len(frac) == 2:
        ms = int(frac) * 10
    elif len(frac) == 1:
        ms = int(frac) * 100
    else:
        ms = 0
    return mm * 60 + ss + ms / 1000.0


def fmt_ts(t):
    ms = int(round(max(0.0, t) * 1000))
    mm, rem = divmod(ms, 60000)
    ss, ms = divmod(rem, 1000)
    return f"[{mm:02d}:{ss:02d}.{ms:03d}]"


def parse_lyrics(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = TS.search(line)
        if not m:
            continue
        text = normalize_jp(m.group(4).strip())
        if not text or META_PAT.search(text):
            continue
        rows.append([ts_to_sec(m), text])
    rows.sort(key=lambda r: r[0])
    return rows


def render(rows):
    return "\n".join(f"{fmt_ts(t)} {txt}" for t, txt in rows) + "\n"


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("lyrics", nargs="?")
    ap.add_argument("--snap", action="store_true", help="吸附到最近人声峰")
    ap.add_argument("--tol", type=float, default=0.25, help="吸附容差（秒）")
    ap.add_argument("--write", action="store_true", help="写回歌词文件")
    ap.add_argument("--out", help="另存路径")
    ap.add_argument("--report", action="store_true", help="不打印逐句明细")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出指标")
    args = ap.parse_args()

    env, dur = vocal_envelope(args.audio)
    peaks = find_onsets(env)
    dt = HOP / SR

    if not args.lyrics:
        print(f"时长 {dur:.2f}s，人声峰 {len(peaks)} 个")
        print("前 20 个峰: " + ", ".join(f"{p:.2f}" for p in peaks[:20]))
        return

    rows = parse_lyrics(args.lyrics)
    if not rows:
        sys.exit("未解析到任何带时间戳的歌词行")

    def evaluate(rs):
        devs = []
        for t, _ in rs:
            j = int(np.argmin(np.abs(peaks - t)))
            devs.append(abs(peaks[j] - t))
        devs = np.array(devs)
        hit = int((devs < HIT_TOL).sum())
        return hit, len(rs), float(devs.mean()), devs

    hit0, total, dev0, _ = evaluate(rows)
    if not args.json:
        print(f"音频 {dur:.2f}s · 歌词 {total} 句 · 人声峰 {len(peaks)} 个")
        print(f"原始时间轴: {hit0}/{total} ({100*hit0/total:.0f}%), 平均偏差 {dev0:.2f}s")

    snapped = 0
    if args.snap:
        for r in rows:
            j = int(np.argmin(np.abs(peaks - r[0])))
            if abs(peaks[j] - r[0]) <= args.tol:
                r[0] = round(float(peaks[j]), 3)
                snapped += 1
        hit1, _, dev1, devs1 = evaluate(rows)
        if not args.json:
            print(f"吸附 {snapped} 句 (容差 {args.tol}s) → "
                  f"{hit1}/{total} ({100*hit1/total:.0f}%), 平均偏差 {dev1:.2f}s")
    else:
        devs1 = evaluate(rows)[3]

    if not args.report and not args.json:
        print("-" * 52)
        for (t, txt), d in zip(rows, devs1):
            flag = "  " if d < args.tol else ("!!" if d < HIT_TOL else "XX")
            print(f"{flag} {fmt_ts(t)}  Δ{d:5.2f}  {txt[:40]}")

    if args.json:
        hit1, _, dev1, _ = evaluate(rows)
        print(json.dumps({
            "duration": round(dur, 3),
            "lines": total,
            "snapped": snapped,
            "hit_rate": round(hit1 / total, 4),
            "mean_dev": round(dev1, 4),
            "hit_rate_before": round(hit0 / total, 4),
            "mean_dev_before": round(dev0, 4),
        }, ensure_ascii=False))

    if args.write or args.out:
        dest = args.out or args.lyrics
        with open(dest, "w", encoding="utf-8") as f:
            f.write(render(rows))
        print(f"已写入 {dest}")


if __name__ == "__main__":
    main()

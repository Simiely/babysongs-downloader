#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝贝中文 UP 主歌曲下载 + AI 分段裁切器
=========================================
两阶段工作流（先标节点、再裁切，避免自动切错不可控）：
  1) detect：下载视频音频 -> AI 检测每首歌的时间节点 -> 输出 segments.json（可审阅/微调）
  2) cut   ：读取 segments.json -> ffmpeg 按节点裁切 -> Whisper 识别歌词自动命名

增强：
  --lrc / --srt ：detect 同时导出时间戳文件，方便边听边校对节点
  --auto        ：detect 后跳过人工审阅直接裁切（仍生成 segments.json 供回看）

依赖
----
- 必须：yt-dlp（下载）、ffmpeg（转码/裁切）
- detect 必须：librosa（pip install librosa）
- 命名可选：openai-whisper（pip install openai-whisper）

用法
----
# 下载整段 mp3（原功能）
python baby_songs_downloader.py --uid 626735752 --limit 10 -o D:/BabySongs

# 检测歌曲节点 + 导出 LRC/SRT 供校对
python baby_songs_downloader.py --detect --url "<视频URL>" -o D:/BabySongs --lrc --srt

# 一键：检测后直接裁切（省事，但仍产出 segments.json）
python baby_songs_downloader.py --detect --uid 626735752 --auto --cookies-from-browser chrome -o D:/BabySongs --whisper

# 审阅 segments.json 后手动裁切
python baby_songs_downloader.py --cut D:/BabySongs/xxx_segments.json -o D:/BabySongs --whisper
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import datetime


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][{level}] {msg}", flush=True)


def run(cmd, timeout=None):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as e:
        return 127, "", str(e)


def check_deps():
    missing = []
    if not shutil.which("yt-dlp"):
        missing.append("yt-dlp")
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    return missing


def resolve_url(args):
    if args.url:
        return args.url
    if args.uid:
        return f"https://space.bilibili.com/{args.uid}/video"
    return None


def list_videos(target, cookie_opts):
    cmd = ["yt-dlp", "--flat-playlist", "--print", "%(webpage_url)s", *cookie_opts, target]
    rc, out, err = run(cmd)
    if rc != 0:
        log(f"列出视频失败: {err.strip()[:300]}", "ERROR")
        return []
    return [u.strip() for u in out.splitlines() if u.strip()]


def get_title(url, cookie_opts):
    cmd = ["yt-dlp", "--no-warnings", "--print", "%(title)s", *cookie_opts, url]
    rc, out, err = run(cmd, timeout=60)
    return out.strip() or "untitled"


def sanitize(name):
    name = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(".").strip()
    return name[:120]


def download_one(url, out_path, cookie_opts):
    cmd = ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
           "--embed-metadata", "--no-overwrites", "-c", *cookie_opts,
           "-o", out_path, url]
    rc, out, err = run(cmd, timeout=900)
    return rc == 0, (err.strip()[:200] if rc != 0 else "")


def otsu_threshold(vals):
    """对能量直方图做 OTSU 自适应二值化，找最优分割阈值（不假设歌曲/解说比例）。"""
    import numpy as np
    v = vals[vals > 1e-9]
    if v.size == 0:
        return 0.0
    hist, edges = np.histogram(v, bins=256)
    centers = (edges[:-1] + edges[1:]) / 2.0
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.0
    sum_total = (hist * centers).sum()
    sum_b = 0.0
    w_b = 0.0
    max_var = -1.0
    best = centers[0]
    for i in range(len(hist)):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += hist[i] * centers[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_b = w_b * w_f * (m_b - m_f) ** 2
        if var_b > max_var:
            max_var = var_b
            best = centers[i]
    return float(best)


def detect_songs(audio_path, min_duration=8.0, merge_gap=1.5, energy_ratio=1.0):
    """用 librosa 检测音频里每首歌（高能量/有伴奏）的时间段。

    原理：儿歌段有强伴奏+持续能量，解说段能量低且有停顿。
    用 RMS 能量包络 + OTSU 自适应阈值定位高能量段，再合并/过滤。
    """
    import numpy as np
    import librosa
    from scipy.ndimage import uniform_filter1d

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    rms = uniform_filter1d(rms, size=5)  # 轻度平滑
    thresh = max(otsu_threshold(rms) * energy_ratio, 1e-4)
    active = rms > thresh
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)

    raw = []
    start = None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            raw.append([times[start], times[i]])
            start = None
    if start is not None:
        raw.append([times[start], times[-1]])

    merged = []
    for s, e in raw:
        if merged and (s - merged[-1][1]) <= merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    segs = [{"start": round(float(s), 2), "end": round(float(e), 2),
             "duration": round(float(e - s), 2)}
            for s, e in merged if (e - s) >= min_duration]

    return {"source": os.path.abspath(audio_path),
            "duration": round(len(y) / sr, 2),
            "segments": segs}


def _lrc_ts(sec):
    sec = float(sec)
    m = int(sec // 60)
    s = sec - m * 60
    return f"[{m:02d}:{s:05.2f}]"


def _srt_ts(sec):
    sec = float(sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def write_lrc(data, path):
    out = ["[ti:宝贝中文歌曲片段]", ""]
    for i, s in enumerate(data["segments"], 1):
        out.append(f"{_lrc_ts(s['start'])} 第{i}首")
        out.append(f"{_lrc_ts(s['end'])}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def write_srt(data, path):
    out = []
    for i, s in enumerate(data["segments"], 1):
        out.append(str(i))
        out.append(f"{_srt_ts(s['start'])} --> {_srt_ts(s['end'])}")
        out.append(f"第{i}首歌")
        out.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def whisper_name(tmp_path, index):
    """用 Whisper 转写前 15s 歌词，给裁切文件命名。需 openai-whisper。"""
    try:
        import whisper
    except Exception:
        log("未安装 openai-whisper，使用序号命名", "WARN")
        return None
    try:
        model = whisper.load_model("tiny")
        res = model.transcribe(tmp_path, duration=15)
        text = (res.get("text") or "").strip()
        if not text:
            return None
        title = re.sub(r'[\\/*?:"<>|]', "_", text)[:20].strip()
        if not title:
            return None
        d = os.path.dirname(tmp_path)
        final = os.path.join(d, f"{index:03d} - {title}.mp3")
        if not os.path.exists(final):
            os.rename(tmp_path, final)
            return final
    except Exception as e:
        log(f"Whisper 命名失败: {e}", "WARN")
    return None


def cut_segments(seg_path, out_dir, whisper):
    with open(seg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    audio = data.get("source")
    segs = data.get("segments", [])
    if not audio or not os.path.exists(audio):
        log(f"源音频不存在: {audio}", "ERROR")
        sys.exit(2)
    if not segs:
        log("segments.json 中没有歌曲段", "WARN")
        sys.exit(0)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    total = len(segs)
    for i, seg in enumerate(segs, 1):
        tmp = os.path.join(out_dir, f"{i:03d}.tmp.mp3")
        cmd = ["ffmpeg", "-y", "-ss", str(seg["start"]), "-to", str(seg["end"]),
               "-i", audio, "-vn", "-acodec", "libmp3lame", "-q:a", "2", tmp]
        rc, _, err = run(cmd, timeout=120)
        if rc != 0 or not os.path.exists(tmp):
            results.append({"index": i, "error": err.strip()[:200]})
            log(f"  第 {i} 段裁切失败: {err.strip()[:120]}", "ERROR")
            continue
        final = os.path.join(out_dir, f"{i:03d}.mp3")
        if whisper:
            named = whisper_name(tmp, i)
            if named:
                final = named
            else:
                os.rename(tmp, final)
        else:
            os.rename(tmp, final)
        results.append({"index": i, "file": os.path.basename(final)})
        log(f"({i}/{total}) -> {os.path.basename(final)}")
    ok = all("error" not in r for r in results)
    if whisper:
        log("（命名已尝试 Whisper；失败项回退为序号）", "INFO")
    log(f"裁切完成：成功 {sum(1 for r in results if 'error' not in r)}/{total}", "INFO")
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(description="宝贝中文 歌曲下载 + AI 分段裁切器")
    p.add_argument("--uid", help="UP 主 UID，如 626735752")
    p.add_argument("--url", help="视频 / 合集 / 空间 URL")
    p.add_argument("-o", "--output", default="./BabySongs", help="输出目录")
    p.add_argument("--limit", type=int, default=0, help="下载模式：最多几个，0=全部")
    p.add_argument("--list", action="store_true", help="只列出视频")
    p.add_argument("--detect", action="store_true", help="检测歌曲时间节点 -> segments.json")
    p.add_argument("--cut", help="segments.json 路径，按节点裁切")
    p.add_argument("--audio", help="detect 直接用本地音频文件（跳过下载）")
    p.add_argument("--min-duration", type=float, default=8.0,
                   help="detect：最短歌曲段秒数（默认 8）")
    p.add_argument("--merge-gap", type=float, default=1.5,
                   help="detect：段间合并间隙秒数（默认 1.5）")
    p.add_argument("--energy-ratio", type=float, default=1.0,
                   help="detect：能量阈值倍数（默认 1.0，越大越严格）")
    p.add_argument("--lrc", action="store_true", help="detect：同时导出 LRC 时间戳")
    p.add_argument("--srt", action="store_true", help="detect：同时导出 SRT 时间戳")
    p.add_argument("--auto", action="store_true",
                   help="detect 后跳过人工审阅直接裁切（仍生成 segments.json）")
    p.add_argument("--whisper", action="store_true", help="cut：用 Whisper 歌词命名")
    p.add_argument("--cookies", help="cookies.txt 路径")
    p.add_argument("--cookies-from-browser", help="浏览器名，如 chrome / edge")
    p.add_argument("--json", action="store_true", help="JSON 输出（便于 AI 解析）")
    args = p.parse_args()

    missing = check_deps()
    if missing:
        log("缺少依赖: " + ", ".join(missing), "ERROR")
        log("Windows: pip install yt-dlp；ffmpeg 见 https://www.gyan.dev/ffmpeg/builds/", "ERROR")
        sys.exit(2)

    cookie_opts = []
    if args.cookies:
        cookie_opts += ["--cookies", args.cookies]
    if args.cookies_from_browser:
        cookie_opts += ["--cookies-from-browser", args.cookies_from_browser]

    # ---- 裁切阶段 ----
    if args.cut:
        if not os.path.exists(args.cut):
            log(f"segments.json 不存在: {args.cut}", "ERROR")
            sys.exit(2)
        cut_segments(args.cut, args.output, args.whisper)
        return

    # ---- 检测阶段 ----
    if args.detect:
        try:
            import librosa  # noqa
        except Exception:
            log("detect 模式需要 librosa：pip install librosa", "ERROR")
            sys.exit(2)

        os.makedirs(args.output, exist_ok=True)
        if args.audio and os.path.exists(args.audio):
            audio = args.audio
            log(f"使用本地音频: {audio}")
        else:
            target = resolve_url(args)
            if not target:
                log("detect 需提供 --audio 或 --url/--uid", "ERROR")
                sys.exit(2)
            videos = list_videos(target, cookie_opts)
            if not videos:
                log("未找到视频，可能需登录(cookie)或链接有误", "ERROR")
                sys.exit(2)
            v = videos[0]
            title = get_title(v, cookie_opts)
            audio = os.path.join(args.output, sanitize(title) + ".mp3")
            if os.path.exists(audio):
                log("音频已存在，跳过下载")
            else:
                log(f"下载音频: {title}")
                ok, err = download_one(v, audio, cookie_opts)
                if not ok:
                    log(f"下载失败: {err}", "ERROR")
                    sys.exit(2)

        log("AI 检测歌曲时间节点中...")
        data = detect_songs(audio, args.min_duration, args.merge_gap, args.energy_ratio)
        stem = sanitize(os.path.splitext(os.path.basename(audio))[0])
        seg_path = os.path.join(args.output, f"{stem}_segments.json")
        with open(seg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        mmss = lambda s: f"{int(s)//60:02d}:{int(s)%60:02d}"
        log(f"音频时长 {mmss(data['duration'])}，检出 {len(data['segments'])} 首歌", "INFO")
        for i, s in enumerate(data["segments"], 1):
            print(f"  #{i:02d}  {mmss(s['start'])} ~ {mmss(s['end'])}  ({s['duration']:.1f}s)")
        log(f"节点已写入: {seg_path}", "INFO")

        if args.lrc:
            lrc_path = seg_path[:-len("_segments.json")] + ".lrc"
            write_lrc(data, lrc_path)
            log(f"已导出 LRC: {lrc_path}", "INFO")
        if args.srt:
            srt_path = seg_path[:-len("_segments.json")] + ".srt"
            write_srt(data, srt_path)
            log(f"已导出 SRT: {srt_path}", "INFO")

        if args.auto:
            log("检测到 --auto，跳过人工审阅直接裁切...", "INFO")
            cut_segments(seg_path, args.output, args.whisper)
            return

        log("请审阅/微调后执行: python baby_songs_downloader.py --cut " +
            f"\"{seg_path}\" -o \"{args.output}\" --whisper", "INFO")
        sys.exit(0)

    # ---- 纯下载阶段（原功能） ----
    target = resolve_url(args)
    if not target:
        log("请提供 --uid / --url，或用 --detect / --cut", "ERROR")
        sys.exit(2)
    videos = list_videos(target, cookie_opts)
    if not videos:
        log("未找到视频，可能需登录(cookie)或链接有误", "ERROR")
        sys.exit(2)
    if args.list:
        if args.json:
            print(json.dumps({"ok": True, "count": len(videos),
                              "videos": videos}, ensure_ascii=False))
        else:
            log(f"共 {len(videos)} 个视频:", "INFO")
            for i, v in enumerate(videos, 1):
                print(f"  {i}. {v}")
        sys.exit(0)
    if args.limit > 0:
        videos = videos[: args.limit]
    os.makedirs(args.output, exist_ok=True)
    results = {"success": [], "failed": []}
    total = len(videos)
    for i, v in enumerate(videos, 1):
        title = get_title(v, cookie_opts)
        safe = sanitize(f"{i:03d} - {title}")
        out_path = os.path.join(args.output, safe + ".mp3")
        log(f"({i}/{total}) {title}")
        if os.path.exists(out_path):
            results["success"].append(out_path)
            log("  已存在，跳过")
            continue
        ok, err = download_one(v, out_path, cookie_opts)
        if ok and os.path.exists(out_path):
            results["success"].append(out_path)
            log(f"  成功 -> {os.path.basename(out_path)}")
        else:
            results["failed"].append({"url": v, "error": err})
            log(f"  失败: {err}", "ERROR")
    if args.json:
        print(json.dumps({"ok": len(results["failed"]) == 0,
                          "success_count": len(results["success"]),
                          "failed_count": len(results["failed"]),
                          "output": os.path.abspath(args.output),
                          "success": [os.path.basename(p) for p in results["success"]],
                          "failed": results["failed"]}, ensure_ascii=False))
    else:
        log(f"完成：成功 {len(results['success'])}，失败 {len(results['failed'])}", "INFO")
        log(f"输出目录: {os.path.abspath(args.output)}", "INFO")
    sys.exit(0 if not results["failed"] else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
合并视频里相邻的两首歌为一段，并重算清单。

典型用途：用户说“把 #28 和 #29 合并成一个 29，取 #29 前 26 秒”。

做法（关键：永远从【原始长音频】重切，不要 concat 小 mp3，避免接缝）：
  1. 读取 <video>_segments.json，校验 a、b 相邻。
  2. merged = [ a.start , b.start + take_b ]   （take_b 默认取满 b）
  3. 把 a、b 两段替换为一段 merged，写回 segments.json（先备份到 _backup_/）。
  4. ffmpeg 从原始长音频重切 merged -> <merged_num>.mp3
  5. 删除被吞掉的那个 mp3（merged-num=b 时删 a；=a 时删 b）。
  6. 重算 歌曲清单.md（被吞那段出现“编号空洞”，后续段编号不变）。

编号约定（默认，与“合并为一个29”一致）：
  - merged-num = b（默认）：合并段沿用 #b 的编号，#a 被删除 -> 后出现 #a 的空洞。
  - merged-num = a：合并段沿用 #a 的编号，#b 被删除 -> 后出现 #b 的空洞。
  （不做“后续段整体前移重编号”，保持音频文件不动、最安全。）

依赖：ffmpeg 在 PATH；python3.11。
"""
import argparse, json, os, shutil, subprocess, sys

FFMPEG = ["ffmpeg", "-y", "-ss", "{s}", "-to", "{e}",
           "-i", "{audio}", "-vn", "-acodec", "libmp3lame", "-q:a", "2", "{out}"]


def mmss(s):
    s = int(round(s))
    return "%02d:%02d" % (s // 60, s % 60)


def main():
    ap = argparse.ArgumentParser(description="合并相邻两段歌曲并刷新清单")
    ap.add_argument("--seg", required=True, help="<video>_segments.json 路径")
    ap.add_argument("--a", type=int, required=True, help="第一段下标（0-based，即 #(a+1)）")
    ap.add_argument("--b", type=int, required=True, help="第二段下标（0-based，应 = a+1）")
    ap.add_argument("--take-b", type=float, default=None,
                    help="合并时从 #b 起点取多少秒（默认取满整段 #b）")
    ap.add_argument("--merged-num", choices=["a", "b"], default="b",
                    help="合并段沿用哪段的编号（默认 b）")
    args = ap.parse_args()

    seg_path = args.seg
    a, b = args.a, args.b
    if b != a + 1:
        sys.exit(f"[错] --b ({b}) 必须 = --a+1 ({a + 1})，只支持相邻两段合并")

    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)
    segs = data["segments"]
    if not (0 <= a < b < len(segs)):
        sys.exit(f"[错] 下标越界：len(segments)={len(segs)}，a={a} b={b}")

    A, B = segs[a], segs[b]
    take_b = args.take_b if args.take_b is not None else (B["end"] - B["start"])
    merged_start = A["start"]
    merged_end = B["start"] + take_b
    if merged_end > B["end"] + 1e-6:
        merged_end = B["end"]  # 取满时截断到 b 真实终点
    merged = {"start": round(merged_start, 2),
              "end": round(merged_end, 2),
              "duration": round(merged_end - merged_start, 2)}

    out_dir = os.path.dirname(os.path.abspath(seg_path))
    base = os.path.splitext(os.path.basename(seg_path))[0].replace("_segments", "")
    audio = data.get("source") or os.path.join(out_dir, base + ".mp3")
    if not os.path.exists(audio):
        sys.exit(f"[错] 找不到原始长音频：{audio}（segments.json 的 source 字段无效）")

    print(f"[merge] {base}：#{a + 1} {A['start']}~{A['end']}  +  "
          f"#{b + 1} {B['start']}~{B['end']}")
    print(f"[merge] -> merged {merged['start']}~{merged['end']} "
          f"(时长 {merged['duration']}s, 取#{b + 1}前 {take_b}s)")

    # 1) 备份旧 segments.json 到 _backup_/
    backup_dir = os.path.join(out_dir, "_backup_", base)
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy(seg_path, os.path.join(backup_dir, os.path.basename(seg_path)))
    print(f"[backup] 已备份原 segments.json -> {backup_dir}")

    # 2) 改写 segments.json
    new_segs = segs[:a] + [merged] + segs[b + 1:]
    data["segments"] = new_segs
    with open(seg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[segments] 旧 {len(segs)} -> 新 {len(new_segs)} 段")

    # 3) ffmpeg 从原始长音频重切合并段
    merged_num = (a + 1) if args.merged_num == "a" else (b + 1)
    merged_file = os.path.join(out_dir, f"{merged_num:03d}.mp3")
    cmd = [c.format(s=merged["start"], e=merged["end"], audio=audio, out=merged_file)
           for c in FFMPEG]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.exit("[错] ffmpeg 失败:\n" + r.stderr.decode("utf-8", "ignore"))
    print(f"[ffmpeg] 已生成 {merged_file}")

    # 4) 删除被吞掉的那个 mp3
    eaten_num = (b + 1) if args.merged_num == "a" else (a + 1)
    eaten_file = os.path.join(out_dir, f"{eaten_num:03d}.mp3")
    if os.path.exists(eaten_file):
        os.remove(eaten_file)
        print(f"[del] 已删除被合并的旧文件 {eaten_file}")

    # 5) 重算 歌曲清单.md（被吞段出现编号空洞）
    md_path = os.path.join(out_dir, "歌曲清单.md")
    lines = ["# 宝贝中文 · 歌曲清单", "",
             f"> 来源视频：**{base}**  ",
             f"> 音频总时长 {data['duration'] / 60:.1f} 分，AI 检出 {len(new_segs)} 首，已裁为独立 mp3",
             "",
             "| # | 时间段 | 时长 | 文件 |",
             "|---|---|---|---|"]
    for i, seg in enumerate(new_segs):
        if i < a:
            num = i + 1
        elif i == a:                      # 合并段
            num = merged_num
        else:                            # i > a：原编号 = i+1，空洞在 eaten_num
            num = i + 1
        lines.append(f"| {num:02d} | {mmss(seg['start'])} ~ {mmss(seg['end'])} "
                     f"| {seg['duration']:.1f}s | `{num:03d}.mp3` |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[md] 已重写 歌曲清单.md，共 {len(new_segs)} 首")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# 宝贝中文 歌曲下载 一键运行脚本
# 用法：
#   ./run_download.sh <视频BV链接或合集链接>            # 全自动：检测节点 + 直接裁切成独立 mp3
#   ./run_download.sh <链接> review                      # 只检测节点并导出 LRC/SRT，人工核对后再裁切
#   ./run_download.sh                                   # 不带参数 = 下载「宝贝中文」最新一个视频并全自动裁切
#
# 前置：把从已登录 B站 的浏览器导出的 cookies.txt 放到 ./cookies/bilibili_cookies.txt
set -euo pipefail
cd "$(dirname "$0")"

COOKIES="cookies/bilibili_cookies.txt"
OUT="BabySongs"
SCRIPT="scripts/baby_songs_downloader.py"
PY=python3.11

if [ ! -f "$COOKIES" ]; then
  echo "❌ 未找到 cookies 文件：$COOKIES"
  echo "   请先把从已登录 B站 的浏览器导出的 cookies.txt 放到该路径（Netscape 格式）。"
  exit 2
fi

URL="${1:-https://space.bilibili.com/626735752/video}"
MODE="${2:-auto}"

mkdir -p "$OUT"

if [ "$MODE" = "review" ]; then
  echo "▶ 仅检测节点（含 LRC/SRT），供人工核对…"
  "$PY" "$SCRIPT" --detect --cookies "$COOKIES" --url "$URL" -o "$OUT" --lrc --srt
  echo ""
  echo "核对完成后执行裁切："
  echo "  $PY $SCRIPT --cut \"$OUT/<xxx>_segments.json\" -o \"$OUT\""
else
  echo "▶ 检测节点 + 直接裁切（全自动）…"
  "$PY" "$SCRIPT" --detect --cookies "$COOKIES" --url "$URL" -o "$OUT" --lrc --srt --auto
fi

echo ""
echo "✅ 产出目录：$OUT"
ls -la "$OUT"/*.mp3 2>/dev/null | awk '{print $5, $9}'

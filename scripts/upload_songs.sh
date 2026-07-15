#!/usr/bin/env bash
# 把已处理视频里的精选歌曲上传到仓库 song/<视频短名>/，并安全推送。
#
# 用法：
#   ./scripts/upload_songs.sh <视频短名> <编号1> [编号2 ...]
#   例：./scripts/upload_songs.sh 宝宝第一个词 005 012 014 023 025 028 030
#
# 要点（固化“防误删”流程，详见 开发README.md §7）：
#   - 先 `git checkout -- song/` 把本地镜像恢复到与远程一致（之前清理本地可能留下未提交的 D）
#   - 只 `git add song/<短名>/` 这一个【新增】文件夹，绝不 git add -A
#   - 提交前打印暂存区，确认没有 D 删除旧歌
#   - 推送
#
# 歌曲来源优先级：
#   1) BabySongs/<编号>.mp3 存在 -> 直接拷
#   2) 不存在，但 _backup_/<短名>/segments.json 里有该编号的原段 -> 从原始长音频重切
#   3) 都没有 -> 警告并跳过（不会中断）
set -euo pipefail
cd "$(dirname "$0")/.."                       # 切到仓库根

SHORT="${1:?用法: $0 <视频短名> <编号...>}"
shift
[ "$#" -ge 1 ] || { echo "❌ 至少要给一个编号"; exit 2; }

SONGDST="song/$SHORT"
mkdir -p "$SONGDST"

echo "▶ 恢复 song/ 镜像到与远程一致（防误删已传歌曲）"
git checkout -- song/ 2>/dev/null || true

PY=python3.11
ok=0; skip=0
for num in "$@"; do
  dst="$SONGDST/$(printf '%03d' "$num").mp3"
  # 1) 直接拷已存在的 mp3
  if [ -f "BabySongs/$(printf '%03d' "$num").mp3" ]; then
    cp "BabySongs/$(printf '%03d' "$num").mp3" "$dst"
    echo "  ✓ $num (来自 BabySongs)"
    ok=$((ok+1)); continue
  fi
  # 2) 从 _backup_ 的原始 segments 重切（适用于已合并/清理过的旧视频）
  bak="_backup_/$SHORT/segments.json"
  if [ -f "$bak" ]; then
    idx=$((num-1))
    "$PY" - "$bak" "$num" "$SHORT" <<'PYEOF'
import json, os, subprocess, sys
bak, num, short = sys.argv[1], int(sys.argv[2]), sys.argv[3]
d = json.load(open(bak, encoding="utf-8"))
segs = d["segments"]
if not (0 <= num-1 < len(segs)):
    print(f"  ⚠ {num} 不在备份 segments 范围(0..{len(segs)-1})，跳过"); sys.exit(3)
seg = segs[num-1]
audio = d.get("source") or f"BabySongs/{short}.mp3"
if not os.path.exists(audio):
    print(f"  ⚠ 找不到原始音频 {audio}，跳过 {num}"); sys.exit(3)
out = f"song/{short}/{num:03d}.mp3"
cmd = ["ffmpeg","-y","-ss",str(seg["start"]),"-to",str(seg["end"]),
        "-i",audio,"-vn","-acodec","libmp3lame","-q:a","2",out]
r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if r.returncode != 0:
    print("  ⚠ ffmpeg 失败:", r.stderr.decode("utf-8","ignore")[:200]); sys.exit(3)
print(f"  ✓ {num} (从 _backup_ 原始段重切)")
PYEOF
    if [ $? -eq 0 ]; then ok=$((ok+1)); continue; fi
  fi
  echo "  ⚠ $num 在 BabySongs 和 _backup_ 都找不到，跳过（请手动提供该段起始/结束秒数后重切）"
  skip=$((skip+1))
done

echo ""
echo "▶ 仅暂存新增文件夹 song/$SHORT/（不碰其它）"
git add "song/$SHORT/"
echo "=== 暂存区（应只有 A 新增，绝无 D 删除）==="
git diff --cached --name-only
if git diff --cached --name-only | grep -q '^ D'; then
  echo "❌ 检测到删除项，终止以防误删远程歌曲。请人工检查。"; exit 1
fi

if [ "$ok" -eq 0 ]; then
  echo "❌ 没有任何歌曲成功放入，不提交。"; exit 1
fi

read -r -p "▶ 确认提交并推送以上文件？[y/N] " ans
if [ "${ans:-N}" != "y" ] && [ "${ans:-N}" != "Y" ]; then
  echo "已取消。文件已放入 $SONGDST，可稍后手动提交。"; exit 0
fi

git -c user.email="bot@workbuddy.local" -c user.name="WorkBuddy" \
  commit -m "add: $SHORT 精选 $ok 首 ($(printf '%03d ' "$@"))"
git push origin main
echo "✅ 已上传 $ok 首到 song/$SHORT/（跳过 $skip 首）"

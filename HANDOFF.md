# 接手手册（HANDOFF）· 新 AI / 新人一次跑通

> 这是给“下一次接手这个项目”的 AI 或人看的 runbook。按 **§0 → §6** 的顺序做，就能把一个视频从下载一路处理到上传，且不会踩我们已经踩过的坑。
> 详细的“现象 / 原因 / 解决”见 **[开发README.md](开发README.md)**；用户向介绍见 **[README.md](README.md)**；脚本参数见 **[SKILL.md](SKILL.md)**。

---

## §0 仓库与目标

- 仓库：`Simiely/babysongs-downloader`，分支 `main`。
- 干什么：下载 B 站 UP 主「宝贝中文」(UID 626735752) 的育儿儿歌视频 → AI 检测视频里**多首歌**的时间节点 → 按节点裁成独立 mp3 → 精选上传到 `song/<视频短名>/` 做备份。
- 远程 URL 已内嵌 PAT（`oauth2:<TOKEN>@github.com/...`），直接 `git push origin main` 即可。

**目录约定**
```
scripts/baby_songs_downloader.py   # 核心：detect / cut 两阶段
scripts/run_babysongs.bat         # Windows 一键（detect 阶段）
run_download.sh                    # Linux 一键：detect → 可选 cut
scripts/merge_segments.py         # 【新增】合并相邻两段歌 + 重算清单
scripts/upload_songs.sh            # 【新增】安全上传精选歌到 song/（防误删）
cookies/bilibili_cookies.txt      # B站登录态（gitignore，不入库）★
BabySongs/                        # 当前视频裁切产物（gitignore）★ 根目录只放“最新一个视频”
song/                            # 已上传精选（入库，做备份）★  song/<视频短名>/<编号>.mp3
_backup_/                         # merge 前的 segments 备份（gitignore）
```
★ = 受 `.gitignore` 保护 / 或刻意入库

---

## §1 一次性环境准备（只做一次）

```bash
# 1) Python 依赖——脚本跑在 python3.11 上，系统若有 3.12 + PEP668，必须这样装：
python3.11 -m pip install --break-system-packages yt-dlp librosa openai-whisper

# 2) ffmpeg 必须在 PATH（下载/裁切都靠它）
ffmpeg -version

# 3) B站 cookies（否则下载必报 HTTP 412）
#    从已登录 B站 的浏览器导出 cookies.txt（Netscape 格式），放到：
#      cookies/bilibili_cookies.txt
#    也可改用 --cookies-from-browser chrome（本机需登录过 B站）
```
> 环境坑详情见 开发README §1（Python 版本冲突）、§2（412）。

---

## §2 处理一个视频（detect → cut → 清单）

```bash
# 全自动：检测节点 + 直接裁切「宝贝中文」最新一个视频
./run_download.sh

# 指定视频 / 合集
./run_download.sh "<视频BV链接或合集链接>"

# 想先人工核对节点（推荐首次）：只检测 + 导出 LRC/SRT，核对后再 cut
./run_download.sh "<链接>" review
# 核对后裁切：
python3.11 scripts/baby_songs_downloader.py --cut "BabySongs/<xxx>_segments.json" -o BabySongs
```
产出在 `BabySongs/`：
- `<视频全名>.mp3` —— **原始长音频（务必保留，后续重切都从它来）**
- `<视频全名>_segments.json` —— 每段 `{start,end,duration}`，段 `i` ↔ `(i+1)` 三位编号 mp3
- `歌曲清单.md` —— 编号 ↔ 时间段 ↔ 文件名
- `001.mp3` … —— 独立歌曲（平铺在 `BabySongs/` 根）

> 多视频会互相覆盖 `001.mp3`：根目录永远只留“当前视频”，旧视频归档到 `BabySongs/<旧视频短名>/`（用 `printf '%03d'`，别用 `seq -w`）。见 开发README §3。

---

## §3 合并 / 编辑某两段歌（可选）

用户要“把 #28 和 #29 合并成一个 29，取 #29 前 26 秒”这类需求时用：

```bash
# a、b 是 0-based 下标（#28=a=27, #29=b=28）
# 默认 merged 沿用 #b 的编号，#a 被删（出现编号空洞，后续不动）
python3.11 scripts/merge_segments.py \
  --seg "BabySongs/<视频全名>_segments.json" \
  --a 27 --b 28 --take-b 26

# 若想合并段沿用 #a 的编号：加 --merged-num a
```
脚本会自动：备份旧 segments 到 `_backup_/` → 改 segments.json → 从**原始长音频** ffmpeg 重切合并段 → 删被吞的 mp3 → 重算 `歌曲清单.md`。
> **永远从原始长音频重切，不要 concat 小 mp3**（有接缝）。路径不要重复拼 `BabySongs/`。见 开发README §4、§6。

---

## §4 精选上传到 GitHub（用脚本，别手敲 git）

```bash
# 把 BabySongs/ 里指定编号的歌，上传到 song/<视频短名>/
./scripts/upload_songs.sh <视频短名> 005 012 014 023 025 028 030
```
脚本已固化**防误删流程**：
1. `git checkout -- song/` 先把本地镜像恢复到与远程一致（之前清理本地可能留下未提交的 `D`）；
2. 只 `git add song/<短名>/` 这一个【新增】文件夹，**绝不 `git add -A`**；
3. 打印暂存区，确认无 `D` 删除旧歌后才提交推送。

歌曲来源：优先拷 `BabySongs/<编号>.mp3`；若该编号已被合并掉且 `BabySongs/` 里没有，会尝试从 `_backup_/<短名>/segments.json` 原始段重切；都找不到则跳过并提示。
> 推送坑（最致命）见 开发README §7。

---

## §5 收尾 → 下一个视频

```bash
# 清理【当前视频】本地 mp3（保留：原始长音频 + 歌曲清单.md，供以后回溯/重切）
# 旧视频若还没归档，先归档：
mkdir -p BabySongs/<旧视频短名> && \
for i in $(seq 1 <旧视频歌曲数>); do mv "BabySongs/$(printf '%03d' $i).mp3" "BabySongs/<旧视频短名>/"; done

# 然后处理下一个视频：回到 §2
```
> 标准节奏：下载 N →（可选上传精选）→ 清理本地 → 下一个。

---

## §6 命令速查表

| 动作 | 命令 |
|------|------|
| 一键下载+裁切最新视频 | `./run_download.sh` |
| 只检测节点（人工核对） | `./run_download.sh "<链接>" review` |
| 核对后裁切 | `python3.11 scripts/baby_songs_downloader.py --cut "BabySongs/<x>_segments.json" -o BabySongs` |
| 合并相邻两段 | `python3.11 scripts/merge_segments.py --seg <seg.json> --a <i> --b <i+1> [--take-b 26] [--merged-num a\|b]` |
| 上传精选到 song/ | `./scripts/upload_songs.sh <短名> <编号...>` |
| 校验某 mp3 时长 | `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 <f>.mp3` |

---

## §7 最容易翻车的 3 件事（详情在 开发README）

1. **Python 报 `No module named 'librosa'`** → 装错解释器了，用 `python3.11 -m pip install --break-system-packages ...`（§1）。
2. **B 站下载 `HTTP 412`** → 缺 cookies，放 `cookies/bilibili_cookies.txt`（Netscape 格式）（§1）。
3. **`git add -A` 把远程已传歌曲删了** → 上传一律走 `./scripts/upload_songs.sh`，它只 add 新文件夹（§4 / 开发README §7）。

> 安全红线：`cookies/` 和 PAT 绝不进文档 / 提交；如 PAT 疑似泄露，立即到 GitHub 撤销重置。

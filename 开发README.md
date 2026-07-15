# 开发 README · 踩坑与关键问题记录

> 目的：把使用本项目过程中反复碰到、容易重蹈覆辙的坑集中记录，下次遇到同类问题直接查这一节。
> 面向维护者 / AI 代理。普通用法看 `README.md`，完整参数看 `SKILL.md`。
> **新接手想“一次跑通”**：直接看 [HANDOFF.md](HANDOFF.md)（按步骤 runbook，已含通用合并/上传脚本）。

---

## 目录

1. [Python 环境与依赖坑](#1-python-环境与依赖坑)
2. [B 站下载：HTTP 412 限流](#2-b-站下载http-412-限流)
3. [多视频文件碰撞 / 编号位数 bug](#3-多视频文件碰撞--编号位数-bug)
4. [ffmpeg 裁切：接缝与路径 double-prefix](#4-ffmpeg-裁切接缝与路径-double-prefix)
5. [segments.json 与 歌曲清单.md 维护](#5-segmentsjson-与-歌曲清单md-维护)
6. [合并 / 编辑歌曲段的标准做法](#6-合并--编辑歌曲段的标准做法)
7. [GitHub 推送坑（最容易误删已传歌曲）](#7-github-推送坑最容易误删已传歌曲)
8. [安全与敏感信息](#8-安全与敏感信息)

---

## 1. Python 环境与依赖坑

**现象**：`run_download.sh` 一跑就 `ImportError: No module named 'librosa'`，但明明装过。

**原因**：机器上有两套 Python——
- pyenv 装的 `python3.11.1`（脚本 `run_download.sh` 里 `PY=python3.11` 实际用的是它）
- 系统自带 `python3.12`

用 `sudo pip3 install librosa` 时，包装进了**系统 3.12**，而脚本跑在 pyenv 3.11 上 → 找不到。

**解决**：把依赖装进脚本用的那个解释器，且系统 Python 受 PEP 668 保护需 `--break-system-packages`：

```bash
python3.11 -m pip install --break-system-packages librosa
# yt-dlp / openai-whisper 同理，统一用 python3.11 -m pip
```

**教训**：
- 先确认脚本实际调用的解释器版本（`which python3.11` / `python3.11 --version`），再往同一个里面装包。
- 凡是 `pip install` 失败或装了找不到，先查“装进了哪个 Python”。

---

## 2. B 站下载：HTTP 412 限流

**现象**：`yt-dlp` 下载 B 站视频报 `HTTP Error 412`（请求被拒绝 / 风控），换了 UA、Referer、chromium cookies、`prefer_playurl_api` 都不行。

**原因**：B 站对**未登录**的请求限流，必须带登录态 cookies。

**解决（两选一）**：

```bash
# 方式 A（推荐，最稳）：用从已登录浏览器导出的 cookies.txt（Netscape 格式）
#   放到 cookies/bilibili_cookies.txt，脚本自动读取
python3.11 scripts/baby_songs_downloader.py --detect --cookies cookies/bilibili_cookies.txt --url "<链接>" -o BabySongs

# 方式 B：直接读本机浏览器登录态（本机需登录过 B 站）
python3.11 scripts/baby_songs_downloader.py --detect --cookies-from-browser chrome --url "<链接>" -o BabySongs
```

**注意**：`cookies/` 已在 `.gitignore`，**绝不可**手动 `git add` 进去——里面是登录态，泄露 = 账号风险。

---

## 3. 多视频文件碰撞 / 编号位数 bug

**现象**：处理完视频 A 再处理视频 B，发现视频 A 的歌被覆盖了；或归档旧视频时 `mv` 没匹配上任何文件。

**原因**：
- 所有视频默认都输出 `001.mp3` … 到同一个 `BabySongs/` 根目录，后一个视频直接覆盖前一个。
- 归档旧视频时曾用 `seq -w 1 48` 生成 `01.mp3`（**2 位**），但实际文件是 `001.mp3`（**3 位**）→ glob 匹配不上，旧文件没被移走、接着被新视频覆盖。

**约定与解决**：
- **目录约定**：最新视频平铺在 `BabySongs/` 根；处理完、确认上传后，把旧视频归档进 `BabySongs/<视频短名>/` 子文件夹，根目录只留“当前视频”。
- **编号一律 3 位**，用 `printf '%03d'`，不要 `seq -w`：
  ```bash
  # 正确：3 位
  for i in $(seq 1 48); do mv "BabySongs/$(printf '%03d' $i).mp3" "BabySongs/视频短名/"; done
  # 列/数当前歌曲时用三位数字 glob，避免误伤原始长音频（文件名以中文开头）
  ls BabySongs/[0-9][0-9][0-9].mp3
  ```

---

## 4. ffmpeg 裁切：接缝与路径 double-prefix

### 4.1 永远从“原始长音频”重切，勿 concat

**现象**：把几段 mp3 直接拼接（concat）出新歌，听起来有接缝 / 编码参数不一致。

**解决**：任何“重新裁一段歌 / 合并两段”的需求，**都从原始长音频重新 ffmpeg 裁切**，而不是拼已切好的小 mp3。脚本原生命令（两端都在 `-i` 前 = 绝对时间区间）：

```bash
ffmpeg -y -ss <start秒> -to <end秒> -i "<原始长音频>.mp3" -vn -acodec libmp3lame -q:a 2 "<输出>.mp3"
# 例：重切原版 #28（1761.7 ~ 1881.12）
ffmpeg -y -ss 1761.7 -to 1881.12 -i "BabySongs/新! 宝宝第一个词 _ 发音 & 手势 & 儿歌启蒙 - 宝贝中文.mp3" -vn -acodec libmp3lame -q:a 2 "song/宝宝第一个词/028.mp3"
```

### 4.2 路径 double-prefix bug（曾导致 AssertionError）

**现象**：写脚本批量按 `segments.json` 重切时报 `AssertionError: BabySongs/BabySongs/新!...mp3`（路径里 `BabySongs/` 出现了两次）。

**原因**：拼接音频路径时，`segf` 这个变量**已经包含** `BabySongs/` 前缀，又用 `os.path.join(base, segf.replace(...))` 再拼了一次 `base`，于是变成 `BabySongs/BabySongs/...`。

**解决**：`segf` 已是完整路径时，直接替换后缀即可，别再 `os.path.join`：

```python
# 错误
audio = os.path.join(base, segf.replace("_segments.json", ".mp3"))
# 正确（segf 已含 base 前缀）
audio = segf.replace("_segments.json", ".mp3")
```

---

## 5. segments.json 与 歌曲清单.md 维护

- `segments.json` 结构：
  ```json
  { "source": "<原始音频绝对路径>", "duration": 2164.14,
    "segments": [ {"start": 56.98, "end": 67.01, "duration": 10.03}, ... ] }
  ```
  - 段与 mp3 **1:1 对应**：第 `i` 段 → `(i+1)` 三位编号的 `.mp3`（如 index 0 → `001.mp3`）。
- `歌曲清单.md`：每视频一份，列「编号 ↔ 时间段(mm:ss) ↔ 时长 ↔ 文件名」。
- **校验任一裁切是否精确**：
  ```bash
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<文件>.mp3"
  # 应 ≈ segments.json 里该段的 duration
  ```

---

## 6. 合并 / 编辑歌曲段的标准做法

以「把 #28 + #29 合并为一个，命名 029，且只取 #29 前 26 秒」为例：

**数学**：
```
merged_start = #28.start                 # 1761.7
merged_end   = #29.start + 26.0         # 1882.81 + 26 = 1908.81
merged_dur   = merged_end - merged_start # 147.11
```

**步骤**：
1. 改 `segments.json`：删掉 #28、#29 两段，在对应位置插入一段 `{"start":1761.7,"end":1908.81,"duration":147.11}`。
2. 从**原始长音频** ffmpeg 重切到 `029.mp3`（命令见 4.1，**不要** concat）。
3. 删除旧的 `028.mp3`（`rm BabySongs/028.mp3`）。
4. 重算 `歌曲清单.md`：注意合并后**编号会出现“空洞”**——#28 没了、#29 是合并段、#30/#31 不变。

**提示**：合并后若用户又要“上传某首已不存在的歌”（如本例合并后又要传 028），从原始长音频**临时重切原版**用于上传，上传完即删临时文件，**不动**本地已合并的状态。

---

## 7. GitHub 推送坑（最容易误删已传歌曲）

**背景**：`song/` 目录是 GitHub 备份镜像，里面是按视频分文件夹的精选 mp3。`BabySongs/` 和 `cookies/` 被 `.gitignore` 排除，不进仓库。

**致命坑：`git add -A` / `git commit -a` 会误删远程已传歌曲**

**现象链**：之前“清理本地 mp3”时用 `rm` 删掉了工作区里的 `song/` 文件，但**没提交** → git 挂了一堆未暂存的 `D`（旧歌在远程还在，只是本地工作树没了）。此时若图省事 `git add -A`，会把远程已上传的旧歌也一起删掉。

**标准安全推送流程**：
```bash
# ① 先恢复 song/ 镜像到工作区，让本地与远程一致（不会动远程）
git checkout -- song/

# ② 只 add “本次新增”的视频文件夹，绝不全盘 add
git add "song/<视频短名>/"

# ③ 提交前复查暂存区：确认没有 D 删除旧歌、只有 A 新增
git diff --cached --name-only

# ④ 提交（仓库未设 user，用 -c 临时指定）
git -c user.email="bot@local" -c user.name="WorkBuddy" commit -m "add: <视频短名> 精选 N 首 (编号列表)"

# ⑤ 推送（远程 URL 已内嵌 PAT，见下）
git push origin main
```

**远程 / 鉴权**：
- 仓库：`https://github.com/Simiely/babysongs-downloader.git`，分支 `main`。
- 远程 URL 内嵌 PAT：`https://oauth2:<TOKEN>@github.com/Simiely/babysongs-downloader.git`（账号 = Simiely）。
- 若 `gh` 未登录、`get_token` 拿不到 OAuth token，最终用用户提供的 PAT（见第 8 节安全提醒）。

**当前 `.gitignore` 保护项**：
```
cookies/          # B站登录态，绝不入库
BabySongs/        # 大体积工作区，不入库
__pycache__/
*.pyc
_backup_*/
```

---

## 8. 安全与敏感信息

- **`cookies/bilibili_cookies.txt`**：含 B 站登录态，已在 `.gitignore`，**禁止** `git add`、禁止写进任何文档。
- **PAT（个人访问令牌）**：账号级凭证，**绝不**写进 README / 提交 / 聊天以外的地方。如怀疑泄露，立即到 GitHub → Settings → Developer settings → Personal access tokens 撤销重置。
- **`BabySongs/`**：每视频几十 MB 的 mp3 工作区，靠 `.gitignore` 避免把大文件推上仓库；它只作本地裁切暂存，长期备份走 `song/`。

---

## 附：标准工作节奏

```
下载视频 N（detect → 可选 review → cut，产出在 BabySongs/ 根）
   ↓
（可选）挑选若干首 → 放进 song/<视频短名>/ → 按第 7 节安全推送
   ↓
清理 BabySongs/ 根里的本地 mp3（保留：原始长音频 + 歌曲清单.md 供回溯）
   ↓
下一个视频
```

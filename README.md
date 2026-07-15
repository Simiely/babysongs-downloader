# 宝贝中文 · 儿歌下载与 AI 分段工具

> 把 B 站 UP 主「宝贝中文」(UID 626735752) 的育儿儿歌视频整段下载为音频，用 AI 检测视频里**多首歌曲**的时间节点，按节点裁切为独立 mp3，并可精选上传到仓库 `song/` 目录做版本化备份。

---

## 项目简介

「宝贝中文」的视频是**「解说 + 音乐」混合**——一个视频里含十几到几十首儿歌，中间穿插讲解。这类视频不能简单“去人声”（儿歌本身就是人唱的），本项目靠**伴奏能量**区分歌曲 / 解说，用 **OTSU 自适应阈值**定位每首歌的起止时间，再用 ffmpeg 逐段裁切成独立 mp3。

核心能力：

- 下载 B 站视频音频（需登录态，绕过 412 限流）
- AI 检测多首歌的时间节点，输出 `segments.json` + 可选 LRC/SRT 时间戳
- 按节点裁切为 `001.mp3` … 独立文件
- 每视频生成「歌曲清单.md」（编号 ↔ 时间戳 ↔ 文件名）
- 精选歌曲上传到 `song/<视频短名>/`，做长期备份

---

## 快速开始

### 1. 安装依赖（首次）

```bash
pip install yt-dlp librosa
# 可选：用歌词自动命名
pip install openai-whisper
```

- **ffmpeg**：下载 https://www.gyan.dev/ffmpeg/builds/ 并把 `bin` 加入 PATH
- **Python**：脚本按 `python3.11` 运行（环境坑见《开发 README》，注意 pyenv / 系统版本冲突）

### 2. 准备 B 站 cookies（关键）

B 站对未登录下载会返回 `HTTP 412` 限流。解决：从**已登录 B 站**的浏览器导出 `cookies.txt`（Netscape 格式），放到：

```
cookies/bilibili_cookies.txt
```

> 脚本会自动读这个路径；也可改用 `--cookies-from-browser chrome`。`cookies/` 已在 `.gitignore`，**不会**进仓库。

### 3. 一键下载 + 分段

```bash
# 全自动：检测节点 + 直接裁切「宝贝中文」最新一个视频
./run_download.sh

# 指定某个视频 / 合集
./run_download.sh "<视频BV链接或合集链接>"

# 只检测节点并导出 LRC/SRT，人工核对后再裁切
./run_download.sh "<链接>" review
```

产出在 `BabySongs/`：原始长音频、`*_segments.json`、`歌曲清单.md`、以及 `001.mp3` …

### 4. 挑选歌曲上传到仓库（可选）

把想长期保存的歌曲，按视频归类放进 `song/`：

```
song/<视频短名>/<编号>.mp3
# 例：song/宝宝第一个词/005.mp3
```

然后提交推送。**注意**：推送有坑，详见《开发 README》「GitHub 推送」一节，**不要** `git add -A`。

---

## 目录结构

```
babysongs-downloader/
├── scripts/baby_songs_downloader.py   # 核心脚本（detect / cut 两阶段）
├── run_download.sh                    # 一键运行（detect → cut）
├── SKILL.md                          # 技能说明（完整参数表 / AI 调用要点）
├── cookies/                          # B站 cookies（gitignore，不入库）        ★
├── BabySongs/                        # 当前视频裁切产物（gitignore）          ★
│   ├── 001.mp3 …                    #   独立歌曲
│   ├── *_segments.json              #   节点
│   └── 歌曲清单.md                  #   编号 ↔ 时间戳 ↔ 文件
└── song/                            # 已上传精选（入库，做备份）            ★
    └── <视频短名>/<编号>.mp3
```

★ = 受 `.gitignore` 保护 / 或刻意入库的目录

---

## 常见问题（简版）

| 现象 | 速查 |
|------|------|
| `HTTP 412` 下载被拒 | 缺 cookies → 见上文第 2 步 |
| detect 检出 0 首 / 误判 | 调 `--energy-ratio`（漏歌 `0.8` / 解说误判 `1.3`）|
| 裁切有接缝 | 永远从**原始长音频**重切，别 concat 多个 mp3 |

更完整的「踩坑记录 + 解决命令」见 **[开发README.md](开发README.md)**。

---

## 合规提醒

个人育儿离线使用，勿二次上传 / 贩卖；喜欢请去主页或音乐平台支持正版。

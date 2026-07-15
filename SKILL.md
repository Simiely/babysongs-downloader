---
name: babysongs-downloader
description: B站「宝贝中文」UP主歌曲下载与分段工具 - 下载视频音频，AI检测视频里多首歌曲的时间节点，按节点裁切为独立mp3并用歌词命名，支持 LRC/SRT 时间戳导出与一键自动裁切。当用户要下载宝贝中文/类似育儿儿歌UP主的视频并提取其中的歌曲片段、或要把"解说+音乐"混合视频裁成一首首独立儿歌时使用。
version: "1.1.0"
author: "Simiely"
created: "2026-07-15"
updated: "2026-07-15"
---

# 宝贝中文 歌曲下载 + AI 分段裁切器

把 B站 UP主「宝贝中文」(UID 626735752) 的视频整段下载为音频，并自动检测视频里**多首歌曲**的时间节点，按节点裁切为独立 mp3（可自动用歌词命名）。

> **背景**：该 UP主视频是「解说 + 音乐」混合，一个视频含多首儿歌。不能简单"去人声"（儿歌本身是人唱的），而是靠**伴奏能量**区分歌曲/解说，用 OTSU 自适应阈值定位歌曲段。

## 何时使用
- 用户要下载「宝贝中文」UP主的视频/歌曲
- 用户要提取视频里多首歌、裁剪成独立音频
- 关键词：宝贝中文、儿歌下载、B站歌曲提取、视频分段、去除解说只留歌曲

## 安装依赖（首次）
```bash
pip install yt-dlp librosa
# 可选：用歌词自动命名
pip install openai-whisper
```
- **ffmpeg**：下载 https://www.gyan.dev/ffmpeg/builds/ 并把 `bin` 加入 PATH
- **遇 B站 412 限流**：本机用 Chrome 登录过 B站，命令加 `--cookies-from-browser chrome`

## 工作流程（两阶段：先标节点、再裁切）
### 阶段1 detect：下载 + AI 标节点
```bash
python <skill-directory>/scripts/baby_songs_downloader.py --uid 626735752 --detect --cookies-from-browser chrome -o D:/BabySongs
# 指定某个视频
python <skill-directory>/scripts/baby_songs_downloader.py --detect --url "<视频URL>" -o D:/BabySongs
# 本地已有音频，直接标节点（跳过下载）
python <skill-directory>/scripts/baby_songs_downloader.py --detect --audio 本地.mp3 -o D:/BabySongs
# 导出 LRC/SRT 时间戳，边听边校对节点
python <skill-directory>/scripts/baby_songs_downloader.py --detect --url "<视频URL>" -o D:/BabySongs --lrc --srt
# 一键：检测后直接裁切（省事，仍产出 segments.json 供回看）
python <skill-directory>/scripts/baby_songs_downloader.py --detect --uid 626735752 --auto --cookies-from-browser chrome -o D:/BabySongs --whisper
```
输出 `D:/BabySongs/xxx_segments.json`（每首歌 start/end），终端打印时间轴；`--lrc/--srt` 额外生成时间戳文件。

### 阶段2 人工审阅（重要，使用 --auto 可跳过）
打开 `xxx_segments.json`（或对照 LRC/SRT），核对每首歌起止时间，不准就手动改数值。

### 阶段3 cut：裁切 + 命名
```bash
python <skill-directory>/scripts/baby_songs_downloader.py --cut "D:/BabySongs/xxx_segments.json" -o D:/BabySongs --whisper
```
按节点用 ffmpeg 逐段裁切，每首独立 mp3；`--whisper` 用前 15 秒歌词自动命名（失败回退序号 `001.mp3`）。

## 参数
| 参数 | 说明 |
|------|------|
| `--uid` | UP主 UID，如 `626735752` |
| `--url` | 指定视频/合集/空间 URL |
| `--audio` | detect 直接用本地音频（跳过下载） |
| `--detect` | 检测歌曲时间节点 → 输出 `segments.json` |
| `--cut` | `segments.json` 路径，按节点裁切 |
| `-o/--output` | 输出目录 |
| `--min-duration` | detect 最短歌曲段秒数（默认 8） |
| `--merge-gap` | detect 段间合并间隙秒数（默认 1.5） |
| `--energy-ratio` | detect 能量阈值倍数（默认 1.0，越大越严格） |
| `--lrc` | detect 同时导出 LRC 时间戳（边听边校对节点） |
| `--srt` | detect 同时导出 SRT 时间戳 |
| `--auto` | detect 后跳过人工审阅直接裁切（仍生成 segments.json） |
| `--whisper` | cut 时用 Whisper 歌词命名 |
| `--cookies` | cookies.txt 路径 |
| `--cookies-from-browser` | 浏览器名，如 `chrome` / `edge` |
| `--limit` | 下载模式：最多几个 |
| `--list` | 只列出视频 |
| `--json` | JSON 输出（便于 AI 解析） |

## AI 调用要点
- 脚本支持 `--json` 结构化输出 + 明确退出码（0 成功 / 1 部分失败 / 2 环境错误），AI 可直接调用并解析结果。
- 建议流程：先 `--detect --lrc --srt` 拿到节点与时间戳，把节点读给用户核对，确认后再 `--cut`（或首次就用 `--auto` 直接出歌）。
- 若 `--detect` 检出 0 首或误判，调 `--energy-ratio`（解说也响→`1.3` 更严；歌曲被漏→`0.8` 更松）。

## 错误处理
| 现象 | 原因 | 解决 |
|------|------|------|
| `HTTP Error 412` | B站风控/未登录 | 加 `--cookies-from-browser chrome`（本机需登录过 B站） |
| detect 检出 0 首 | 阈值不适 | 调 `--energy-ratio` 到 `0.8` |
| 解说被误判成歌 | 阈值过松 | 调 `--energy-ratio` 到 `1.3` |
| 裁切段时长偏差 | 帧边界 | 脚本已用重新编码保证精确，无需处理 |

## 合规提醒
个人育儿离线使用，勿二次上传/贩卖；喜欢请去主页或音乐平台支持正版。

## 一键（Windows）
双击 `<skill-directory>/scripts/run_babysongs.bat` 即执行 detect 阶段并提示后续 cut 命令。

@echo off
chcp 65001 >nul
echo ============================================
echo   宝贝中文 歌曲下载 + AI 标节点
echo ============================================
echo 前置条件：
echo   1. pip install yt-dlp librosa
echo   2. ffmpeg 已加入 PATH (https://www.gyan.dev/ffmpeg/builds/)
echo   3. 本机用 Chrome 登录过 B站 (绕过 412 限流)
echo.
echo 本脚本会：下载该 UP 主最新视频音频，并用 AI 标出每首歌的时间节点
echo 节点保存在 BabySongs\ 下的 *_segments.json，请先审阅/微调再裁切
echo.
python "%~dp0baby_songs_downloader.py" --uid 626735752 --detect --cookies-from-browser chrome -o "%~dp0BabySongs"
echo.
echo ============================================
echo 下一步：打开上面生成的 *_segments.json 审阅每首歌起止时间
echo 确认后运行裁切（自动按歌词命名）：
echo   python "%~dp0baby_songs_downloader.py" --cut "BabySongs\<视频名>_segments.json" -o "%~dp0BabySongs" --whisper
echo ============================================
pause >nul

# floatsub

听某一个应用正在播放的声音，译成选定的语言，显示在一条可以拖动的置顶字幕上。不进浏览器，也不抓整台电脑的声音。

## 准备

1. 复制环境文件：

```powershell
Copy-Item .env.example .env
```

2. 用编辑器打开 `.env`。Gemini 的 Key 填到 `GEMINI_API_KEY=`，千问的 Key 填到 `DASHSCOPE_API_KEY=`。不要加引号。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

窗口会一直留在最前面。按住「floatsub」或字幕可以拖动。

1. 先让目标应用出声，例如打开 YouTube 并播放。
2. 点「刷新」，选中那个应用。同名进程会收成一个，并连同它的子进程一起听。
3. 选 Gemini 或千问，再点「开始听」。

上面是译文，下面是听到的原文。听到和译成都可以选日语、英语、韩语、中文。

Gemini 和千问都把声音直接送进实时翻译，字幕跟着说话走。「译成」是目标语言。两个模型都会自己判断听到的语言。千问的模型是 qwen3.8-livetranslate-flash-realtime，只取文字，不播译出的声音。

加密播放的声音抓出来是静音，这种应用译不了。YouTube 网页一般可以。

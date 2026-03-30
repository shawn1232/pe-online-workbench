PE Agent Live Demo · Quickstart
================================

1) Start the local server
-------------------------
Windows:
  double-click start_server.bat

macOS / Linux:
  python3 app.py

2) Open the workbench
---------------------
After the server starts, open:
  http://127.0.0.1:8765/

3) Save your API Key once
-------------------------
Click "设置 API Key" and save your OpenAI API key.
The key is stored locally on this computer in:
  local_config.json

4) Run a live search
--------------------
Click "今日全量搜索".
The system will use today's public information to generate:
- sector mapping
- unlisted candidate pool
- horizontal comparison and exclusion logic
- explainable scores
- final recommendation

5) Demo mode
------------
If live search is unavailable, you can use:
- "读取上次成功结果"
- "载入演示样例"

Important
---------
This package is for local demo use.
For production, do NOT keep API keys in local files or browser code.
Use a secure server-side proxy instead.

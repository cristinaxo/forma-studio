"""Open the studio and keep its local server in this terminal."""
from pathlib import Path
import json, os, sys, threading, time, urllib.request, webbrowser
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
URL = 'http://127.0.0.1:8765'
try:
    with urllib.request.urlopen(URL + '/api/status', timeout=2) as response:
        status = json.load(response)
    if status.get('mode') == 'local' and status.get('version') == '0.1.0':
        webbrowser.open(URL)
        print('Forma is already running at ' + URL)
        raise SystemExit(0)
except (OSError, ValueError):
    pass

def open_when_ready():
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + '/api/status', timeout=1).close()
            webbrowser.open(URL)
            return
        except OSError:
            time.sleep(.5)

threading.Thread(target=open_when_ready, daemon=True).start()
print('Forma — local audio studio\nKeep this window open. Press Control-C here to stop.\n')
import uvicorn
uvicorn.run('server:app', host='127.0.0.1', port=8765, log_level='warning')

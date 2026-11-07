"""Run the local app using existing model artifacts. No training is performed."""
import os, socket, threading, time, webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
from prepare import prepare
if not prepare():raise SystemExit(2)
from backend.app import ACCESS_CODE,app
import uvicorn

if __name__=='__main__':
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',8000))==0:
            raise SystemExit('Port 8000 is in use. Close the existing server first; setup will not kill other processes.')
    print('\nHLB FLOW — LOCAL SYNTHETIC DEMO')
    print('Demo access code: '+ACCESS_CODE)
    print('Storefront: http://127.0.0.1:8000/')
    print('Bank dashboard: http://127.0.0.1:8000/bank')
    print('Chrome extension: enable Developer mode at chrome://extensions, Load unpacked -> '+str(ROOT/'extension'))
    print('All payments are simulated. Press Ctrl+C to stop.\n',flush=True)
    if not os.environ.get('FLOW_NO_BROWSER'):
        def open_browser():
            time.sleep(1.5)
            webbrowser.open('http://127.0.0.1:8000/')
            webbrowser.open('http://127.0.0.1:8000/bank')
        threading.Thread(target=open_browser,daemon=True).start()
    uvicorn.run(app,host='127.0.0.1',port=8000,log_level='warning')

"""Isolated demo benchmark; consumes the Colab artifact, never trains."""
import os,tempfile,time,json,platform,statistics
from pathlib import Path
os.environ['FLOW_RUNTIME']=tempfile.mkdtemp(prefix='flow-benchmark-');os.environ['FLOW_ACCESS_CODE']='benchmark-only'
from fastapi.testclient import TestClient
from backend.app import app,ENGINE
client=TestClient(app)
token=client.post('/api/login',json={'code':'benchmark-only','role':'customer','persona':'gig'}).json()['token']
h={'Authorization':'Bearer '+token}
def run(i):
    o=client.post('/api/orders',headers=h,json={'sku':'phone'}).json()
    co=client.post('/api/consents',headers=h,json={'order_id':o['id'],'granted':True}).json()
    start=time.perf_counter()
    r=client.post('/api/applications',headers={**h,'Idempotency-Key':f'bench-{i}'},json={'order_id':o['id'],'order_version':1,'consent_id':co['id'],'principal_vnd':6000000,'tenure_months':6})
    assert r.status_code==200,r.text
    return (time.perf_counter()-start)*1000,r.json()['latency_ms'],r.json()['outcome']
run(-1)
result=[run(i) for i in range(30)]
def summary(values):
    s=sorted(values);return {'mean_ms':statistics.mean(s),'p95_ms':s[int(.95*len(s))-1],'max_ms':max(s)}
report={'environment':platform.platform(),'python':platform.python_version(),'n':30,'population':'Identical synthetic gig persona, new VND6m/6-month mock order per request; separate disposable test database','api_round_trip':summary([x[0] for x in result]),'backend_decision':summary([x[1] for x in result]),'outcomes':{k:sum(x[2]==k for x in result) for k in set(x[2] for x in result)},'model_version':ENGINE.manifest['version'],'note':'Warm local TestClient measurements include actual inference and policy; no real external provider latency, network or production cost measured.'}
path=Path(__file__).resolve().parents[1]/'reports/performance.json';path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

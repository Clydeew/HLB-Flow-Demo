"""Local synthetic demo API. All credit and transaction state is server-owned."""
from pathlib import Path
from contextlib import contextmanager
from typing import Literal
import datetime as dt, hashlib, json, os, secrets, sqlite3, threading, time, uuid
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from backend.engine import ROOT, RiskEngine, schedule, affordability

RUNTIME=Path(os.environ.get('FLOW_RUNTIME',str(ROOT/'runtime'))); RUNTIME.mkdir(exist_ok=True)
DB=RUNTIME/'flow.sqlite'; LOCK=threading.RLock()
ACCESS_FILE=RUNTIME/'access_code.txt'
if not ACCESS_FILE.exists(): ACCESS_FILE.write_text(secrets.token_urlsafe(9)); ACCESS_FILE.chmod(0o600)
ACCESS_CODE=os.environ.get('FLOW_ACCESS_CODE',ACCESS_FILE.read_text().strip())
ENGINE=RiskEngine()
app=FastAPI(title='HLB Flow — synthetic demo',version='1.0')
app.add_middleware(CORSMiddleware,allow_origin_regex=r'^(chrome-extension://[a-p]{32}|http://(localhost|127\.0\.0\.1):8000)$',allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type','Idempotency-Key'])

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def uid(prefix): return prefix+'-'+uuid.uuid4().hex[:12].upper()
def error(code,status=400): raise HTTPException(status_code=status,detail=code)

@contextmanager
def transaction():
    with LOCK:
        c=sqlite3.connect(DB,timeout=15)
        c.execute('PRAGMA foreign_keys=ON'); c.execute('BEGIN IMMEDIATE')
        try: yield c; c.commit()
        except: c.rollback(); raise
        finally: c.close()

def put(c,kind,id,data): c.execute('INSERT INTO documents(kind,id,data) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',(kind,id,json.dumps(data)))
def get(c,kind,id):
    r=c.execute('SELECT data FROM documents WHERE kind=? AND id=?',(kind,id)).fetchone()
    return json.loads(r[0]) if r else None
def items(c,kind): return [json.loads(r[0]) for r in c.execute('SELECT data FROM documents WHERE kind=? ORDER BY rowid DESC',(kind,))]
def event(c,a,kind,metadata=None,actor='system'):
    e={'id':uid('EVT'),'application_id':a.get('id'),'run_id':a.get('run_id'),'type':kind,'at':now(),'actor':actor,'metadata':metadata or {}}
    put(c,'event',e['id'],e)

with transaction() as c:
    c.execute('CREATE TABLE IF NOT EXISTS documents (kind TEXT,id TEXT,data TEXT,PRIMARY KEY(kind,id))')
    if not get(c,'settings','current'): put(c,'settings','current',{'run_id':uid('RUN'),'fault':'none','persona':'gig'})

class Strict(BaseModel): model_config=ConfigDict(extra='forbid')
class Login(Strict):
    code:str
    role:Literal['customer','officer','presenter','observer']='customer'
    persona:Literal['gig','salaried','merchant','thin']='gig'

def auth(authorization:str|None=Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '): error('AUTH_REQUIRED',401)
    token=authorization[7:]
    with transaction() as c: s=get(c,'session',hashlib.sha256(token.encode()).hexdigest())
    if not s or s['expires_at']<time.time(): error('SESSION_EXPIRED',401)
    return s
def require(s,*roles):
    if s['role'] not in roles: error('FORBIDDEN',403)
def own(s,a):
    if not a: error('NOT_FOUND',404)
    if s['role']=='customer' and a['customer_id']!=s['customer_id']: error('FORBIDDEN',403)
def current(c): return get(c,'settings','current')

@app.middleware('http')
async def security(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.headers.get('origin'):
        origin=request.headers['origin']
        if not (origin in ['http://127.0.0.1:8000','http://localhost:8000'] or origin.startswith('chrome-extension://')):
            return JSONResponse({'detail':'ORIGIN_NOT_ALLOWED'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    return response

LOGIN_ATTEMPTS={}
@app.post('/api/login')
def login(body:Login,request:Request):
    host=request.client.host if request.client else 'local'; t=time.time()
    LOGIN_ATTEMPTS[host]=[x for x in LOGIN_ATTEMPTS.get(host,[]) if t-x<60]
    if len(LOGIN_ATTEMPTS[host])>=20: error('TOO_MANY_ATTEMPTS',429)
    if not secrets.compare_digest(body.code,ACCESS_CODE): LOGIN_ATTEMPTS[host].append(t); error('INVALID_DEMO_ACCESS_CODE',401)
    token=secrets.token_urlsafe(32)
    s={'role':body.role,'customer_id':body.persona,'expires_at':t+8*3600,'created_at':now()}
    with transaction() as c: put(c,'session',hashlib.sha256(token.encode()).hexdigest(),s)
    return {'token':token,**s,'demo':True}

@app.get('/api/health')
def health(): return {'ready':not ENGINE.error,'model_error':ENGINE.error,'model_version':ENGINE.manifest.get('version'),'mode':'synthetic-local-demo','training_environment':ENGINE.provenance.get('execution_environment')}

@app.get('/api/personas')
def personas(s=Depends(auth)):
    return [{'key':p['key'],'name':p['name'],'segment':p['row']['customer_profile'],'source_applicant_id':p['row']['applicant_id']} for p in ENGINE.personas]

class OrderRequest(Strict): sku:Literal['phone','laptop','headphones']='phone'
CATALOG={'phone':{'name':'Nova Phone 12','price_vnd':6_000_000,'category':'Smartphone'},'laptop':{'name':'StudioBook Air','price_vnd':12_000_000,'category':'Laptop'},'headphones':{'name':'Soundform Pro','price_vnd':2_400_000,'category':'Audio'}}
@app.get('/api/catalog')
def catalog(): return CATALOG
@app.post('/api/orders')
def create_order(body:OrderRequest,s=Depends(auth)):
    require(s,'customer'); o={'id':uid('ORDER'),'customer_id':s['customer_id'],'merchant_id':'NOVA-DEMO','sku':body.sku,**CATALOG[body.sku],'version':1,'status':'OPEN','currency':'VND','created_at':now()}
    with transaction() as c: put(c,'order',o['id'],o)
    return o
@app.get('/api/orders/{id}')
def order(id:str,s=Depends(auth)):
    with transaction() as c: o=get(c,'order',id)
    own(s,o); return o

class ConsentRequest(Strict): order_id:str; text_version:str='consent-v1'; granted:bool
@app.post('/api/consents')
def consent(body:ConsentRequest,s=Depends(auth)):
    require(s,'customer')
    if not body.granted: error('CONSENT_REQUIRED')
    with transaction() as c:
        o=get(c,'order',body.order_id); own(s,o)
        co={'id':uid('CONSENT'),'customer_id':s['customer_id'],'order_id':o['id'],'order_version':o['version'],'version':body.text_version,'granted_at':now(),'withdrawn':False}
        put(c,'consent',co['id'],co)
    return co

class ApplicationRequest(Strict):
    order_id:str; order_version:int; consent_id:str
    principal_vnd:int=Field(ge=1_600_000,le=15_000_000)
    down_payment_vnd:int=Field(default=0,ge=0)
    tenure_months:Literal[3,6,9,12]=6

def add_stage(c,a,name,state='complete',detail=None):
    a['stages'].append({'name':name,'state':state,'detail':detail,'at':now()}); event(c,a,name,{'state':state,'detail':detail})
def refer(c,a,reason,outcome='REFERRED'):
    a['outcome']=outcome; a['reason_codes']=[reason]
    if outcome in ['REFERRED','PENDING_DEPENDENCY','BLOCKED']:
        case={'id':uid('REVIEW'),'application_id':a['id'],'run_id':a['run_id'],'status':'OPEN','reason':reason,'created_at':now(),'history':[]}
        put(c,'review',case['id'],case); a['review_case_id']=case['id']; event(c,a,'review_created',{'reason':reason})

def evaluate(c,a,p,fix=False):
    start=time.perf_counter(); fault=a['fault'] if not fix else 'none'
    a['stages']=[]; a['model']=None; a['offer']=None; a['affordability']=None
    a['evidence']={'source':'Supplied synthetic workbook + supplemental demo fixture','observable':bool(p['row']['has_observable_tx']),'identity':'verified','fetched_at':now(),'source_applicant_id':p['row']['applicant_id']}
    add_stage(c,a,'Order verified',detail='Server-owned price, merchant and order version')
    if fault=='identity':
        a['evidence']['identity']='mismatch'; add_stage(c,a,'Identity check','blocked','Simulated identity mismatch'); refer(c,a,'IDENTITY_UNRESOLVED','BLOCKED')
    elif fault in ['missing_data','api_outage'] or not a['evidence']['observable']:
        a['evidence']['observable']=False; add_stage(c,a,'Financial evidence','unavailable','Transaction source unavailable; scoring skipped')
        refer(c,a,'FINANCIAL_EVIDENCE_UNAVAILABLE','PENDING_DEPENDENCY' if fault=='api_outage' else 'REFERRED')
    elif fault=='model_outage' or ENGINE.error:
        add_stage(c,a,'Model readiness','unavailable','Model bundle unavailable'); refer(c,a,'MODEL_UNAVAILABLE','PENDING_DEPENDENCY')
    else:
        add_stage(c,a,'Identity verified'); add_stage(c,a,'Financial evidence verified',detail='Synthetic pre-application fixture')
        row=dict(p['row']); row['requested_loan_vnd']=a['principal_vnd']; row['loan_tenure_months']=a['tenure_months']
        a['feature_snapshot']={k:row[k] for k in ['has_formal_cic_history','monthly_inflow_vnd','inflow_cv','casa_balance_vnd','dti_ratio','on_time_bill_ratio','e_wallet_topups_pm','regular_weekly_pattern','rapid_drain_flag','requested_loan_vnd','loan_tenure_months']}
        try:
            a['model']=ENGINE.score(row); add_stage(c,a,'LightGBM inference',detail='Live Colab-trained model; raw-margin contributions reconstructed')
            terms=schedule(a['principal_vnd'],a['tenure_months'])
            a['affordability']=affordability(row,terms,fault=='unaffordable')
            add_stage(c,a,'Affordability evaluated',detail='20% net-income stress; 40% DTI ceiling and VND1m residual floor')
            risk=a['model']['risk']; thresholds=ENGINE.manifest['thresholds']
            if not a['affordability']['passes']:
                refer(c,a,'AFFORDABILITY_INSUFFICIENT','DECLINED')
            elif risk>=thresholds['decline_at_or_above']: refer(c,a,'SIMULATED_RISK_ABOVE_DEMO_POLICY','DECLINED')
            elif risk>=thresholds['approve_below']: refer(c,a,'RISK_REQUIRES_REVIEW')
            else:
                a['outcome']='APPROVED'; a['reason_codes']=['VERIFIED_EVIDENCE','AFFORDABILITY_PASSED','WITHIN_DEMO_RISK_BAND']
                a['offer']={'id':uid('OFFER'),**terms,'expires_at':time.time()+600,'status':'ISSUED','order_version':a['order_version'],'evidence_at':time.time(),'terms_version':'terms-v1'}
                event(c,a,'offer_issued',{'offer_id':a['offer']['id']})
        except Exception as exc:
            add_stage(c,a,'Model evaluation','unavailable',type(exc).__name__); refer(c,a,'MODEL_EVALUATION_FAILED','PENDING_DEPENDENCY')
    a['status']='DECIDED' if a['outcome'] in ['APPROVED','DECLINED','REFERRED'] else a['outcome']
    a['latency_ms']=round((time.perf_counter()-start)*1000,2); a['decided_at']=now()
    event(c,a,'decision_saved',{'outcome':a['outcome'],'policy':'demo-policy-v1','latency_ms':a['latency_ms']})

@app.post('/api/applications')
def apply(body:ApplicationRequest,s=Depends(auth),idempotency_key:str=Header(alias='Idempotency-Key')):
    require(s,'customer'); payload=body.model_dump(); digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(); key=s['customer_id']+':'+idempotency_key
    with transaction() as c:
        old=get(c,'idempotency',key)
        if old:
            if old['digest']!=digest: error('IDEMPOTENCY_CONFLICT',409)
            return safe(get(c,'application',old['id']),s)
        o=get(c,'order',body.order_id); own(s,o)
        if o['status']!='OPEN': error('ORDER_NOT_OPEN',409)
        if o['version']!=body.order_version: error('ORDER_CHANGED',409)
        if o['price_vnd']!=body.principal_vnd+body.down_payment_vnd: error('AMOUNT_MISMATCH',409)
        co=get(c,'consent',body.consent_id)
        if not co or co['customer_id']!=s['customer_id'] or co['order_id']!=o['id'] or co['order_version']!=o['version'] or co['withdrawn']: error('CONSENT_REQUIRED')
        # Only one active offer per order. Re-evaluation requires invalidation, never parallel liabilities.
        for prev in items(c,'application'):
            if prev['order_id']==o['id'] and prev.get('offer') and prev['offer']['status'] in ['ISSUED','ACCEPTED']:
                prev['offer']['status']='INVALIDATED'; put(c,'application',prev['id'],prev); event(c,prev,'offer_invalidated',{'reason':'NEW_APPLICATION'})
        settings=current(c); p=next((x for x in ENGINE.personas if x['key']==s['customer_id']),None)
        if not p: error('MODEL_PERSONAS_UNAVAILABLE',503)
        a={'id':uid('APP'),'customer_id':s['customer_id'],'customer_name':p['name'],'segment':p['row']['customer_profile'],**payload,
          'run_id':settings['run_id'],'fault':settings['fault'],'created_at':now(),'status':'SUBMITTED','payment':None,'policy_version':'demo-policy-v1'}
        event(c,a,'application_submitted',{'principal_vnd':body.principal_vnd})
        evaluate(c,a,p); put(c,'application',a['id'],a); put(c,'idempotency',key,{'digest':digest,'id':a['id']})
        return safe(a,s)

def safe(a,s):
    if not a:return a
    a=json.loads(json.dumps(a))
    if s['role']=='customer':
        a.pop('feature_snapshot',None); a.pop('fault',None)
        # Model explanation exposes model signals, never internal identity/fraud heuristics.
    return a

@app.get('/api/applications')
def applications(s=Depends(auth)):
    with transaction() as c: data=items(c,'application')
    return [safe(a,s) for a in data if s['role']!='customer' or a['customer_id']==s['customer_id']]
@app.get('/api/applications/{id}')
def application(id:str,s=Depends(auth)):
    with transaction() as c: a=get(c,'application',id)
    own(s,a); return safe(a,s)

@app.post('/api/consents/{id}/withdraw')
def withdraw(id:str,s=Depends(auth)):
    require(s,'customer')
    with transaction() as c:
        co=get(c,'consent',id); own(s,co); co['withdrawn']=True; put(c,'consent',id,co)
        for a in items(c,'application'):
            if a['consent_id']==id:
                if a.get('offer') and a['offer']['status']!='CONSUMED': a['offer']['status']='WITHDRAWN'
                put(c,'application',a['id'],a); event(c,a,'consent_withdrawn')
    return {'withdrawn':True}

def live_offer(c,a,s):
    own(s,a); require(s,'customer'); offer=a.get('offer'); co=get(c,'consent',a['consent_id']); o=get(c,'order',a['order_id'])
    if not offer or a['outcome']!='APPROVED': error('NO_APPROVED_OFFER',409)
    if not co or co['withdrawn']: error('CONSENT_REQUIRED',409)
    if offer['expires_at']<time.time(): error('OFFER_EXPIRED',409)
    if offer['status'] not in ['ISSUED','ACCEPTED']: error('INVALID_OFFER_STATE',409)
    if offer['order_version']!=o['version'] or a['principal_vnd']+a['down_payment_vnd']!=o['price_vnd']: error('ORDER_CHANGED',409)
    if time.time()-offer['evidence_at']>900: error('EVIDENCE_EXPIRED',409)
    return offer,o

@app.post('/api/applications/{id}/accept')
def accept(id:str,s=Depends(auth)):
    with transaction() as c:
        a=get(c,'application',id); off,o=live_offer(c,a,s)
        if o['status']!='OPEN':error('ORDER_NOT_OPEN',409)
        off['status']='ACCEPTED'; off['accepted_at']=now(); a['offer']=off
        put(c,'application',id,a); event(c,a,'offer_accepted',{'offer_id':off['id'],'terms_version':off['terms_version']},'customer')
    return safe(a,s)

@app.post('/api/applications/{id}/challenge')
def challenge(id:str,s=Depends(auth)):
    with transaction() as c:
        a=get(c,'application',id); off,o=live_offer(c,a,s)
        if off['status']!='ACCEPTED': error('ACCEPT_TERMS_FIRST',409)
        code=str(secrets.randbelow(900000)+100000); ch={'id':uid('CHALLENGE'),'application_id':id,'offer_id':off['id'],'code_hash':hashlib.sha256(code.encode()).hexdigest(),'expires_at':time.time()+120,'attempts':0,'used':False}
        put(c,'challenge',ch['id'],ch)
    return {'id':ch['id'],'demo_code':code,'expires_in':120,'label':'Synthetic authentication code — no SMS sent'}

class PayRequest(Strict): challenge_id:str; code:str
@app.post('/api/applications/{id}/pay')
def pay(id:str,body:PayRequest,s=Depends(auth),idempotency_key:str=Header(alias='Idempotency-Key')):
    require(s,'customer'); failure=None
    with transaction() as c:
        a=get(c,'application',id); own(s,a)
        digest=hashlib.sha256(json.dumps(body.model_dump(),sort_keys=True).encode()).hexdigest()
        key=s['customer_id']+':PAY:'+idempotency_key
        prior=get(c,'idempotency',key)
        if prior:
            if prior['digest']!=digest or prior['id']!=id: error('IDEMPOTENCY_CONFLICT',409)
            return safe(a,s)
        if a.get('payment') and a['payment']['status'] in ['CAPTURED','UNKNOWN','REFUNDED']: error('PAYMENT_ALREADY_EXISTS',409)
        off,o=live_offer(c,a,s)
        if o['status']!='OPEN' or off['status']!='ACCEPTED': error('INVALID_PAYMENT_STATE',409)
        ch=get(c,'challenge',body.challenge_id)
        if not ch or ch['application_id']!=id or ch['offer_id']!=off['id'] or ch['used'] or ch['expires_at']<time.time() or ch['attempts']>=5: error('CHALLENGE_INVALID',409)
        ch['attempts']+=1
        if not secrets.compare_digest(ch['code_hash'],hashlib.sha256(body.code.encode()).hexdigest()):
            put(c,'challenge',ch['id'],ch); failure='AUTHENTICATION_CODE_INCORRECT'
        else:
            ch['used']=True; put(c,'challenge',ch['id'],ch)
            p={'id':uid('PAY'),'reference':uid('SIM'),'amount_vnd':a['principal_vnd'],'currency':'VND','status':'AUTHORISING','created_at':now(),'simulation':True}
            a['payment']=p; event(c,a,'payment_authorising',{'reference':p['reference']})
            fault=current(c)['fault']
            if fault=='payment_fail':
                p['status']='FAILED'; event(c,a,'payment_failed'); off['status']='ISSUED'
            elif fault=='payment_unknown':
                p['status']='UNKNOWN'; o['status']='PAYMENT_PENDING'; event(c,a,'payment_unknown')
            else: capture(c,a,o)
            put(c,'application',id,a); put(c,'order',o['id'],o); put(c,'idempotency',key,{'digest':digest,'id':id})
    if failure:error(failure,401)
    return safe(a,s)

def capture(c,a,o):
    if o['status']=='CONFIRMED' or a['payment']['status']=='CAPTURED': return
    a['payment']['status']='CAPTURED'; a['payment']['captured_at']=now(); a['offer']['status']='CONSUMED'
    a['loan']={'id':uid('LOAN'),'status':'ACTIVE','principal_vnd':a['principal_vnd'],'payment_id':a['payment']['id'],'created_at':now()}
    o['status']='CONFIRMED'; event(c,a,'payment_captured',{'reference':a['payment']['reference']}); event(c,a,'loan_activated',{'loan_id':a['loan']['id']})

@app.post('/api/applications/{id}/reconcile')
def reconcile(id:str,s=Depends(auth)):
    with transaction() as c:
        a=get(c,'application',id); own(s,a)
        if not a.get('payment') or a['payment']['status']!='UNKNOWN':error('NO_UNKNOWN_PAYMENT',409)
        # Deterministic simulator lookup of the original reference; never makes another charge.
        o=get(c,'order',a['order_id']); capture(c,a,o); put(c,'order',o['id'],o); put(c,'application',id,a); event(c,a,'payment_reconciled')
    return safe(a,s)

@app.post('/api/applications/{id}/refund')
def refund(id:str,s=Depends(auth)):
    require(s,'presenter','officer')
    with transaction() as c:
        a=get(c,'application',id); own(s,a)
        if not a.get('payment') or a['payment']['status']!='CAPTURED':error('NO_CAPTURED_PAYMENT',409)
        a['payment']['status']='REFUNDED'; a['loan']['status']='CANCELLED'; a['loan']['reversal_at']=now()
        o=get(c,'order',a['order_id']); o['status']='REFUNDED'; put(c,'order',o['id'],o); put(c,'application',id,a); event(c,a,'refund_completed',{'amount_vnd':a['principal_vnd']},s['role'])
    return a

@app.get('/api/reviews')
def reviews(s=Depends(auth)):
    require(s,'officer','presenter','observer')
    with transaction() as c:return items(c,'review')
class ReviewRequest(Strict): note:str=Field(min_length=5,max_length=2000); evidence_recovered:bool=False
@app.post('/api/reviews/{id}/resolve')
def review(id:str,body:ReviewRequest,s=Depends(auth)):
    require(s,'officer')
    with transaction() as c:
        case=get(c,'review',id)
        if not case or case['status']!='OPEN':error('REVIEW_NOT_OPEN',409)
        a=get(c,'application',case['application_id'])
        if a['fault'] in ['identity','model_outage'] and current(c)['fault']!='none':error('MANDATORY_GATE_UNRESOLVED',409)
        if not body.evidence_recovered:error('VERIFIED_EVIDENCE_REQUIRED',409)
        if current(c)['fault']!='none':error('UPSTREAM_FAULT_STILL_ACTIVE',409)
        co=get(c,'consent',a['consent_id']); o=get(c,'order',a['order_id'])
        if co['withdrawn'] or o['version']!=a['order_version']:error('APPLICATION_PREREQUISITE_CHANGED',409)
        event(c,a,'review_evidence_added',{'note':body.note,'source':'Fresh synthetic fixture'},'officer')
        previous={'outcome':a['outcome'],'model':a.get('model'),'decided_at':a['decided_at'],'stages':a['stages']}
        a.setdefault('decision_history',[]).append(previous)
        p=next(x for x in ENGINE.personas if x['key']==a['customer_id']); evaluate(c,a,p,fix=True)
        case['status']='RESOLVED';case['resolution']=body.note;case['resolved_at']=now();case['history'].append(previous)
        put(c,'review',id,case);put(c,'application',a['id'],a)
    return a

FAULTS=['none','missing_data','identity','api_outage','model_outage','unaffordable','payment_fail','payment_unknown']
class SettingsRequest(Strict): fault:Literal['none','missing_data','identity','api_outage','model_outage','unaffordable','payment_fail','payment_unknown']='none'; new_run:bool=False
@app.get('/api/settings')
def settings(s=Depends(auth)):
    require(s,'presenter','officer','observer')
    with transaction() as c:return {**current(c),'faults':FAULTS}
@app.post('/api/settings')
def set_settings(body:SettingsRequest,s=Depends(auth)):
    require(s,'presenter')
    with transaction() as c:
        st=current(c); st['fault']=body.fault
        if body.new_run:
            for a in items(c,'application'):
                if a.get('offer') and a['offer']['status'] in ['ISSUED','ACCEPTED']:
                    a['offer']['status']='INVALIDATED';put(c,'application',a['id'],a);event(c,a,'offer_invalidated',{'reason':'NEW_DEMO_RUN'})
            st['run_id']=uid('RUN')
        put(c,'settings','current',st);event(c,{'run_id':st['run_id']},'scenario_configured',{'fault':body.fault},'presenter')
    return st

class PriceRequest(Strict): price_vnd:int=Field(ge=1000,le=100000000)
@app.post('/api/orders/{id}/price')
def change_price(id:str,body:PriceRequest,s=Depends(auth)):
    require(s,'presenter')
    with transaction() as c:
        o=get(c,'order',id)
        if not o or o['status']!='OPEN':error('ORDER_NOT_OPEN',409)
        o['version']+=1;o['price_vnd']=body.price_vnd;put(c,'order',id,o)
        for a in items(c,'application'):
            if a['order_id']==id and a.get('offer') and a['offer']['status'] in ['ISSUED','ACCEPTED']:
                a['offer']['status']='INVALIDATED';put(c,'application',a['id'],a);event(c,a,'offer_invalidated',{'reason':'ORDER_CHANGED'})
    return o

@app.get('/api/events/{id}')
def events(id:str,s=Depends(auth)):
    require(s,'officer','presenter','observer')
    with transaction() as c: return [e for e in items(c,'event') if e['application_id']==id][::-1]
@app.get('/api/model')
def model_card(s=Depends(auth)):
    require(s,'officer','presenter','observer')
    report=ROOT/'reports/model_report.json'; audit=ROOT/'reports/data_audit.json'
    return {'manifest':{k:v for k,v in ENGINE.manifest.items() if k!='partitions'},'provenance':ENGINE.provenance,
      'report':json.loads(report.read_text()) if report.exists() else {},'audit':json.loads(audit.read_text()) if audit.exists() else {}}

@app.get('/api/metrics')
def metrics(s=Depends(auth)):
    require(s,'officer','presenter','observer')
    with transaction() as c:
        st=current(c); data=[a for a in items(c,'application') if a['run_id']==st['run_id']]
    n=len(data); counts={k:sum(a['outcome']==k for a in data) for k in ['APPROVED','DECLINED','REFERRED','BLOCKED','PENDING_DEPENDENCY']}
    automatic=[a for a in data if a['outcome'] in ['APPROVED','DECLINED'] and not a.get('review_case_id') and not a.get('decision_history')]
    routing=[a['latency_ms'] for a in data]; final=[a['latency_ms'] for a in automatic]
    review=sum(bool(a.get('review_case_id')) for a in data)
    return {'run_id':st['run_id'],'n':n,'counts':counts,'automatic_final_count':len(automatic),'automatic_final_rate':len(automatic)/n if n else 0,
      'routing_mean_ms':sum(routing)/n if n else None,'final_decision_mean_ms':sum(final)/len(final) if final else None,
      'captured':sum(a.get('payment',{}).get('status')=='CAPTURED' for a in data if a.get('payment')),
      'modelled_cost_vnd':12000+380000*review/n if n else None,
      'cost_assumptions':{'automation_per_application_vnd':12000,'additional_review_vnd':380000,'type':'Supplied simulation benchmark; not realised cost'},
      'manual_cost_benchmark_vnd':380000,'supplied_time_range':{'manual_business_days':[1.8,4.6],'stp_minutes':[1,3]},
      'note':'Measured local execution timings are separate from supplied business-day benchmarks. Human-reviewed cases remain outside STP even after approval; automated final-decision timing excludes them.'}

app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
@app.get('/')
def index():return FileResponse(ROOT/'web/index.html')
@app.get('/bank')
def bank():return FileResponse(ROOT/'web/bank.html')
@app.get('/checkout')
def checkout():return FileResponse(ROOT/'web/checkout.html')
@app.get('/training-notebook')
def notebook():return FileResponse(ROOT/'training/HLB_Flow_LightGBM_Training.ipynb',filename='HLB_Flow_LightGBM_Training.ipynb')

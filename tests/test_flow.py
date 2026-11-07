import os, tempfile, uuid, math, concurrent.futures
os.environ['FLOW_RUNTIME']=tempfile.mkdtemp(prefix='hlb-flow-test-')
os.environ['FLOW_ACCESS_CODE']='automated-test-code'
import pytest
from fastapi.testclient import TestClient
from backend.app import app,ENGINE,transaction,get,put
from backend.engine import schedule
from training.train import FEATURES,vector

client=TestClient(app)

def login(role='customer',persona='gig'):
    r=client.post('/api/login',json={'code':'automated-test-code','role':role,'persona':persona});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
def post(path,h,body=None,key=None):
    return client.post('/api'+path,headers={**h,**({'Idempotency-Key':key} if key else {})},json=body)
def create(fault='none',persona='gig',tenure=6):
    p=login('presenter');assert post('/settings',p,{'fault':fault}).status_code==200
    h=login(persona=persona);o=post('/orders',h,{'sku':'phone'}).json()
    co=post('/consents',h,{'order_id':o['id'],'granted':True}).json()
    payload={'order_id':o['id'],'order_version':o['version'],'consent_id':co['id'],'principal_vnd':6000000,'tenure_months':tenure}
    key=str(uuid.uuid4());r=post('/applications',h,payload,key);assert r.status_code==200,r.text
    return h,o,co,r.json(),payload,key
def checkout(h,a,fault='none'):
    assert a['outcome']=='APPROVED',a
    assert post('/applications/'+a['id']+'/accept',h).status_code==200
    ch=post('/applications/'+a['id']+'/challenge',h).json()
    p=login('presenter');post('/settings',p,{'fault':fault})
    body={'challenge_id':ch['id'],'code':ch['demo_code']};key=str(uuid.uuid4())
    return post('/applications/'+a['id']+'/pay',h,body,key),body,key

def test_model_is_from_colab_and_ready():
    assert ENGINE.error is None
    assert ENGINE.provenance['execution_environment']=='Google Colab'
def test_no_label_leakage():
    prohibited={'is_default_90d','manual_approval_status','stp_approval_status','approved_loan_vnd','is_abandoned','interest_rate_pct','unified_credit_score','applicant_id','customer_profile','application_date'}
    assert not prohibited.intersection(FEATURES)
    row=dict(ENGINE.personas[0]['row']);base=ENGINE.score(row)['risk']
    for k in prohibited:row[k]=0
    assert ENGINE.score(row)['risk']==base
def test_contributions_reconstruct_margin():
    score=ENGINE.score(ENGINE.personas[0]['row'])
    assert math.isclose(score['base_margin']+sum(x['contribution'] for x in score['contributions']),score['raw_margin'],abs_tol=1e-7)
@pytest.mark.parametrize('months',[3,6,9,12])
@pytest.mark.parametrize('rate',[0,20])
def test_schedule_reconciles(months,rate):
    s=schedule(6000001,months,rate)
    assert sum(x['principal_vnd'] for x in s['schedule'])==6000001
    assert s['schedule'][-1]['closing_vnd']==0
    assert s['total_repayment_vnd']==6000001+s['total_interest_vnd']
def test_month_end():
    import datetime
    s=schedule(6000000,3,20,datetime.date(2026,1,31));assert s['schedule'][0]['due_date']=='2026-02-28'
@pytest.mark.parametrize('fault,expected',[('identity','BLOCKED'),('missing_data','REFERRED'),('api_outage','PENDING_DEPENDENCY'),('model_outage','PENDING_DEPENDENCY')])
def test_missing_evidence_never_scores(fault,expected):
    h,o,co,a,_,_=create(fault);assert a['outcome']==expected;assert a['model'] is None;assert a['offer'] is None;assert a['review_case_id']
def test_affordability_blocks_low_risk():
    h,o,co,a,_,_=create('unaffordable');assert a['outcome']=='DECLINED';assert not a['affordability']['passes'];assert a['offer'] is None
def test_source_visibility_flag_beats_populated_values(monkeypatch):
    p=next(x for x in ENGINE.personas if x['key']=='gig')
    monkeypatch.setitem(p['row'],'has_observable_tx',0)
    h,o,co,a,_,_=create()
    assert a['outcome']=='REFERRED' and a['model'] is None
def test_happy_path_capture():
    h,o,co,a,_,_=create();r,_,_=checkout(h,a);assert r.status_code==200,r.text
    a=r.json();assert a['payment']['status']=='CAPTURED';assert a['loan']['status']=='ACTIVE'
    assert client.get('/api/orders/'+o['id'],headers=h).json()['status']=='CONFIRMED'
def test_duplicate_payment_same_key():
    h,o,co,a,_,_=create();r,body,key=checkout(h,a);again=post('/applications/'+a['id']+'/pay',h,body,key)
    assert again.json()['loan']['id']==r.json()['loan']['id']
    bad=post('/applications/'+a['id']+'/pay',h,{**body,'code':'000000'},key);assert bad.status_code==409
def test_concurrent_payment_no_duplicate_loan():
    h,o,co,a,_,_=create();post('/applications/'+a['id']+'/accept',h);ch=post('/applications/'+a['id']+'/challenge',h).json();body={'challenge_id':ch['id'],'code':ch['demo_code']}
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:post('/applications/'+a['id']+'/pay',h,body,'same-concurrent-key'),range(2)))
    assert all(r.status_code==200 for r in results)
    assert results[0].json()['loan']['id']==results[1].json()['loan']['id']
def test_unknown_payment_reconciles_original_reference():
    h,o,co,a,_,_=create();r,_,_=checkout(h,a,'payment_unknown');p=r.json()['payment'];assert p['status']=='UNKNOWN';assert not r.json().get('loan')
    resolved=post('/applications/'+a['id']+'/reconcile',h).json();assert resolved['payment']['id']==p['id'];assert resolved['payment']['status']=='CAPTURED'
    assert post('/applications/'+a['id']+'/reconcile',h).status_code==409
def test_failed_payment_has_no_loan():
    h,o,co,a,_,_=create();r,_,_=checkout(h,a,'payment_fail');assert r.json()['payment']['status']=='FAILED';assert not r.json().get('loan')
def test_refund_reverses_loan():
    h,o,co,a,_,_=create();r,_,_=checkout(h,a);r=post('/applications/'+a['id']+'/refund',login('officer'));assert r.status_code==200
    assert r.json()['payment']['status']=='REFUNDED';assert r.json()['loan']['status']=='CANCELLED'
def test_application_idempotency():
    h,o,co,a,payload,key=create();assert post('/applications',h,payload,key).json()['id']==a['id']
    assert post('/applications',h,{**payload,'tenure_months':3},key).status_code==409
def test_declined_consent():
    h=login();o=post('/orders',h,{'sku':'phone'}).json();assert post('/consents',h,{'order_id':o['id'],'granted':False}).status_code==400
def test_withdrawal_blocks_acceptance():
    h,o,co,a,_,_=create();assert post('/consents/'+co['id']+'/withdraw',h).status_code==200
    assert post('/applications/'+a['id']+'/accept',h).status_code==409
def test_unsupported_tenure():
    h,o,co,a,payload,key=create();assert post('/applications',h,{**payload,'tenure_months':5},str(uuid.uuid4())).status_code==422
def test_amount_tampering():
    h,o,co,a,payload,key=create();assert post('/applications',h,{**payload,'principal_vnd':5000000},str(uuid.uuid4())).status_code==409
def test_customer_cannot_inject_features():
    h,o,co,a,payload,key=create();assert post('/applications',h,{**payload,'risk':0,'monthly_inflow_vnd':999999999},str(uuid.uuid4())).status_code==422
def test_ownership_and_roles():
    h,o,co,a,_,_=create();other=login(persona='salaried')
    assert client.get('/api/applications/'+a['id'],headers=other).status_code==403
    assert post('/settings',h,{'fault':'none'}).status_code==403
    assert client.get('/api/model',headers=h).status_code==403
def test_auth_required():assert client.get('/api/applications').status_code==401
def test_invalid_origin():
    assert client.post('/api/login',headers={'Origin':'https://evil.example'},json={'code':'automated-test-code'}).status_code==403
def test_price_change_invalidates_offer():
    h,o,co,a,_,_=create();p=login('presenter');assert post('/orders/'+o['id']+'/price',p,{'price_vnd':6100000}).status_code==200
    assert post('/applications/'+a['id']+'/accept',h).status_code==409
def test_offer_expiry():
    h,o,co,a,_,_=create()
    with transaction() as c:
        stored=get(c,'application',a['id']);stored['offer']['expires_at']=0;put(c,'application',a['id'],stored)
    assert post('/applications/'+a['id']+'/accept',h).status_code==409
def test_wrong_auth_code_attempts_persist():
    h,o,co,a,_,_=create();post('/applications/'+a['id']+'/accept',h);ch=post('/applications/'+a['id']+'/challenge',h).json()
    for _ in range(5):assert post('/applications/'+a['id']+'/pay',h,{'challenge_id':ch['id'],'code':'bad'},str(uuid.uuid4())).status_code==401
    assert post('/applications/'+a['id']+'/pay',h,{'challenge_id':ch['id'],'code':ch['demo_code']},str(uuid.uuid4())).status_code==409
def test_review_requires_recovery():
    h,o,co,a,_,_=create('identity');off=login('officer')
    payload={'note':'Fresh fixture verification','evidence_recovered':True}
    assert post('/reviews/'+a['review_case_id']+'/resolve',off,payload).status_code==409
    post('/settings',login('presenter'),{'fault':'none'})
    r=post('/reviews/'+a['review_case_id']+'/resolve',off,payload);assert r.status_code==200,r.text
    assert r.json()['decision_history'][0]['outcome']=='BLOCKED';assert r.json()['model']
def test_audit_contains_capture_once():
    h,o,co,a,_,_=create();checkout(h,a);ev=client.get('/api/events/'+a['id'],headers=login('officer')).json()
    assert sum(e['type']=='payment_captured' for e in ev)==1;assert any(e['type']=='decision_saved' for e in ev)
def test_metrics_separates_modelled_cost():
    m=client.get('/api/metrics',headers=login('observer')).json();assert m['cost_assumptions']['type'].startswith('Supplied simulation');assert 'note' in m
def test_manual_review_resolution_never_counts_as_stp():
    post('/settings',login('presenter'),{'fault':'none','new_run':True})
    h,o,co,a,_,_=create('missing_data')
    post('/settings',login('presenter'),{'fault':'none'})
    r=post('/reviews/'+a['review_case_id']+'/resolve',login('officer'),{'note':'Fresh synthetic source checked','evidence_recovered':True})
    assert r.json()['outcome']=='APPROVED'
    m=client.get('/api/metrics',headers=login('observer')).json()
    assert m['n']==1 and m['automatic_final_rate']==0 and m['final_decision_mean_ms'] is None
def test_new_run_retains_audit_and_invalidates_offer():
    h,o,co,a,_,_=create();post('/settings',login('presenter'),{'fault':'none','new_run':True})
    again=client.get('/api/applications/'+a['id'],headers=h).json();assert again['offer']['status']=='INVALIDATED'
    assert client.get('/api/events/'+a['id'],headers=login('observer')).json()

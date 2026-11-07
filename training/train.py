"""Reproducible competition-label model. No historical decisions enter predictors."""
from pathlib import Path
import argparse, collections, datetime as dt, hashlib, json, platform
import numpy as np
import openpyxl
import lightgbm as lgb
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss, confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['has_formal_cic_history','monthly_inflow_vnd','inflow_cv','casa_balance_vnd','dti_ratio','on_time_bill_ratio','e_wallet_topups_pm','regular_weekly_pattern','rapid_drain_flag','requested_loan_vnd','loan_tenure_months','requested_to_inflow','casa_to_inflow']
VERSION = 'flow-lgbm-v1'
LIMITATIONS = [
 'Synthetic competition data; not validated for real lending.',
 'is_default_90d means 90+ days past due during loan tenure, not default within 90 days.',
 'All positive labels occur among applications declined by both supplied decision methods; outcome provenance requires confirmation.',
 'Outcome maturity dates and repeated-person identifiers are unavailable.',
 'Primary model excludes opaque unified_credit_score, assigned interest rate, IDs, segment and all historical decisions/outcomes.',
 'Model output is a simulated risk estimate. Demo thresholds and pricing are illustrative.',
]

def vector(r):
    d = dict(r)
    income = float(d['monthly_inflow_vnd'])
    if income <= 0: raise ValueError('Income must be positive')
    d['requested_to_inflow'] = float(d['requested_loan_vnd']) / income
    d['casa_to_inflow'] = float(d['casa_balance_vnd']) / income
    values = [float(d[k]) for k in FEATURES]
    if not all(np.isfinite(values)): raise ValueError('Non-finite features')
    return values

def metrics(y, p):
    p = np.clip(np.asarray(p), 1e-9, 1-1e-9)
    return {'n':len(y),'positives':int(sum(y)), 'prevalence':float(np.mean(y)),
      'roc_auc':float(roc_auc_score(y,p)) if len(set(y))>1 else None,
      'pr_auc':float(average_precision_score(y,p)), 'brier':float(brier_score_loss(y,p)),
      'log_loss':float(log_loss(y,p,labels=[0,1])),
      'confusion_at_005':confusion_matrix(y,p>=.05,labels=[0,1]).tolist()}

def main(source=None):
    source = Path(source or ROOT/'data/source.xlsx')
    w = openpyxl.load_workbook(source, read_only=True, data_only=True)
    definitions = {row[0]:row[1] for row in w['data definition'].iter_rows(min_row=2,values_only=True) if row[0]}
    it=w['dataset'].iter_rows(values_only=True); header=next(it)
    rows=[]
    for vals in it:
        if vals[0] is None: continue
        r=dict(zip(header,vals))
        date=r['application_date']
        if isinstance(date,(float,int)): date=dt.datetime(1899,12,30)+dt.timedelta(days=date)
        r['application_date']=date.strftime('%Y-%m-%d') if hasattr(date,'strftime') else str(date)[:10]
        rows.append(r)
    audit={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(rows),'fields':len(header),
       'unique_applications':len({r['applicant_id'] for r in rows}), 'positive_labels':sum(int(r['is_default_90d']) for r in rows),
       'unobservable':sum(not r['has_observable_tx'] for r in rows),
       'unsupported_tenure':sum(r['loan_tenure_months'] not in [3,6,9,12,18,24] for r in rows),
       'positive_labels_among_manual_approvals':sum(int(r['is_default_90d']) for r in rows if r['manual_approval_status']),
       'positive_labels_among_supplied_stp_approvals':sum(int(r['is_default_90d']) for r in rows if r['stp_approval_status']),
       'definitions':definitions, 'limitations':LIMITATIONS}
    eligible=[]; excluded=collections.Counter()
    for r in rows:
        if not r['has_observable_tx']: excluded['unobservable']+=1; continue
        if r['loan_tenure_months'] not in [3,6,9,12,18,24]: excluded['unsupported_tenure']+=1; continue
        try: vector(r)
        except (ValueError,TypeError,KeyError): excluded['invalid_features']+=1; continue
        eligible.append(r)
    groups = {'train':[], 'tuning':[], 'calibration':[], 'test':[]}
    for r in eligible:
        d=r['application_date']
        key='train' if d<'2026-05-01' else 'tuning' if d<'2026-05-16' else 'calibration' if d<'2026-06-01' else 'test'
        groups[key].append(r)
    xy={k:(np.asarray([vector(r) for r in rs]),np.asarray([int(r['is_default_90d']) for r in rs])) for k,rs in groups.items()}
    for k,(x,y) in xy.items():
        if len(set(y))<2: raise ValueError(f'{k}: both label classes required')
    model=lgb.LGBMClassifier(objective='binary',n_estimators=500,learning_rate=.03,num_leaves=15,max_depth=4,
       min_child_samples=50,colsample_bytree=.8,subsample=.8,subsample_freq=1,reg_alpha=.1,reg_lambda=1,
       random_state=42,n_jobs=1,verbosity=-1)
    model.fit(*xy['train'],eval_set=[xy['tuning']],callbacks=[lgb.early_stopping(50,verbose=False)])
    baseline=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000,random_state=42))
    baseline.fit(*xy['train'])
    # A separate temporal partition fits sigmoid calibration. No June data is used here.
    def raw(x): return np.asarray(model.booster_.predict(x,raw_score=True))
    calibrator=LogisticRegression(C=1.0,random_state=42).fit(raw(xy['calibration'][0]).reshape(-1,1),xy['calibration'][1])
    a=float(calibrator.coef_[0,0]); b=float(calibrator.intercept_[0])
    def calibrated(x): return 1/(1+np.exp(-np.clip(a*raw(x)+b,-700,700)))
    testx,testy=xy['test']
    reports={k:{'raw':metrics(y,model.predict_proba(x)[:,1]),'calibrated':metrics(y,calibrated(x))} for k,(x,y) in xy.items()}
    test_baselines={'constant':metrics(testy,np.repeat(np.mean(xy['train'][1]),len(testy))),
       'logistic':metrics(testy,baseline.predict_proba(testx)[:,1])}
    segments={}
    pred=calibrated(testx)
    for seg in sorted({r['customer_profile'] for r in groups['test']}):
        ix=np.array([r['customer_profile']==seg for r in groups['test']]); segments[seg]=metrics(testy[ix],pred[ix])
    reliability=[]
    for lo,hi in [(0,.01),(.01,.05),(.05,.12),(.12,.3),(.3,1.000001)]:
        ix=(pred>=lo)&(pred<hi)
        reliability.append({'lower':lo,'upper':min(hi,1),'n':int(ix.sum()),'mean_score':float(pred[ix].mean()) if ix.any() else None,'label_rate':float(testy[ix].mean()) if ix.any() else None})
    manifest={'version':VERSION,'features':FEATURES,'best_iteration':model.best_iteration_,
       'calibration':{'method':'sigmoid','coefficient':a,'intercept':b,'partition':'2026-05-16 through 2026-05-31'},
       'thresholds':{'approve_below':.05,'decline_at_or_above':.12,'status':'illustrative demo settings; not bank-approved'},
       'output':'Calibrated estimate of supplied synthetic 90+ DPD label during loan tenure',
       'source_sha256':audit['source_sha256'],'limitations':LIMITATIONS,
       'versions':{'python':platform.python_version(),'lightgbm':lgb.__version__,'sklearn':sklearn.__version__},
       'partitions':{k:{'n':len(rs),'positives':sum(int(r['is_default_90d']) for r in rs),'ids':[r['applicant_id'] for r in rs]} for k,rs in groups.items()},
       'trained_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    # Pick actual eligible holdout records only AFTER the model is frozen, for walkthroughs, never for tuning.
    persona=[]
    candidates=groups['test']
    allpred=calibrated(testx)
    for kind,segment in [('gig','Gig / platform workers'),('salaried','Salaried, with credit history'),('merchant','Online merchants (MSME)'),('thin','Salaried, no credit history')]:
        matches=[(r,p) for r,p in zip(candidates,allpred) if r['customer_profile']==segment]
        if not matches: matches=list(zip(candidates,allpred))
        # Prefer low risk for a shopping demo. The actual score of the NEW order is always recomputed.
        r,_=min(matches,key=lambda t:t[1]); persona.append({'key':kind,'name':{'gig':'Minh Nguyen','salaried':'Linh Tran','merchant':'Anh Pham','thin':'Mai Le'}[kind], 'row':r})
    artifacts=ROOT/'model'; reportsdir=ROOT/'reports'; artifacts.mkdir(exist_ok=True); reportsdir.mkdir(exist_ok=True)
    model.booster_.save_model(str(artifacts/'lightgbm.txt'))
    manifest['model_sha256']=hashlib.sha256((artifacts/'lightgbm.txt').read_bytes()).hexdigest()
    for path,obj in [(artifacts/'manifest.json',manifest),(artifacts/'personas.json',persona),(reportsdir/'data_audit.json',{**audit,'eligible':len(eligible),'excluded':dict(excluded)}),
        (reportsdir/'model_report.json',{'partitions':reports,'test_baselines':test_baselines,'test_segments':segments,'reliability':reliability,'limitations':LIMITATIONS}),
        (reportsdir/'schema.json',{'fields':[{'name':k,'definition':definitions.get(k),'column':i+1} for i,k in enumerate(header)]})]:
        path.write_text(json.dumps(obj,indent=2,default=str))
    print(json.dumps({'version':VERSION,'eligible':len(eligible),'test':reports['test'],'baselines':test_baselines,'limitations':LIMITATIONS},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source'); args=p.parse_args(); main(args.source)

from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP, localcontext
from calendar import monthrange
import datetime as dt, hashlib, json, math
import numpy as np
import lightgbm as lgb
from training.train import FEATURES, vector

ROOT=Path(__file__).resolve().parents[1]

def schedule(principal, months, annual_rate=20, today=None):
    today=today or dt.date.today()
    with localcontext() as ctx:
        ctx.prec=32
        p=Decimal(principal); r=Decimal(str(annual_rate))/1200
        emi=(p/months if not r else p*r/(1-(1+r)**(-months))).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
        balance=p; rows=[]
        for i in range(1,months+1):
            interest=(balance*r).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
            paid=balance if i==months else min(balance,emi-interest)
            month=today.month-1+i; year=today.year+month//12; month=month%12+1
            due=dt.date(year,month,min(today.day,monthrange(year,month)[1]))
            rows.append({'number':i,'due_date':due.isoformat(),'opening_vnd':int(balance),'principal_vnd':int(paid),
              'interest_vnd':int(interest),'payment_vnd':int(paid+interest),'closing_vnd':int(balance-paid)})
            balance-=paid
        total=sum(x['payment_vnd'] for x in rows)
        return {'principal_vnd':principal,'tenure_months':months,'annual_rate_pct':annual_rate,'fees_vnd':0,
          'monthly_payment_vnd':max(x['payment_vnd'] for x in rows),'total_interest_vnd':total-principal,
          'total_repayment_vnd':total,'schedule':rows}

class RiskEngine:
    def __init__(self, folder=None):
        self.folder=Path(folder or ROOT/'model'); self.error=None
        try:
            self.manifest=json.loads((self.folder/'manifest.json').read_text())
            path=self.folder/'lightgbm.txt'
            if hashlib.sha256(path.read_bytes()).hexdigest()!=self.manifest['model_sha256']: raise ValueError('Model hash mismatch')
            if self.manifest['features']!=FEATURES: raise ValueError('Feature schema mismatch')
            self.model=lgb.Booster(model_file=str(path)); self.personas=json.loads((self.folder/'personas.json').read_text())
            self.provenance=json.loads((self.folder/'colab_provenance.json').read_text())
            if self.provenance.get('execution_environment')!='Google Colab': raise ValueError('Colab provenance required')
        except Exception as e:
            self.error=str(e); self.personas=[]; self.manifest={}; self.provenance={}

    def score(self, row):
        if self.error: raise RuntimeError('MODEL_UNAVAILABLE: '+self.error)
        x=np.asarray([vector(row)])
        raw=float(self.model.predict(x,raw_score=True,num_threads=1)[0])
        contrib=self.model.predict(x,pred_contrib=True,num_threads=1)[0]
        if not math.isclose(float(contrib.sum()),raw,abs_tol=1e-7): raise ValueError('Explanation reconstruction failed')
        c=self.manifest['calibration']; risk=1/(1+math.exp(-max(-700,min(700,c['coefficient']*raw+c['intercept']))))
        contributions=sorted([{'feature':k,'value':float(v),'contribution':float(s)} for k,v,s in zip(FEATURES,x[0],contrib[:-1])],key=lambda a:abs(a['contribution']),reverse=True)
        return {'risk':risk,'raw_margin':raw,'base_margin':float(contrib[-1]),'contributions':contributions,
          'version':self.manifest['version'],'semantics':self.manifest['output'],'calibrated':True,
          'explanation_units':'Raw model log-odds; not percentage-point changes or causal effects'}

def affordability(row,terms,unaffordable=False):
    # Supplemental synthetic net-income/debt/living-cost assumptions, never claimed to be workbook facts.
    inflow=float(row['monthly_inflow_vnd'])
    net=inflow*(.6 if row['customer_profile']=='Online merchants (MSME)' else .8)
    debt=net*.20; living=net*.30
    if unaffordable: net=3_000_000; debt=1_500_000; living=2_000_000
    stressed=net*.8; installment=terms['monthly_payment_vnd']
    ratio=(debt+installment)/stressed; residual=stressed-debt-installment-living
    return {'net_income_vnd':round(net),'income_haircut_pct':20,'stressed_income_vnd':round(stressed),
      'existing_debt_vnd':round(debt),'living_cost_vnd':round(living),'installment_vnd':installment,
      'post_loan_dti':ratio,'residual_vnd':round(residual),'passes':ratio<=.4 and residual>=1_000_000,
      'source':'Supplemental synthetic demo fixture; net income/obligations are not supplied workbook fields',
      'maximum_dti':.4,'minimum_residual_vnd':1_000_000}

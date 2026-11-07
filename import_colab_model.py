"""Import trusted model text/JSON files from a Colab export, without running code."""
from pathlib import Path
import argparse, csv, hashlib, json, zipfile
ROOT=Path(__file__).resolve().parent
ALLOWED={'model/lightgbm.txt','model/manifest.json','model/personas.json','model/colab_provenance.json','reports/model_report.json','reports/schema.json','reports/data_audit.json'}
def main(path):
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        required={'model/lightgbm.txt','model/manifest.json','model/personas.json','model/colab_provenance.json'}
        if not required<=names:raise ValueError('ZIP is missing required Colab model files')
        m=json.loads(z.read('model/manifest.json')); p=json.loads(z.read('model/colab_provenance.json'))
        if p.get('execution_environment')!='Google Colab':raise ValueError('Colab provenance missing')
        if hashlib.sha256(z.read('model/lightgbm.txt')).hexdigest()!=m['model_sha256']:raise ValueError('Model checksum mismatch')
        if (ROOT/'data/source.xlsx').exists() and hashlib.sha256((ROOT/'data/source.xlsx').read_bytes()).hexdigest()!=m['source_sha256']:
            # Colab may receive the byte-different CSV export. Verify EVERY value against original XLSX.
            import openpyxl
            csvpath=ROOT/'data/source.csv'
            if not csvpath.exists() or hashlib.sha256(csvpath.read_bytes()).hexdigest()!=p.get('input_csv_sha256'):
                raise ValueError('Source workbook/CSV hash mismatch')
            w=openpyxl.load_workbook(ROOT/'data/source.xlsx',read_only=True,data_only=True)
            it=w['dataset'].iter_rows(values_only=True);header=next(it);xlsxrows=list(it)
            csvrows=list(csv.DictReader(csvpath.open()))
            if len(xlsxrows)!=len(csvrows):raise ValueError('CSV/XLSX row count mismatch')
            for index,(a,values) in enumerate(zip(csvrows,xlsxrows)):
                for k,v in zip(header,values):
                    expected=a[k]
                    if k=='application_date':same=expected[:10]==v.strftime('%Y-%m-%d')
                    elif k in ['applicant_id','customer_profile']:same=expected==v
                    else:same=abs(float(expected.replace(',',''))-float(v))<1e-8
                    if not same:raise ValueError(f'Source equivalence failed at row {index+2}, {k}')
        for name in names&ALLOWED:
            target=ROOT/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(z.read(name))
    # Preserve authoritative definitions from the original workbook, not the Colab conversion's paraphrases.
    import openpyxl
    w=openpyxl.load_workbook(ROOT/'data/source.xlsx',read_only=True,data_only=True)
    definitions={r[0]:r[1] for r in w['data definition'].iter_rows(min_row=2,values_only=True) if r[0]}
    columns=next(w['dataset'].iter_rows(values_only=True))
    (ROOT/'reports/schema.json').write_text(json.dumps({'source':'Original user-supplied XLSX data definition tab','fields':[{'name':k,'definition':definitions[k],'column':i+1} for i,k in enumerate(columns)]},indent=2))
    print('Imported Colab model to '+str(ROOT/'model'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip_path');a=p.parse_args();main(a.zip_path)

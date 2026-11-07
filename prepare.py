"""Prepare local static extension assets and verify existing Colab model. NEVER trains."""
from pathlib import Path
import hashlib, json, shutil, sys
ROOT=Path(__file__).resolve().parent

def prepare():
    for name in ['common.js','checkout.js','styles.css']:
        shutil.copy2(ROOT/'web'/name,ROOT/'extension'/name)
    panel=(ROOT/'web/checkout.html').read_text().replace('/assets/styles.css','styles.css').replace('/assets/checkout.js','checkout.js')
    (ROOT/'extension/panel.html').write_text(panel)
    needed=['lightgbm.txt','manifest.json','personas.json','colab_provenance.json']
    missing=[n for n in needed if not (ROOT/'model'/n).is_file()]
    if missing:
        print('SETUP STOPPED: missing Colab output in model/: '+', '.join(missing))
        print('Open training/HLB_Flow_LightGBM_Training.ipynb in Google Colab, run it, download the ZIP.')
        print('Then run: python import_colab_model.py /path/to/hlb_flow_colab_model.zip')
        print('Setup never trains or retrains a model.')
        return False
    manifest=json.loads((ROOT/'model/manifest.json').read_text())
    if hashlib.sha256((ROOT/'model/lightgbm.txt').read_bytes()).hexdigest()!=manifest['model_sha256']:
        raise ValueError('Model hash mismatch. Import the original Colab bundle again.')
    from backend.engine import RiskEngine
    engine=RiskEngine()
    if engine.error: raise RuntimeError(engine.error)
    print('Colab-trained model verified: '+manifest['version'])
    print('Extension prepared: '+str(ROOT/'extension'))
    return True

if __name__=='__main__':sys.exit(0 if prepare() else 2)

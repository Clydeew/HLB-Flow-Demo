$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) { $PythonCommand = 'py' }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $PythonCommand = 'python' }
else { throw 'Install Python 3.11+ from python.org (include pip), then run this script again.' }
& $PythonCommand -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ required.' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
  & $PythonCommand -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and Python version.' }
& $VenvPython prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed. Import the existing Colab export; setup never retrains.' }
& $VenvPython launch.py
if ($LASTEXITCODE -ne 0) { throw 'HLB Flow exited with an error.' }

"""Registra execucao real e hashes do caso TDD, sem alterar codigo ou simular falhas."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('red','green','refactor'))
    args = parser.parse_args()
    command = ['-B','-m','unittest','discover','-s','tests','-p','test_nlp.py',
               '-k','combo_preserves_separate_mouse_and_mousepad','-v']
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([sys.executable,*command],cwd=ROOT,capture_output=True,text=True)
    output = (result.stdout+result.stderr).replace(str(ROOT), '<repo>')
    output = output.replace(str(Path(sys.base_prefix)), '<python>')
    expected = result.returncode == 1 and 'AssertionError' in output if args.phase == 'red' else result.returncode == 0
    if not expected or 'Ran 1 test' not in output:
        print(output)
        raise SystemExit('Fase inesperada; evidencia nao foi gravada.')
    git = shutil.which('git.exe') or shutil.which('git')
    # Windows pode ter um alias de git sem permissao de execucao.
    if sys.platform == 'win32' and Path('C:/Program Files/Git/cmd/git.exe').is_file():
        git = 'C:/Program Files/Git/cmd/git.exe'
    head = subprocess.check_output([git,'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    record = {'phase':args.phase,'started_at_utc':started,
        'finished_at_utc':datetime.now(timezone.utc).isoformat(),'head_before_record':head,
        'python_version':sys.version.split()[0],'command':'python '+' '.join(command),
        'exit_code':result.returncode,'output':output,
        'sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                  for name in ('tests/test_nlp.py','nlp/analysis.py')},
        'scope':'Caso novo de combo mouse/mousepad; nao comprova TDD de funcionalidades anteriores.'}
    path = ROOT/'docs/evidence/tdd-combo'/f'{args.phase}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise SystemExit('Registro existente preservado; use nova pasta para outro ciclo.')
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(output)
    print(f'Evidencia {args.phase} registrada em {path.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

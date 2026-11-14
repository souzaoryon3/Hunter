"""Resumo com metadados selecionados; nao captura ambiente, credenciais ou dumps."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT/'local-reports/ci'
    directory.mkdir(parents=True,exist_ok=True)
    tests = directory/'tests.log'
    text = tests.read_text(encoding='utf-8',errors='replace') if tests.is_file() else ''
    match = re.search(r'Ran (\d+) tests? in ([\d.]+)s',text)
    coverage = directory/'coverage.json'
    totals = json.loads(coverage.read_text(encoding='utf-8'))['totals'] if coverage.is_file() else {}
    passed = bool(re.search(r'^OK(?: \(skipped=\d+\))?\s*$',text,re.M))
    skipped = re.search(r'OK \(skipped=(\d+)\)',text)
    record = {'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'repository':os.environ.get('GITHUB_REPOSITORY'), 'commit':os.environ.get('GITHUB_SHA'),
        'run_id':os.environ.get('GITHUB_RUN_ID'), 'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
        'unit_integration_passed':passed,
        'tests':int(match[1]) if match else None,'duration_seconds':float(match[2]) if match else None,
        'skipped':int(skipped[1]) if skipped else 0 if passed else None,
        'coverage_percent':totals.get('percent_covered'),
        'covered_lines':totals.get('covered_lines'),'statements':totals.get('num_statements'),
        'minimum_coverage_percent':80,
        'tdd_scope':'Caso combo mouse/mousepad: evidencias RED/GREEN/REFACTOR versionadas; nao representa todo o projeto.'}
    (directory/'summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a',encoding='utf-8') as stream:
            stream.write('## Evidencias de qualidade Hunter\n\n')
            stream.write(f"Commit: `{record['commit']}`\n\n")
            stream.write(f"Testes unitarios/integracao: {record['tests']}; aprovados: {passed}; skips: {record['skipped']}.\n\n")
            stream.write(f"Cobertura de linhas Python: {record['coverage_percent']}%; minimo: 80%.\n\n")
            stream.write('Logs, cobertura XML/JSON, demos e registros TDD estao no artefato hunter-quality.\n')
    print(json.dumps(record,ensure_ascii=False))


if __name__ == '__main__':
    main()

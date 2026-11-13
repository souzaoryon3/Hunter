"""Coleta ate 50 perifericos por loja e salva relatorio local."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraping.peripherals import collect_peripherals
from scraping.public_sources import STORES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', action='append', choices=tuple(STORES))
    parser.add_argument('--target', type=int, choices=range(1, 51), default=50)
    parser.add_argument('--max-pages', type=int, choices=range(1, 11), default=5)
    parser.add_argument('--transport', choices=('auto', 'http', 'browser'), default='auto')
    args = parser.parse_args()
    folder = Path(tempfile.gettempdir()) / 'HunterRuntime'
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = folder / ('peripherals-' + stamp + '.json')
    results = []
    for store in args.store or STORES:
        print('Coletando: ' + store, flush=True)
        def progress(row):
            print(json.dumps(dict(loja=store, **row), ensure_ascii=True), flush=True)
        try:
            result = collect_peripherals(store, args.target, args.max_pages, progress=progress,
                                         browser=None if args.transport == 'auto' else args.transport == 'browser')
        except Exception as exc:
            result = dict(loja=store, produtos=0, status='erro_' + type(exc).__name__, ofertas=[])
        results.append(result)
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k not in ('ofertas', 'paginas')},
                         ensure_ascii=True), flush=True)
    print('Relatorio local: ' + str(path), flush=True)


if __name__ == '__main__':
    main()

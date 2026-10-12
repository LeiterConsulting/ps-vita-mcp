"""Locate the public PS Vita MCP checkout and run its project helper."""
from pathlib import Path
import json
import os
import runpy
import sys


def repository():
    override = os.environ.get('VITA_APP_REPO')
    if override:
        choices = [Path(override)]
    else:
        local = Path(__file__).resolve().parents[1] / 'repository.json'
        if local.is_file():
            choices = [Path(json.loads(local.read_text(encoding='utf-8'))['repository'])]
        else:
            choices = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    for choice in choices:
        root = choice.resolve()
        if (root / 'tools/vita_app.py').is_file() and (root / 'workbench/native_package.py').is_file():
            return root
    raise RuntimeError('Set VITA_APP_REPO to your PS Vita MCP checkout, or run from that checkout')


if __name__ == '__main__':
    repo = repository()
    sys.path.insert(0, str(repo))
    runpy.run_path(str(repo / 'tools/vita_app.py'), run_name='__main__')

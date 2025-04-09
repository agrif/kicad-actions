#!/usr/bin/env python3

import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

import click

@click.group
def cli():
    pass

def find_extension(ext, path=None):
    if path is None:
        path = '.'
    path = pathlib.Path(path)

    if path.is_file():
        return path

    if not path.is_dir():
        raise RuntimeError('path does not exist: {}'.format(path))

    matches = list(path.rglob('*{}'.format(ext)))
    if len(matches) == 0:
        raise RuntimeError('file does not exist: {}/**/*{}'.format(path, ext))
    elif len(matches) == 1:
        return matches[0]

    raise RuntimeError('path is ambiguous: {}/**/*{}'.format(path, ext))

def project_file(path=None):
    return find_extension('.kicad_pro', path)

def find_project_extension(ext, path=None):
    if path is None:
        path = '.'
    path = pathlib.Path(path)

    if path.is_file():
        if path.suffix == '.kicad_pro':
            newpath = path.with_suffix(ext)
            if newpath.is_file():
                return newpath
            raise RuntimeError('path does not exist: {}'.format(newpath))

        return path

    if not path.is_dir():
        raise RuntimeError('path does not exist: {}'.format(path))

    project = None
    try:
        project = project_file(path)
    except RuntimeError:
        pass

    if project:
        return find_project_extension(ext, project)
    else:
        return find_extension(ext, path)

def schematic_file(path=None):
    return find_project_extension('.kicad_sch', path)

def pcb_file(path=None):
    return find_project_extension('.kicad_pcb', path)

def kicad_cli(*args, **kwargs):
    cmd = os.environ.get('KICAD_CLI', 'kicad-cli')
    cmd = shlex.split(cmd)
    try:
        subprocess.run([*cmd, *args], check=True, stdout=sys.stderr, **kwargs)
    except FileNotFoundError:
        raise RuntimeError('kicad-cli not found. Set $KICAD_CLI to point to it, or add it to your $PATH.') from None

@cli.command
@click.argument('path', required=False, type=click.Path())
def find_project(path):
    print(project_file(path))

@cli.command
@click.argument('path', required=False, type=click.Path())
def find_schematic(path):
    print(schematic_file(path))

@cli.command
@click.argument('path', required=False, type=click.Path())
def find_pcb(path):
    print(pcb_file(path))

def markdown_escape(s):
    ESCAPES = "\\`*_{}[]<>()#+-.!|"
    for c in ESCAPES:
        s = s.replace(c, '\\' + c)
    return s

def markdown_report(outer, data):
    unit = outer.get('coordinate_units', '')
    if unit:
        unit = ' ' + unit

    SEVERITIES = {
        'error': ':x:',
        'warning': ':warning:',
    }

    for v in data.get('schematic_parity', []) + data.get('violations', []):
        description = markdown_escape(v.get('description', ''))
        severity = SEVERITIES.get(v.get('severity'), '')
        print(' *', severity, description)

        for it in v.get('items', []):
            description = markdown_escape(it.get('description', ''))

            pos = ''
            x = it.get('pos', {}).get('x')
            y = it.get('pos', {}).get('y')
            if (x, y) != (None, None):
                pos = markdown_escape('({}{}, {}{})'.format(x, unit, y, unit))

            print('   *', description, pos)

@cli.command
@click.option('-f', '--format', type=click.Choice(['markdown', 'json'], case_sensitive=False))
@click.argument('path', required=False, type=click.Path())
def erc(format, path):
    sch = schematic_file(path)
    with tempfile.TemporaryDirectory(prefix='kipper.') as d:
        report = pathlib.Path(d) / 'report.json'
        kicad_cli('sch', 'erc', '--format=json', '-o', report, sch)
        with open(report) as f:
            data = f.read()

    if format == 'json':
        print(data)
    else:
        data = json.loads(data)
        sheets = data.get('sheets', [])
        for sheet in sheets:
            if len(sheets) > 1:
                print('#### Schematic', markdown_escape(sheet.get('path', '<unknown>')))
            markdown_report(data, sheet)

@cli.command
@click.option('-f', '--format', type=click.Choice(['markdown', 'json'], case_sensitive=False))
@click.option('--schematic-parity/--no-schematic-parity', default=True)
@click.argument('path', required=False, type=click.Path())
def drc(format, schematic_parity, path):
    pcb = pcb_file(path)
    with tempfile.TemporaryDirectory(prefix='kipper.') as d:
        report = pathlib.Path(d) / 'report.json'

        args = []
        if schematic_parity:
            args.append('--schematic-parity')

        kicad_cli('pcb', 'drc', '--format=json', *args, '-o', report, pcb)
        with open(report) as f:
            data = f.read()

    if format == 'json':
        print(data)
    else:
        data = json.loads(data)
        markdown_report(data, data)

if __name__ == '__main__':
    cli()

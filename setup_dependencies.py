"""Set up the local editor, with an optional Voicebox installer and demo."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from studio import ROOT, install_remotion, quickstart


def node_ready():
    return shutil.which('node') and int(subprocess.check_output(
        ['node', '-p', 'parseInt(process.versions.node)'], text=True)) >= 22


def install_voicebox(manifest, system):
    machine = platform.machine().lower()
    target = f'{system}-{machine}'
    if target not in manifest:
        raise ValueError(f'Для {target} нет проверенного установщика Voicebox. См. SETUP.txt.')
    name, checksum = manifest[target]
    downloads = ROOT / '.downloads'
    downloads.mkdir(exist_ok=True)
    destination = downloads / name
    with tempfile.TemporaryDirectory(dir=downloads) as directory:
        staged = Path(directory) / name
        candidate = destination
        if not candidate.exists():
            subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--output',
                            str(staged), manifest['source'] + name], check=True)
            candidate = staged
        digest = hashlib.sha256()
        with candidate.open('rb') as installer:
            for block in iter(lambda: installer.read(1024**2), b''):
                digest.update(block)
        if digest.hexdigest() != checksum:
            raise ValueError(f'Не совпадает SHA-256 установщика {name}.')
        if candidate == staged:
            os.replace(staged, destination)
    print(f'Установщик Voicebox: {destination}', flush=True)
    command = ['msiexec.exe', '/i'] if system == 'Windows' else ['open']
    subprocess.run([*command, str(destination)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voicebox', action='store_true')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    system = platform.system()
    manifest = json.loads((ROOT / 'dependencies.json').read_text(encoding='utf-8'))
    if system == 'Darwin':
        missing = []
        if not node_ready():
            missing.append(manifest['macos']['node'])
        if not all(shutil.which(name) for name in ('ffmpeg', 'ffprobe')):
            missing.append(manifest['macos']['ffmpeg'])
        if missing:
            if not shutil.which('brew'):
                raise RuntimeError('Установите отсутствующие инструменты через Homebrew. См. SETUP.txt.')
            subprocess.run(['brew', 'install', *missing], check=True)
    if not node_ready():
        raise RuntimeError('Нужен Node.js 22+ в PATH. Перезапустите терминал после установки.')
    install_remotion()
    print('FFmpeg и Remotion готовы.', flush=True)
    if args.voicebox:
        install_voicebox(manifest['voicebox'], system)
    if args.demo:
        quickstart(ROOT / '2d-output', 'all')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

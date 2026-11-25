"""Check and download local assets, and generate narration with Voicebox."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from studio import ROOT, request
from media_tools import FLUX_UNET, FLUX_ENCODER, FLUX_VAE

HF = 'https://huggingface.co/'
MODELS = (
    ('checkpoints', 'Lightricks/LTX-2.3-fp8', '91eda216f820e5ecb3d17dc9fe3b7cdaf56b587d',
     'ltx-2.3-22b-dev-fp8.safetensors', 29145431166, '28606c5b5a06ce56f896d4dfcb20f212739e07a68fbe48e53638188449d26450'),
    ('loras', 'Comfy-Org/ltx-2.3', 'f20f3a54378001e5e6d642acc84719cc78addf4b',
     'split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors', 2741024390, '31e0c0195fb841bf31af78e8b60858f489e87ddcea4a5239abc80943da65e3ac'),
    ('text_encoders', 'Comfy-Org/ltx-2', 'ccde4ba417d7900669fd56dd292a883cee11ff37',
     'split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors', 9447702218, 'aaca463d11e6d8d2a4bdb0d6299214c15ef78a3f73e0ef8113d5a9d0219b3f6d'),
    ('latent_upscale_models', 'Lightricks/LTX-2.3', 'c1521179de480464f366a98a9d9b2acc4cc097b9',
     'ltx-2.3-spatial-upscaler-x2-1.1.safetensors', 995743560, '5f416311fa8172b65af67530758964708d29a317b830d689a51143b7f91913ed'),
)
IMAGE_MODELS = (
    ('unet', 'unsloth/FLUX.2-klein-4B-GGUF', '8342a6a97b2d18acae5d62124735c39ba23060e2',
     FLUX_UNET, 3409273408, 'fb3b5430d9229f982616c7db084deff1db5035d0cb6558f2d4f704cfe5e609e2'),
    ('text_encoders', 'Comfy-Org/Flux-2-Klein-4B', '5b3abca5c0dc1ecd4eaf3340868d09063fc1c965',
     'split_files/text_encoders/' + FLUX_ENCODER, 3848213998,
     '3eab03a77adb0ee5304a4e677d5c10ac22f9049c1d7c894adca4f8bb39206ca8'),
    ('vae', 'Comfy-Org/flux2-dev', '9630c1b4b6e690497ae0c19bb6b1b35d4ebedcb7',
     'split_files/vae/' + FLUX_VAE, 336213556,
     'd64f3a68e1cc4f9f4e29b6e0da38a0204fe9a49f2d4053f0ec1fa1ca02f9c4b5'),
)


def models(root, download, entries=MODELS):
    if not (root / 'input').is_dir() or not (root / 'output').is_dir():
        raise ValueError('Укажите корень работающей установки ComfyUI с папками input и output.')
    pending = []
    for folder, repo, revision, remote, size, digest in entries:
        target = root / 'models' / folder / Path(remote).name
        if target.exists():
            if target.stat().st_size != size:
                raise ValueError(f'Файл другого размера: {target}. Проверьте его перед заменой.')
            print(f'Есть, размер совпадает: {target.name}')
            continue
        partial = target.with_suffix(target.suffix + '.part')
        remaining = size - (partial.stat().st_size if partial.exists() else 0)
        if remaining < 0:
            raise ValueError(f'Некорректный размер временного файла: {partial}')
        print(f'Не загружен: {target.name} ({remaining / 1e9:.2f} ГБ осталось)')
        pending.append((target, partial, HF + repo + '/resolve/' + revision + '/' + remote,
                        size, digest, remaining))
    total = sum(entry[-1] for entry in pending)
    print(f'К загрузке: {total / 1e9:.2f} ГБ', flush=True)
    if not download or not pending:
        return
    if not shutil.which('curl'):
        raise ValueError('Для скачивания с докачкой нужен curl.')
    if shutil.disk_usage(root).free < total + 1024**3:
        raise ValueError('Недостаточно места для оставшихся весов и запаса в 1 ГиБ.')
    for target, partial, url, size, digest, remaining in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        if remaining:
            subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--continue-at', '-',
                            '--output', str(partial), url], check=True)
        with partial.open('rb') as stream:
            checksum = hashlib.sha256()
            for block in iter(lambda: stream.read(8 * 1024**2), b''):
                checksum.update(block)
        if partial.stat().st_size != size or checksum.hexdigest() != digest:
            raise ValueError(f'Проверка SHA-256 не пройдена: {partial}. Файл не установлен.')
        if target.exists():
            raise FileExistsError(target)
        partial.rename(target)
        print(f'Установлен: {target.name}', flush=True)



CAST_TEXT = (
    'С виду обычный коврик. Но деньги здесь не в резине. '
    'Клиент платит за точную форму, чтобы коврик сел как родной. Покажу, с чего начать.'
)
CAST = {
    'panther': 'Пантера',
    'tigress': 'Тигрица',
    'wolf': 'Волк',
}


def cast_profile(url, actor, profiles):
    if actor not in CAST:
        raise ValueError(f'Неизвестный голос «{actor}». Доступны: {", ".join(CAST)}.')
    label = 'Reel Studio v2 · ' + CAST[actor]
    profile = next((item for item in profiles if item.get('name') == label), None)
    if profile is None:
        profile = request(url, '/profiles', {
            'name': label, 'language': 'ru', 'voice_type': 'cloned', 'default_engine': 'qwen',
            'description': 'Оригинальный синтетический голос Reel Studio.',
        })
    route = '/profiles/' + quote(profile['id'], safe='') + '/samples'
    if not request(url, route):
        name = f'{actor}-reference.wav'
        reference = (ROOT / 'assets' / 'voices' / name).read_bytes()
        boundary = uuid.uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="reference_text"\r\n\r\n'
            f'{CAST_TEXT}\r\n--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            'Content-Type: audio/wav\r\n\r\n'
        ).encode() + reference + f'\r\n--{boundary}--\r\n'.encode()
        upload = Request(url + route, body, {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        })
        with urlopen(upload, timeout=60) as response:
            json.load(response)
    return profile['id']


def speak(args, url):
    destination = args.output.resolve()
    if destination.suffix.lower() != '.wav' or destination.exists():
        raise ValueError('Укажите новый выходной файл с расширением .wav.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    profile = request(url, '/profiles/' + quote(args.profile, safe=''))
    engine = args.engine or profile.get('default_engine') or (
        'qwen_custom_voice' if profile.get('voice_type') in ('preset', 'designed') else 'qwen'
    )
    recipe = {'profile_id': args.profile, 'text': args.text, 'language': args.language,
              'engine': engine, 'seed': 7}
    if args.instruct:
        recipe['instruct'] = args.instruct
    generation = request(url, '/generate', recipe)['id']
    print(f'Voicebox: {generation}', flush=True)
    route_id = quote(str(generation), safe='')
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        status = request(url, '/history/' + route_id)
        if status['status'] == 'completed':
            break
        if status['status'] in ('failed', 'cancelled', 'canceled'):
            raise RuntimeError(status.get('error') or 'Генерация Voicebox прервана.')
        time.sleep(2)
    else:
        raise TimeoutError('Voicebox не завершил генерацию за 15 минут.')
    with urlopen(url + '/audio/' + route_id, timeout=60) as response:
        audio = response.read()
    if len(audio) < 44 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
        raise ValueError('Voicebox вернул данные в формате, отличном от WAV.')
    with tempfile.TemporaryDirectory(prefix='voicebox-', dir=destination.parent) as directory:
        staged = Path(directory) / destination.name
        staged.write_bytes(audio)
        staged.replace(destination)
    print(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voicebox-url', default='http://127.0.0.1:17493')
    commands = parser.add_subparsers(dest='command', required=True)
    weights = commands.add_parser('models')
    weights.add_argument('--comfy', type=Path, required=True)
    weights.add_argument('--download', action='store_true')
    weights.add_argument('--set', choices=['video', 'image', 'all'], default='video')
    commands.add_parser('profiles')
    voice = commands.add_parser('speak')
    selector = voice.add_mutually_exclusive_group(required=True)
    selector.add_argument('--profile')
    selector.add_argument('--cast', choices=CAST)
    voice.add_argument('--text', required=True)
    voice.add_argument('--language', default='ru')
    voice.add_argument('--engine')
    voice.add_argument('--instruct')
    voice.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'models':
        sets = {'video': MODELS, 'image': IMAGE_MODELS, 'all': MODELS + IMAGE_MODELS}
        models(args.comfy.resolve(), args.download, sets[args.set])
        return
    url = args.voicebox_url.rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Укажите локальный HTTP-адрес Voicebox.')
    if args.command == 'profiles' or args.cast:
        profiles = request(url, '/profiles')
        if isinstance(profiles, dict):
            profiles = profiles['profiles']
        if args.command == 'profiles':
            print(json.dumps([{'id': p['id'], 'name': p.get('name')} for p in profiles],
                             ensure_ascii=False, indent=2))
            return
        args.profile = cast_profile(url, args.cast, profiles)
    speak(args, url)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

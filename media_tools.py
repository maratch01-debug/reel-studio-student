"""Local tools for images, subtitles, interpolation and simple sound effects."""
import argparse
import json
import math
import random
import re
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from array import array
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from studio import ffmpeg, media_info, request

FLUX_UNET = 'flux-2-klein-4b-Q6_K.gguf'
FLUX_ENCODER = 'qwen_3_4b_fp4_flux2.safetensors'
FLUX_VAE = 'flux2-vae.safetensors'


def flux_workflow(prompt, seed, width, height, prefix, reference):
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': FLUX_UNET}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': FLUX_ENCODER, 'type': 'flux2'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': FLUX_VAE}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
        '5': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '6': {'class_type': 'Flux2Scheduler', 'inputs': {'steps': 4, 'width': width, 'height': height}},
        '7': {'class_type': 'BasicGuider', 'inputs': {'model': ['1', 0], 'conditioning': ['4', 0]}},
        '8': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
        '9': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        '10': {'class_type': 'SamplerCustomAdvanced', 'inputs': {
            'noise': ['8', 0], 'guider': ['7', 0], 'sampler': ['9', 0], 'sigmas': ['6', 0], 'latent_image': ['5', 0],
        }},
        '11': {'class_type': 'VAEDecode', 'inputs': {'samples': ['10', 0], 'vae': ['3', 0]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': prefix}},
    }
    if reference:
        graph.update({
            '20': {'class_type': 'LoadImage', 'inputs': {'image': reference}},
            '21': {'class_type': 'ImageScaleToTotalPixels', 'inputs': {
                'image': ['20', 0], 'upscale_method': 'lanczos', 'megapixels': 1.0, 'resolution_steps': 1,
            }},
            '22': {'class_type': 'VAEEncode', 'inputs': {'pixels': ['21', 0], 'vae': ['3', 0]}},
            '23': {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': ['4', 0], 'latent': ['22', 0]}},
        })
        graph['7']['inputs']['conditioning'] = ['23', 0]
    return graph


def image(args, output):
    url = args.url.rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Укажите локальный HTTP-адрес ComfyUI.')
    if any(value < 256 or value > 1536 or value % 16 for value in (args.width, args.height)):
        raise ValueError('Ширина и высота должны быть кратны 16 и лежать между 256 и 1536.')
    prefix = 'reel_asset_' + uuid.uuid4().hex
    reference = None
    if args.reference:
        if not args.comfy or not (args.comfy / 'input').is_dir():
            raise ValueError('Для --reference укажите корень ComfyUI через --comfy.')
        reference = (args.comfy / 'input' / (prefix + '.png')).resolve()
        ffmpeg('-i', args.reference, '-frames:v', 1, '-threads', 1, reference)
    graph = flux_workflow(args.prompt, args.seed, args.width, args.height, prefix,
                          reference.name if reference else None)
    task = request(url, '/prompt', {'prompt': graph})['prompt_id']
    print(f'ComfyUI: {task}', flush=True)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        state = request(url, '/history/' + task).get(task, {})
        status = state.get('status', {})
        if status.get('status_str') == 'error':
            raise RuntimeError(f'ComfyUI: {status.get("messages", [])[-1:]}')
        if status.get('completed'):
            images = state.get('outputs', {}).get('12', {}).get('images', [])
            if not images:
                raise RuntimeError('ComfyUI не вернул изображение.')
            with urlopen(url + '/view?' + urlencode(images[0]), timeout=60) as response:
                data = response.read()
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('ComfyUI вернул файл, отличный от PNG.')
            output.write_bytes(data)
            if reference:
                reference.unlink(missing_ok=True)
            return
        time.sleep(2)
    raise TimeoutError(f'ComfyUI не закончил задачу {task} за 15 минут.')


def captions(args, output):
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError('Установите зависимости: python -m pip install -r requirements-captions.txt') from error
    model = WhisperModel(args.model, device='cpu', compute_type='int8')
    segments, _ = model.transcribe(str(args.input), language=args.language, word_timestamps=True)
    result = []
    for segment in segments:
        words = segment.words or []
        if args.format == 'pronin':
            result.extend({'word': word.word.strip(), 'start': round(word.start, 3),
                           'end': round(word.end, 3)} for word in words if word.word.strip())
        else:
            for start in range(0, len(words), args.words):
                group = words[start:start + args.words]
                result.append({'start': round(group[0].start, 3), 'end': round(group[-1].end, 3),
                               'text': ''.join(word.word for word in group).strip()})
    if not result:
        raise ValueError('Whisper не нашёл речь с таймингами в этом файле.')
    document = {'words': result} if args.format == 'pronin' else result
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def smooth(args, output, work):
    if args.rife:
        if not args.rife_model or not args.rife_model.is_dir():
            raise ValueError('Для RIFE укажите папку модели через --rife-model.')
        frames_in, frames_out = work / 'input', work / 'output'
        frames_in.mkdir()
        frames_out.mkdir()
        ffmpeg('-i', args.input, '-map', '0:v:0', '-threads', 1, frames_in / '%08d.png')
        duration = float(media_info(args.input)['format']['duration'])
        count = max(2, round(duration * args.fps))
        subprocess.run([str(args.rife.resolve(strict=True)), '-i', str(frames_in), '-o', str(frames_out),
                        '-m', str(args.rife_model.resolve(strict=True)), '-n', str(count), '-j', '1:2:2'], check=True)
        files = sorted(frames_out.glob('*.png'))
        if len(files) != count:
            raise RuntimeError(f'RIFE создал {len(files)} кадров вместо {count}.')
        # RIFE builds may start numbering their PNGs at zero or one.
        ffmpeg('-framerate', args.fps, '-start_number', int(files[0].stem),
               '-i', frames_out / '%08d.png', '-i', args.input, '-map', '0:v:0', '-map', '1:a:0?',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-t', duration, output)
    else:
        duration = float(media_info(args.input)['format']['duration'])
        ffmpeg('-i', args.input, '-map', '0:v:0', '-map', '0:a:0?',
               '-vf', f'tpad=stop_mode=clone:stop_duration=0.2,minterpolate=fps={args.fps}',
               '-t', duration, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', output)


def sound(effect, output):
    rate = 48000
    duration = {'pop': 0.17, 'chime': 0.42, 'swoosh': 0.33}[effect]
    count = round(rate * duration)
    samples = array('h')
    rng = random.Random(11)
    lowpass = 0
    for index in range(count):
        t = index / rate
        envelope = math.sin(math.pi * index / count) ** 1.5
        if effect == 'swoosh':
            lowpass = 0.85 * lowpass + 0.15 * rng.uniform(-1, 1)
            value = lowpass * envelope
        else:
            frequency = 460 if effect == 'pop' else 740
            value = math.sin(2 * math.pi * frequency * t) * envelope
            if effect == 'chime':
                value = 0.65 * value + 0.35 * math.sin(2 * math.pi * 1108 * t) * envelope
        samples.append(round(value * 10000))
    with wave.open(str(output), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        if sys.byteorder == 'big':
            samples.byteswap()
        stream.writeframes(samples.tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    draw = commands.add_parser('image')
    draw.add_argument('output', type=Path)
    draw.add_argument('--prompt', required=True)
    draw.add_argument('--width', type=int, default=768)
    draw.add_argument('--height', type=int, default=1344)
    draw.add_argument('--seed', type=int, default=7)
    draw.add_argument('--reference', type=Path)
    draw.add_argument('--comfy', type=Path)
    draw.add_argument('--url', default='http://127.0.0.1:8188')
    cut = commands.add_parser('cutout')
    cut.add_argument('input', type=Path)
    cut.add_argument('output', type=Path)
    cut.add_argument('--color', default='ffffff')
    cut.add_argument('--similarity', type=float, default=0.12)
    words = commands.add_parser('captions')
    words.add_argument('input', type=Path)
    words.add_argument('output', type=Path)
    words.add_argument('--language', default='ru')
    words.add_argument('--model', choices=['tiny', 'base', 'small', 'medium'], default='small')
    words.add_argument('--words', type=int, choices=range(1, 7), default=3)
    words.add_argument('--format', choices=['reel-studio', 'pronin'], default='reel-studio')
    motion = commands.add_parser('smooth')
    motion.add_argument('input', type=Path)
    motion.add_argument('output', type=Path)
    motion.add_argument('--fps', type=int, choices=[30, 60], default=30)
    motion.add_argument('--rife', type=Path)
    motion.add_argument('--rife-model', type=Path)
    fx = commands.add_parser('sound')
    fx.add_argument('effect', choices=['pop', 'swoosh', 'chime'])
    fx.add_argument('output', type=Path)
    args = parser.parse_args()
    target = args.output.resolve()
    suffix = {'image': '.png', 'cutout': '.png', 'captions': '.json', 'smooth': '.mp4', 'sound': '.wav'}
    if target.exists() or target.suffix.lower() != suffix[args.command]:
        raise ValueError(f'Укажите новый файл с расширением {suffix[args.command]}.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='reel-tools-', dir=target.parent) as directory:
        work = Path(directory)
        output = work / target.name
        if args.command == 'image':
            image(args, output)
        elif args.command == 'captions':
            captions(args, output)
        elif args.command == 'cutout':
            if not re.fullmatch('[0-9a-fA-F]{6}', args.color) or not 0.01 <= args.similarity <= 1:
                raise ValueError('Укажите цвет RRGGBB и similarity от 0.01 до 1.')
            ffmpeg('-i', args.input, '-vf', f'format=rgba,colorkey=0x{args.color}:{args.similarity}:0.04',
                   '-frames:v', 1, '-threads', 1, output)
        elif args.command == 'smooth':
            smooth(args, output, work)
        else:
            sound(args.effect, output)
        if target.exists():
            raise FileExistsError(target)
        output.rename(target)
    print(target)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

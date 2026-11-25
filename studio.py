"""Local reel builder for user-owned assets."""
import argparse
from array import array
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from ltx import workflow

ROOT = Path(__file__).resolve().parent
REMOTION = ROOT / 'remotion'
FORMATS_2D = ('classic', 'white-background', 'comic', 'cartoon-story')
STUDENT_FORMATS = ('classic', 'white-background', 'comic', 'talk')
DEMO_MEDIA = ROOT / 'examples' / 'first-reel'


def ffmpeg(*args, cwd=None):
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-y', *map(str, args)], check=True, cwd=cwd)


def media_info(path):
    return json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]
    ))


def request(base, route, body=None):
    req = Request(base + route, json.dumps(body).encode() if body is not None else None,
                  {'Content-Type': 'application/json'})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def animate(image, audio, prompt, destination, comfy, url, work, seed, strength):
    tag = uuid.uuid4().hex
    prefix = f'studio_{tag}'
    # Normalize user media before handing it to ComfyUI.
    still = comfy / 'input' / f'ia2v_{tag}.png'
    speech = comfy / 'input' / f'ia2v_{tag}.wav'
    completed = False
    try:
        ffmpeg('-i', image, '-frames:v', 1, '-threads', 1, still)
        ffmpeg('-i', audio, '-vn', '-ac', 1, '-ar', 44100, speech)
        seconds = float(media_info(speech)['format']['duration'])
        graph = workflow(prompt, tag, prefix, seconds, seed, strength)
        job = request(url, '/prompt', {'prompt': graph})['prompt_id']
        print(f'ComfyUI: {job}', flush=True)
        deadline = time.monotonic() + 7200
        while time.monotonic() < deadline:
            status = request(url, f'/history/{job}').get(job, {}).get('status', {})
            if status.get('status_str') == 'error':
                raise RuntimeError(f'ComfyUI: {status.get("messages", [])[-1:]}')
            if status.get('completed'):
                break
            time.sleep(5)
        else:
            raise TimeoutError(f'ComfyUI не завершил задачу {job} за два часа')
        files = sorted((comfy / 'output').glob(f'{prefix}_*.png'))
        if not files:
            raise RuntimeError('Готовые кадры не найдены. Проверьте папку output ComfyUI.')
        for index, frame in enumerate(files):
            shutil.copyfile(frame, work / f'frame{index:05d}.png')
        ffmpeg('-framerate', 24, '-i', work / 'frame%05d.png', '-i', speech,
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', destination)
        completed = True
    finally:
        # Retain inputs if ComfyUI could still be reading them after an error or timeout.
        if completed:
            still.unlink(missing_ok=True)
            speech.unlink(missing_ok=True)
            for frame in files:
                frame.unlink()


def timestamp(seconds):
    centiseconds = round(seconds * 100)
    return f'{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}'


def captions_file(path, captions):
    lines = [
        '[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1080', 'PlayResY: 1920',
        '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        'Style: Default,Arial,56,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,90,90,350,1',
        '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    for start, end, caption in captions:
        caption = caption.translate(str.maketrans({'{': '', '}': '', '\\': '/', '\n': ' ', '\r': ' '}))
        lines.append(f'Dialogue: 0,{timestamp(start)},{timestamp(end)},Default,,0,0,0,,{caption}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def remotion_installed():
    return all((REMOTION / 'node_modules' / '@remotion' / package / 'package.json').is_file()
               for package in ('renderer', 'fonts'))


def check_remotion():
    if not shutil.which('node'):
        raise RuntimeError('Для Remotion установите Node.js 22+ по инструкции SETUP.txt.')
    version = subprocess.check_output(['node', '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 22:
        raise RuntimeError(f'Установлен Node.js {version}. Для Remotion требуется версия 22 или новее.')
    if not remotion_installed():
        raise RuntimeError('Установите Remotion командой npm ci --prefix remotion из папки проекта.')


def export_remotion(work, public, scenes, music, spec, music_volume):
    if music:
        duration = sum(scene['frames'] for scene in scenes) / 30
        ffmpeg('-i', music, '-vn', '-t', duration, '-c:a', 'aac', public / 'music.m4a')
    props = {
        'scenes': scenes,
        'music': 'music.m4a' if music else None,
        'musicVolume': music_volume,
        'captionStyle': spec.get('captionStyle', 'clean'),
        'transition': spec.get('transition', 'cut'),
    }
    props_file = work / 'remotion-props.json'
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding='utf-8')
    print('Монтаж и экспорт: Remotion', flush=True)
    subprocess.run(['node', str(REMOTION / 'render.mjs'), str(props_file),
                    str(public), str(work / 'result.mp4'), str(work / 'bundle')], check=True)


def export_ffmpeg(work, public, scenes, music, music_volume):
    captions = []
    elapsed_frames = 0
    for scene in scenes:
        end = elapsed_frames + scene['frames']
        if scene.get('caption'):
            captions.append((elapsed_frames / 30, end / 30, scene['caption']))
        elapsed_frames = end
    (work / 'clips.txt').write_text(
        ''.join(f"file '{(public / scene['src']).relative_to(work).as_posix()}'\n"
                for scene in scenes), encoding='ascii')
    ffmpeg('-f', 'concat', '-safe', 1, '-i', 'clips.txt', '-c', 'copy', 'joined.mp4', cwd=work)
    args = ['-i', 'joined.mp4']
    if music:
        args += ['-stream_loop', -1, '-i', music]
    if captions:
        captions_file(work / 'captions.ass', captions)
        args += ['-vf', 'ass=captions.ass', '-c:v', 'libx264', '-pix_fmt', 'yuv420p']
    else:
        args += ['-c:v', 'copy']
    if music:
        args += ['-filter_complex',
                 f'[1:a]volume={music_volume}[music];[0:a][music]amix=inputs=2:duration=first:normalize=0[a]',
                 '-map', '0:v:0', '-map', '[a]', '-c:a', 'aac']
    else:
        args += ['-c:a', 'copy']
    ffmpeg(*args, '-movflags', '+faststart', 'result.mp4', cwd=work)


def media_path(project, name):
    return (project.parent / name).resolve(strict=True)


def stage_image(project, name, destination):
    ffmpeg('-i', media_path(project, name), '-frames:v', 1,
           '-pix_fmt', 'rgba', '-threads', 1, destination)
    return destination.name


def stage_audio(source, destination):
    ffmpeg('-i', source, '-vn', '-c:a', 'aac', destination)
    return destination.name


def mouth_frames(voice, frames):
    samples_per_frame = 400
    pcm = subprocess.check_output([
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(voice),
        '-vn', '-ac', '1', '-ar', '12000', '-f', 's16le', '-',
    ])
    samples = array('h', pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    levels = []
    for start in range(0, min(len(samples), frames * samples_per_frame), samples_per_frame):
        span = samples[start:start + samples_per_frame]
        levels.append(math.sqrt(sum(sample * sample for sample in span) / len(span)))
    if not levels:
        return []
    sorted_levels = sorted(levels)
    voice_level = sorted_levels[int((len(sorted_levels) - 1) * 0.82)]
    quiet = max(70, voice_level * 0.11)
    return [0 if level < quiet else 1 if level < voice_level * 0.62 else 2
            for level in levels]


def frame_number(seconds):
    value = float(seconds)
    if not math.isfinite(value) or value < 0:
        raise ValueError('Тайминг должен быть неотрицательным числом.')
    return round(value * 30)


def scene_overlays(project, scene, public, index, frames):
    if 'captionsFile' in scene and 'cues' in scene:
        raise ValueError('Укажите cues или captionsFile, одно поле на сцену.')
    cues = scene.get('cues', [])
    if scene.get('captionsFile'):
        cues = json.loads(media_path(project, scene['captionsFile']).read_text(encoding='utf-8-sig'))
    result = {
        'caption': scene.get('caption'),
        'motion': scene.get('motion', 'none'),
        'cues': [
            {'fromFrame': frame_number(cue['start']), 'toFrame': frame_number(cue['end']), 'text': cue['text']}
            for cue in cues
        ],
    }
    if result['motion'] not in {'none', 'push', 'pull', 'pan'}:
        raise ValueError('Движение должно быть none, push, pull или pan.')
    if scene.get('badge'):
        badge = scene['badge']
        result['badge'] = {'text': badge['text'], 'icon': badge.get('icon', 'spark'),
                           'fromFrame': frame_number(badge.get('start', 0)),
                           'toFrame': frame_number(badge['end']) if 'end' in badge else frames}
    if scene.get('sticker'):
        result['sticker'] = stage_image(project, scene['sticker'], public / f'sticker{index}.png')
    if scene.get('sound'):
        result['sound'] = stage_audio(media_path(project, scene['sound']), public / f'sound{index}.m4a')
        result['soundFrom'] = frame_number(scene.get('soundAt', 0))
        volume = float(scene.get('soundVolume', 0.45))
        if not 0 <= volume <= 1:
            raise ValueError('soundVolume должен быть числом от 0 до 1.')
        result['soundVolume'] = volume
    return result


def classic_beat(scene):
    beat = scene.get('classic')
    if not isinstance(beat, dict) or beat.get('kind') not in {
            'hero', 'illustration', 'compare', 'total', 'steps', 'poll'}:
        raise ValueError('Для classic укажите classic.kind: hero, illustration, compare, total, steps или poll.')
    kind = beat['kind']
    limits = {'label': 46, 'before': 12, 'after': 12, 'value': 12, 'formula': 34}
    required = {'compare': ('before', 'after'), 'total': ('value',)}.get(kind, ())
    for key, maximum in limits.items():
        if key in required or key in beat:
            value = beat.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                raise ValueError(f'В classic.{key} нужна строка до {maximum} символов.')
    if kind == 'illustration' and not (scene.get('art') or scene.get('imagePrompt')):
        raise ValueError('Для classic illustration нужно art или imagePrompt.')
    if kind == 'steps':
        diagram = scene.get('diagram', {})
        steps = diagram.get('steps') if isinstance(diagram, dict) else None
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3 or not all(
                isinstance(step, str) and 1 <= len(step.strip()) <= 45 for step in steps):
            raise ValueError('Для classic steps нужны от одного до трёх коротких diagram.steps.')
    if 'revealAt' in beat:
        frame_number(beat['revealAt'])
    return beat


def stage_graphic_or_sprite(project, scene, kind, public, index, voice, frames):
    result = {'kind': kind, 'frames': frames}
    if voice:
        result['voice'] = stage_audio(voice, public / f'voice{index}.m4a')
        result['voiceFrames'] = frame_number(media_info(voice)['format']['duration'])
        if kind == 'sprite':
            result['mouthFrames'] = mouth_frames(voice, frames)
    if kind == 'graphic':
        data = scene['graphic']
        if not data.get('title') or len(data.get('items', [])) > 5:
            raise ValueError('У графической сцены нужен заголовок и максимум пять строк.')
        result['graphic'] = data
    else:
        result['src'] = stage_image(project, scene['media'], public / f'character{index}.png')
        mouths = scene.get('mouths', [])
        if not mouths:
            raise ValueError('Для sprite укажите минимум одну картинку открытого рта в mouths.')
        result['mouths'] = [
            stage_image(project, image, public / f'mouth{index}_{pose}.png')
            for pose, image in enumerate(mouths)
        ]
        result['background'] = scene.get('background', '#172534')
        if scene.get('layout'):
            if scene['layout'] not in FORMATS_2D:
                raise ValueError(f"Неизвестный 2D-формат: {scene['layout']}")
            result.update(layout=scene['layout'], panel=scene.get('panel', index + 1),
                          heading=scene.get('heading'), gesture=scene.get('gesture', 'idle'),
                          lockHead=scene.get('lockHead') is True)
            if scene['layout'] == 'classic':
                result['classic'] = classic_beat(scene)
                if result['classic']['kind'] == 'illustration' and not scene.get('art'):
                    raise ValueError('В project.json для classic illustration нужен готовый файл art.')
            if scene.get('diagram'):
                result['diagram'] = scene['diagram']
            if scene.get('art'):
                result['art'] = stage_image(project, scene['art'], public / f'art{index}.png')
    return result


def render(project, output, comfy, url, renderer='remotion'):
    if output.suffix.lower() != '.mp4':
        raise ValueError('Имя результата должно оканчиваться на .mp4.')
    if output.exists():
        raise FileExistsError(f'Результат уже существует: {output}. Выберите другое имя.')
    spec = json.loads(project.read_text(encoding='utf-8-sig'))
    scenes = spec['scenes']
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('Добавьте хотя бы одну сцену.')
    if renderer == 'remotion':
        check_remotion()
    music = media_path(project, spec['music']) if spec.get('music') else None
    audio_mix = spec.get('audioMix', 'legacy')
    if audio_mix not in {'legacy', 'dialogue', 'classic'}:
        raise ValueError('audioMix должен быть legacy, dialogue или classic.')
    render_music = music if audio_mix == 'legacy' else None
    music_volume = float(spec.get('musicVolume', 0.12))
    if not 0 <= music_volume <= 1:
        raise ValueError('musicVolume должен быть числом от 0 до 1.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='reel-studio-', dir=output.parent) as directory:
        work = Path(directory)
        public = work / 'media'
        public.mkdir()
        if any(scene.get('layout') == 'classic' for scene in scenes):
            for source, name in (('smoke-puff.png', 'smoke.png'),
                                 ('neucha-cyrillic.woff2', 'neucha-cyrillic.woff2'),
                                 ('neucha-latin.woff2', 'neucha-latin.woff2')):
                shutil.copyfile(ROOT / 'assets' / 'classic' / source, public / f'classic-{name}')
        montage = []
        for index, scene in enumerate(scenes):
            kind = scene.get('kind', 'video')
            if kind not in {'video', 'image', 'ltx', 'graphic', 'sprite'}:
                raise ValueError(f'Неизвестный тип сцены: {kind}')
            if renderer == 'ffmpeg' and kind in {'graphic', 'sprite'}:
                raise ValueError(f'Для сцен {kind} нужен Remotion.')
            media = media_path(project, scene['media']) if kind != 'graphic' else None
            voice = media_path(project, scene['voice']) if scene.get('voice') else None
            print(f'Сцена {index + 1}/{len(scenes)}: {kind}', flush=True)
            if kind == 'ltx':
                if not comfy or not voice:
                    raise ValueError('Для LTX нужны --comfy и файл voice в сцене.')
                animated = work / f'animated{index}.mp4'
                frame_dir = work / f'frames{index}'
                frame_dir.mkdir()
                animate(media, voice, scene['prompt'], animated, comfy, url, frame_dir,
                        int(scene.get('seed', 2)), float(scene.get('strength', 0.5)))
                media, kind, voice = animated, 'video', None
            video = media_info(media) if kind == 'video' else None
            duration = float(scene['seconds']) if 'seconds' in scene else (
                float(media_info(voice)['format']['duration']) if voice else
                float(video['format']['duration']) if video else 3)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError('Длительность сцены должна быть положительным числом.')
            frames = math.ceil(duration * 30)
            duration = frames / 30
            overlays = (scene_overlays(project, scene, public, index, frames) if renderer == 'remotion'
                        else {'caption': scene.get('caption')})
            if kind in {'graphic', 'sprite'}:
                staged = stage_graphic_or_sprite(project, scene, kind, public, index, voice, frames)
                montage.append({**staged, **overlays})
                continue
            args = ['-loop', 1, '-framerate', 30] if kind == 'image' else []
            args += ['-i', media]
            if voice:
                args += ['-i', voice]
                audio_map = '1:a:0'
            elif video and any(s['codec_type'] == 'audio' for s in video['streams']):
                audio_map = '0:a:0'
            else:
                args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                audio_map = '1:a:0'
            framing = scene.get('framing', spec.get('framing', 'cover'))
            if framing == 'contain':
                fit = 'scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2'
            elif framing == 'cover':
                fit = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
            else:
                raise ValueError(f'Неизвестное кадрирование: {framing}')
            ffmpeg(*args, '-map', '0:v:0', '-map', audio_map, '-t', f'{duration:.6f}',
                   '-vf', f'{fit},setsar=1,fps=30,tpad=stop_mode=clone:stop_duration={duration}',
                   '-af', 'apad', '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                   '-g', 30, '-bf', 0, '-video_track_timescale', 90000,
                   '-c:a', 'aac', '-ar', 48000, '-ac', 2, public / f'scene{index}.mp4')
            montage.append({'kind': 'video', 'src': f'scene{index}.mp4', 'frames': frames, **overlays})
        if renderer == 'remotion':
            export_remotion(work, public, montage, render_music, spec, music_volume)
        else:
            export_ffmpeg(work, public, montage, render_music, music_volume)
        result = work / 'result.mp4'
        if audio_mix != 'legacy':
            from soundtrack import master_audio
            mastered = work / 'mastered.mp4'
            master_audio(result, music, music_volume, mastered, duck=audio_mix == 'dialogue')
            result = mastered
        os.replace(result, output)
    print(output)


def init_project(project, template):
    if project.exists():
        raise FileExistsError(f'Проект уже существует: {project}.')
    contents = template.read_text(encoding='utf-8')
    spec = json.loads(contents)
    references = [spec.get('music')]
    for scene in spec['scenes']:
        references.extend(scene.get(field) for field in ('media', 'voice', 'art', 'sound'))
        references.extend(scene.get('mouths', []))
    project.parent.mkdir(parents=True, exist_ok=True)
    for name in dict.fromkeys(name for name in references if name):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Укажите путь к учебному материалу внутри проекта: {name}')
        source = DEMO_MEDIA / relative
        if not source.is_file():
            source = ROOT / relative
        destination = project.parent / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_demo_asset(source, destination)
    with project.open('x', encoding='utf-8') as target:
        target.write(contents)
    print(project.resolve())


def copy_demo_asset(source, destination):
    if not Path(destination).exists():
        shutil.copyfile(source, destination)


def install_remotion():
    if platform.system() not in {'Windows', 'Darwin'}:
        raise RuntimeError('Ученический запуск рассчитан на Windows и macOS.')
    for executable in ('node', 'ffmpeg', 'ffprobe'):
        if not shutil.which(executable):
            raise RuntimeError(f'Не найден {executable}. Установите зависимости по SETUP.txt.')
    if not remotion_installed():
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('Не найден npm. Установите Node.js с npm по SETUP.txt.')
        print('Устанавливаю зависимости Remotion', flush=True)
        subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=REMOTION, check=True)
    check_remotion()


def quickstart(output_dir, selected):
    install_remotion()
    for name in (STUDENT_FORMATS if selected == 'all' else (selected,)):
        project = output_dir / name / 'project.json'
        output = project.with_name(name + '.mp4')
        if not project.exists():
            init_project(project, ROOT / 'formats' / (name + '.json'))
        if output.exists():
            print(f'Готовый ролик уже существует: {output}', flush=True)
            continue
        render(project, output, None, '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    init = commands.add_parser('init')
    init.add_argument('project', type=Path)
    init.add_argument('--format', choices=STUDENT_FORMATS,
                      default='white-background')
    start = commands.add_parser('quickstart', help='Собрать учебные примеры')
    start.add_argument('--format', choices=['all', *STUDENT_FORMATS], default='all')
    start.add_argument('--output-dir', type=Path, default=ROOT / '2d-output')
    make = commands.add_parser('produce', help='Собрать один ролик или пачку по плану агента')
    make.add_argument('brief', type=Path)
    make.add_argument('--output-dir', type=Path, default=ROOT / 'output')
    make.add_argument('--comfy', type=Path)
    build = commands.add_parser('render')
    build.add_argument('project', type=Path)
    build.add_argument('output', type=Path)
    build.add_argument('--comfy', type=Path, help='Корневая папка ComfyUI')
    build.add_argument('--url', default='http://127.0.0.1:8188')
    build.add_argument('--renderer', choices=['remotion', 'ffmpeg'], default='remotion')
    args = parser.parse_args()
    if args.command == 'doctor':
        print(f'{platform.system()} {platform.machine()}')
        missing = []
        for name in ('ffmpeg', 'ffprobe'):
            found = shutil.which(name)
            print(f'{name}: {found or "не найден"}')
            if not found:
                missing.append(name)
        try:
            check_remotion()
            print('Remotion: зависимости установлены')
        except RuntimeError as error:
            print(error)
            missing.append('remotion')
        if missing:
            raise SystemExit(1)
    elif args.command == 'init':
        init_project(args.project, ROOT / 'formats' / f'{args.format}.json')
    elif args.command == 'quickstart':
        quickstart(args.output_dir.resolve(), args.format)
    elif args.command == 'produce':
        from produce import produce
        produce(args.brief.resolve(), args.output_dir.resolve(),
                args.comfy.resolve() if args.comfy else None)
    else:
        render(args.project.resolve(), args.output.resolve(),
               args.comfy.resolve() if args.comfy else None, args.url.rstrip('/'), args.renderer)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))

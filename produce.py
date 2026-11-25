"""Build one or more short reels from a plan written by the coding agent."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from provision import CAST, cast_profile, speak
from studio import FORMATS_2D, ROOT, STUDENT_FORMATS, classic_beat, ffmpeg, install_remotion, media_info, render, request

VOICEBOX = 'http://127.0.0.1:17493'
CHARACTERS = {'panther': 'Ono_Anna', 'tigress': 'Vivian', 'wolf': 'Ryan'}
POSES = ('idle.png', 'mouth-small.png', 'mouth-open.png')
GRAPHIC_FORMATS = {'explainer': 'cards', 'comparison': 'bars', 'timeline': 'timeline', 'kinetic': 'title'}
FORMATS = {*FORMATS_2D, *GRAPHIC_FORMATS, 'story', 'demo', 'talk', 'dialog'}


def pick_voice(voice, actor, language):
    profile_name = voice.get('profile')
    preset = voice.get('preset')
    cast = voice.get('cast') or (actor if actor in CAST else 'panther')
    if sum(bool(voice.get(key)) for key in ('profile', 'preset', 'cast')) > 1:
        raise ValueError('В voice выберите одно поле: profile, cast или preset.')
    try:
        profiles = request(VOICEBOX, '/profiles')
    except OSError as error:
        raise RuntimeError('Откройте Voicebox и запустите локальный сервер. См. SETUP.txt.') from error
    if isinstance(profiles, dict):
        profiles = profiles['profiles']
    if profile_name:
        matches = [p for p in profiles if profile_name in (p.get('name'), p.get('id'))]
        if len(matches) != 1:
            raise ValueError(f'Нужен один профиль Voicebox с именем или ID «{profile_name}».')
        return matches[0]['id'], voice.get('engine')
    if not preset and (language == 'ru' or voice.get('cast')):
        return cast_profile(VOICEBOX, cast, profiles), voice.get('engine', 'qwen')
    preset = preset or CHARACTERS.get(actor, 'Ono_Anna')
    existing = next((p for p in profiles if p.get('preset_engine') == 'qwen_custom_voice'
                     and str(p.get('preset_voice_id', '')).casefold() == preset.casefold()), None)
    if existing is None:
        existing = request(VOICEBOX, '/profiles', {
            'name': f'Reel Studio · {preset}', 'language': language, 'voice_type': 'preset',
            'preset_engine': 'qwen_custom_voice', 'preset_voice_id': preset,
            'default_engine': 'qwen_custom_voice',
        })
    return existing['id'], 'qwen_custom_voice'


def stage(source, target):
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='asset-', dir=target.parent) as directory:
            staged = Path(directory) / target.name
            shutil.copyfile(source.resolve(strict=True), staged)
            staged.replace(target)
    return target.name


def diagram(data):
    if not isinstance(data, dict):
        raise ValueError('diagram должен быть объектом со steps или value.')
    steps = data.get('steps')
    if steps is not None:
        if not isinstance(steps, list) or not 1 <= len(steps) <= 3 or not all(
                isinstance(step, str) and 0 < len(step.strip()) <= 45 for step in steps):
            raise ValueError('diagram.steps должен содержать от одного до трёх коротких шагов.')
    elif not isinstance(data.get('value'), str) or not 0 < len(data['value'].strip()) <= 26:
        raise ValueError('Для диаграммы задайте steps или короткое текстовое значение value.')
    if 'label' in data and (not isinstance(data['label'], str) or len(data['label']) > 60):
        raise ValueError('diagram.label должен быть строкой не длиннее 60 знаков.')
    return data


def stage_media(source, target, name, stem):
    media = source / name
    return stage(media, target / f'{stem}{media.suffix.lower()}')


def build_picture(scene, source, folder, number, comfy, layout):
    if scene.get('art'):
        return stage_media(source, folder, scene['art'], f'art-{number:02}')
    if not scene.get('imagePrompt'):
        return None
    picture = folder / f'art-{number:02}.png'
    if not picture.exists():
        width, height = ('768', '1344') if layout == 'talk' else ('832', '624')
        command = [sys.executable, str(ROOT / 'media_tools.py'), 'image', str(picture),
                   '--prompt', scene['imagePrompt'], '--comfy', str(comfy),
                   '--width', width, '--height', height]
        if scene.get('imageReference'):
            command.extend(['--reference', str((source / scene['imageReference']).resolve(strict=True))])
        subprocess.run(command, check=True)
    return picture.name


def build_visual(scene, layout, source, folder, number, comfy, poses):
    if layout in GRAPHIC_FORMATS:
        graphic = {'variant': GRAPHIC_FORMATS[layout], 'title': scene.get('caption') or scene['say']}
        graphic.update(scene.get('graphic', {}))
        return {'kind': 'graphic', 'graphic': graphic}
    if scene.get('video') and layout not in FORMATS_2D:
        media = stage_media(source, folder, scene['video'], f'clip-{number:02}')
        return {'kind': 'video', 'media': media}
    picture = (stage_media(source, folder, scene['portrait'], f'portrait-{number:02}')
               if layout == 'talk' and scene.get('portrait')
               else build_picture(scene, source, folder, number, comfy, layout))
    if layout in FORMATS_2D:
        visual = {'kind': 'sprite', 'layout': layout, 'media': poses[0], 'mouths': poses[1:]}
        if picture:
            visual['art'] = picture
        for key in ('diagram', 'heading', 'gesture', 'panel', 'classic'):
            if key in scene:
                visual[key] = scene[key]
        return visual
    if layout == 'talk':
        return {'kind': 'ltx', 'media': picture, 'prompt': scene['prompt'],
                'seed': scene.get('seed', 2), 'strength': scene.get('strength', 0.5)}
    return {'kind': 'image', 'media': picture}


def validate_scene(scene, layout, comfy):
    if not isinstance(scene, dict) or not isinstance(scene.get('say'), str) or not scene['say'].strip():
        raise ValueError('В каждой сцене нужен непустой текст say.')
    if layout == 'classic':
        classic_beat(scene)
    if layout in GRAPHIC_FORMATS:
        graphic = scene.get('graphic', {})
        if not isinstance(graphic, dict) or not isinstance(graphic.get('items', []), list):
            raise ValueError('В графической сцене graphic должен быть объектом, а items списком.')
        return
    if layout not in FORMATS_2D and scene.get('video'):
        return
    if layout == 'talk':
        if comfy is None or not isinstance(scene.get('prompt'), str) or not scene['prompt'].strip():
            raise ValueError('Для оживления портрета в talk нужны --comfy и prompt. Для готового клипа укажите video.')
        if not any(scene.get(key) for key in ('portrait', 'art', 'imagePrompt')):
            raise ValueError('Добавьте в talk портрет, иллюстрацию или imagePrompt.')
    if scene.get('imagePrompt') and not scene.get('art') and not scene.get('portrait') and comfy is None:
        raise ValueError('Для imagePrompt укажите --comfy или приложите иллюстрацию.')
    if layout in ('story', 'demo') and not (scene.get('art') or scene.get('imagePrompt')):
        raise ValueError(f'В сцене {layout} нужен клип video, иллюстрация art или imagePrompt.')
    if 'diagram' in scene:
        diagram(scene['diagram'])


def stage_character(character, source, folder, prefix=''):
    sprites = ROOT / 'characters' / character if character in CHARACTERS else source / character
    return [stage(sprites / name, folder / (prefix + name)) for name in POSES]


def arrange_classic_voice(source, target, tempo):
    if not math.isfinite(tempo) or not 0.85 <= tempo <= 1.40:
        raise ValueError('voiceTempo должен быть числом от 0.85 до 1.40.')
    trim = ('silenceremove=start_periods=1:start_duration=0.025:'
            'start_threshold=-43dB:start_silence=0.04')
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        staged = Path(folder) / target.name
        pauses = ('silenceremove=stop_periods=-1:stop_duration=0.24:'
                  'stop_threshold=-43dB:stop_silence=0.14')
        ffmpeg('-i', source, '-vn', '-af',
               f'{trim},areverse,{trim},areverse,{pauses},atempo={tempo},apad=pad_dur=0.08', staged)
        staged.replace(target)


def build_reel(brief, source, folder, comfy):
    reel_format = brief.get('format', 'white-background')
    if reel_format not in FORMATS:
        raise ValueError(f'Неизвестный формат: {reel_format}. Учебные форматы: {", ".join(STUDENT_FORMATS)}.')
    dialogue = reel_format == 'dialog'
    layout = 'white-background' if dialogue else reel_format
    character = brief.get('character', 'panther')
    scenes = brief.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('Добавьте хотя бы одну сцену в scenes.')
    for scene in scenes:
        validate_scene(scene, layout, comfy)
        if dialogue and (not isinstance(scene.get('character'), str) or not scene['character'].strip()):
            raise ValueError('Для dialog укажите character в каждой сцене.')
    signature = {'assetBase': str(source), 'brief': brief}
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder / 'brief.json'
    if saved.exists():
        if json.loads(saved.read_text(encoding='utf-8')) != signature:
            raise ValueError(f'Этот id уже занят другим планом: {folder.name}. Задайте новый id.')
    else:
        with saved.open('x', encoding='utf-8') as file:
            json.dump(signature, file, ensure_ascii=False, indent=2)
    output = folder / 'result.mp4'
    if output.exists():
        print(f'Уже готово: {output}', flush=True)
        return
    cast = {}
    if dialogue:
        for index, name in enumerate(dict.fromkeys(scene['character'] for scene in scenes), 1):
            cast[name] = stage_character(name, source, folder, f'actor-{index}-')
    elif layout in FORMATS_2D:
        cast[character] = stage_character(character, source, folder)
    selected_voices = {}
    classic = layout == 'classic'
    soundtrack = brief.get('music', 'classic' if classic else 'pulse')
    mix = brief.get('audioMix', 'classic' if classic else 'dialogue')
    mix_volumes = {'classic': 0.75, 'dialogue': 0.72, 'legacy': 0.22}
    project = {'scenes': [], 'audioMix': mix, 'musicVolume': brief.get(
        'musicVolume', mix_volumes.get(mix, 0.22))}
    if layout == 'talk':
        project['captionStyle'] = 'talk'
    for key in ('framing', 'transition', 'captionStyle'):
        if key in brief:
            project[key] = brief[key]
    if soundtrack:
        bundled_music = {'pulse': 'pulse-bed.m4a', 'studio': 'studio-bed.m4a', 'classic': 'classic/bed.m4a'}
        song = (ROOT / 'assets' / bundled_music[soundtrack]
                if soundtrack in bundled_music else source / soundtrack)
        project['music'] = stage(song, folder / f'music{song.suffix.lower()}')
    for number, scene in enumerate(scenes, 1):
        spoken = scene['say']
        actor = scene['character'] if dialogue else character
        clip = source / scene['video'] if layout == 'talk' and scene.get('video') else None
        if scene.get('audio'):
            src = source / scene['audio']
            audio = folder / f'voice-{number:02}{src.suffix.lower()}'
            stage(src, audio)
        else:
            audio = folder / f'voice-{number:02}.wav'
            if not audio.exists() and clip and any(
                    s['codec_type'] == 'audio' for s in media_info(clip)['streams']):
                with tempfile.TemporaryDirectory(dir=folder) as directory:
                    extracted = Path(directory) / audio.name
                    ffmpeg('-i', clip, '-map', '0:a:0', '-vn', extracted)
                    extracted.replace(audio)
            if not audio.exists():
                override = scene.get('voice', {})
                voice = {**brief.get('voice', {}), **override}
                selectors = ('profile', 'preset', 'cast')
                if any(field in override for field in selectors):
                    voice = {field: value for field, value in voice.items()
                             if field not in selectors or field in override}
                language = voice.get('language', 'ru')
                key = (actor, language, *(voice.get(field) for field in (*selectors, 'engine')))
                if key not in selected_voices:
                    selected_voices[key] = pick_voice(voice, actor, language)
                profile, engine = selected_voices[key]
                timed = 'cues' in scene or 'captionsFile' in scene
                cut_voice = classic and not timed
                raw = audio.with_name(f'voice-{number:02}-source.wav') if cut_voice else audio
                if not raw.exists():
                    speak(SimpleNamespace(output=raw, profile=profile, engine=engine,
                                          language=language, text=spoken, instruct=voice.get('instruct')), VOICEBOX)
                if cut_voice:
                    default_tempo = 1.18 if number <= 3 else 1.10
                    tempo = float(scene.get('voiceTempo', brief.get('voiceTempo', default_tempo)))
                    arrange_classic_voice(raw, audio, tempo)
        length = float(media_info(audio)['format']['duration'])
        if length <= 0:
            raise ValueError(f'Пустая озвучка сцены {number}.')
        caption = scene.get('caption', spoken)
        next_scene = build_visual(scene, layout, source, folder, number, comfy, cast.get(actor))
        next_scene.update(voice=audio.name, seconds=length)
        if 'captionsFile' in scene:
            if 'cues' in scene:
                raise ValueError('Укажите cues или captionsFile, одно поле на сцену.')
            next_scene['captionsFile'] = stage_media(
                source, folder, scene['captionsFile'], f'captions-{number:02}')
        else:
            next_scene['cues'] = scene.get('cues', [{'start': 0, 'end': length, 'text': caption}])
        if layout in FORMATS_2D:
            next_scene['lockHead'] = brief.get('lockHead', layout == 'white-background')
        for key in ('framing', 'motion', 'badge'):
            if key in scene:
                next_scene[key] = scene[key]
        for field in ('sound', 'sticker'):
            if scene.get(field):
                bundled = {'point': 'point.m4a', 'classic-coin': 'classic/coin.mp3'}
                if field == 'sound' and scene[field] in bundled:
                    file = ROOT / 'assets' / bundled[scene[field]]
                    next_scene[field] = stage(file, folder / file.name)
                else:
                    next_scene[field] = stage_media(source, folder, scene[field], f'{field}-{number:02}')
        for key in ('soundAt', 'soundVolume'):
            if key in scene:
                next_scene[key] = scene[key]
        project['scenes'].append(next_scene)
    spec = folder / 'project.json'
    spec.write_text(json.dumps(project, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if selected_voices and layout == 'talk' and any(scene['kind'] == 'ltx' for scene in project['scenes']):
        try:
            request(VOICEBOX, '/models/unload', {})
        except (OSError, ValueError):
            print('Voicebox: API не подтвердил выгрузку модели перед LTX.', flush=True)
    render(spec, output, comfy, 'http://127.0.0.1:8188')


def produce(plan, output, comfy):
    data = json.loads(plan.read_text(encoding='utf-8-sig'))
    reels = data.get('reels', [data])
    if not isinstance(reels, list) or not reels:
        raise ValueError('План должен содержать один ролик или непустой список reels.')
    ids = [item.get('id', '') for item in reels]
    reserved = {'con', 'prn', 'aux', 'nul', *(f'{p}{i}' for p in ('com', 'lpt') for i in range(10))}
    if any(not isinstance(i, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', i)
           or i in reserved for i in ids):
        raise ValueError('Укажите id из строчных латинских букв, цифр и дефисов.')
    if len(ids) != len(set(ids)):
        raise ValueError('У каждого ролика в пачке должен быть отдельный id.')
    install_remotion()
    for item, name in zip(reels, ids):
        build_reel(item, plan.parent, output / name, comfy)

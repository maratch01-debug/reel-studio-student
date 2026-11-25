"""Mix a music bed under the Remotion narration and master the result."""
import json
import subprocess

from studio import ffmpeg, media_info


def master_audio(source, music, volume, output, *, duck=True):
    print('Сведение звука: FFmpeg', flush=True)
    inputs = ['-i', source]
    streams = media_info(source)['streams']
    video = next(stream for stream in streams if stream['codec_type'] == 'video')
    duration = float(video['duration'])
    has_audio = any(stream['codec_type'] == 'audio' for stream in streams)
    if has_audio:
        narration = '[0:a:0]'
    else:
        inputs += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        narration = '[1:a:0]'
    speech = narration + 'aformat=sample_rates=48000:channel_layouts=stereo,apad'
    if music and volume:
        music_input = 1 if has_audio else 2
        inputs += ['-stream_loop', '-1', '-i', music]
        tail = min(0.42, duration / 3)
        bed = (f'[{music_input}:a:0]aformat=sample_rates=48000:channel_layouts=stereo,'
               f'volume={volume},atrim=0:{duration},afade=t=out:st={duration-tail}:d={tail}[bed];')
        if duck:
            speech += ',asplit=2[voice][key];'
            bed += '[bed][key]sidechaincompress=threshold=0.045:ratio=2.8:attack=14:release=240[ducked];'
        else:
            speech += '[voice];'
        music_label = 'ducked' if duck else 'bed'
        mix = speech + bed + f'[voice][{music_label}]amix=inputs=2:duration=first:normalize=0'
    else:
        mix = speech
    mix += f',atrim=0:{duration}'

    target = 'loudnorm=I=-14:TP=-1.5:LRA=9'
    measure = subprocess.run(
        ['ffmpeg', '-nostdin', '-hide_banner', '-nostats', *map(str, inputs),
         '-filter_complex', mix + ',' + target + ':print_format=json[a]',
         '-map', '[a]', '-f', 'null', '-'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', check=True,
    )
    levels, _ = json.JSONDecoder().raw_decode(measure.stderr[measure.stderr.rindex('{'):])
    if levels['input_i'] != '-inf':
        target += (
            f":measured_I={levels['input_i']}:measured_TP={levels['input_tp']}"
            f":measured_LRA={levels['input_lra']}:measured_thresh={levels['input_thresh']}"
            f":offset={levels['target_offset']}:linear=true"
        )
        mix += ',' + target
    samples = round(duration * 48000)
    mix += f',aresample=48000,apad,atrim=end_sample={samples}[a]'
    ffmpeg(*inputs, '-filter_complex', mix, '-map', '0:v:0', '-map', '[a]',
           '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', output)

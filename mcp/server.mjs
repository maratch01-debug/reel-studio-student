import {spawn, spawnSync} from 'node:child_process';
import {lstat, readFile, realpath, stat} from 'node:fs/promises';
import {delimiter, dirname, extname, isAbsolute, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {z} from 'zod';

const root = await realpath(fileURLToPath(new URL('..', import.meta.url)));
if (process.env.REEL_STUDIO_TOOL_PATH) {
  process.env.PATH = [process.env.REEL_STUDIO_TOOL_PATH, process.env.PATH].filter(Boolean).join(delimiter);
}
const formats = ['classic', 'white-background', 'comic', 'talk'];
const characters = ['panther', 'tigress', 'wolf'];
const workspaceFile = z.string().min(1).describe('Путь к файлу внутри папки Reel Studio.');
const comfyFolder = z.string().min(1).optional().describe('Папка локального ComfyUI для Flux или LTX.');
const reelId = z.string().regex(/^[a-z0-9][a-z0-9-]{0,63}$/);
const server = new McpServer({name: 'reel-studio', version: '1.0.0'}, {
  instructions: 'Работай в локальной папке Reel Studio. Для нового ролика прочитай AGENTS.md и TOOLS.txt, подготовь brief.json, собери ролик и верни MP4 вместе с project.json. Озвучка через Voicebox и анимация через ComfyUI используют локальные сервисы.',
});

function inside(path) {
  const fromRoot = relative(root, path);
  return !isAbsolute(fromRoot) && fromRoot !== '..' && !fromRoot.startsWith('..' + sep);
}

async function workspacePath(value, extension, input = false) {
  const path = resolve(root, value);
  if (!inside(path) || extname(path).toLowerCase() !== extension) {
    throw new Error('Укажите файл ' + extension + ' внутри папки Reel Studio.');
  }
  for (let current = path; current !== root; current = dirname(current)) {
    let entry;
    try {
      entry = await lstat(current);
    } catch (error) {
      if (error.code !== 'ENOENT' || input) throw error;
      continue;
    }
    if (entry.isSymbolicLink() || !inside(await realpath(current))) {
      throw new Error('Путь должен оставаться внутри папки Reel Studio.');
    }
    if (current === path && input && !entry.isFile()) throw new Error('Укажите файл.');
  }
  return path;
}

let python;
function pythonCommand() {
  if (python) return python;
  const configured = process.env.REEL_STUDIO_PYTHON;
  const candidates = [
    ...(configured ? [[configured]] : []),
    ...(process.platform === 'win32' ? [['py', '-3'], ['python']] : [
      ['python3'], ['/opt/homebrew/bin/python3'], ['/usr/local/bin/python3'],
    ]),
  ];
  python = candidates.find(([command, ...args]) => spawnSync(command, [
    ...args, '-c', 'import sys; sys.exit(sys.version_info < (3, 10))',
  ], {stdio: 'ignore', windowsHide: true, timeout: 5000}).status === 0);
  if (!python) throw new Error('Требуется Python 3.10+. Запустите установщик Reel Studio.');
  return python;
}

function run(command, args, signal) {
  return new Promise((done, fail) => {
    const child = spawn(command, args, {
      cwd: root,
      signal,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {...process.env, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1'},
    });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8').on('data', part => { stdout = (stdout + part).slice(-24000); });
    child.stderr.setEncoding('utf8').on('data', part => { stderr = (stderr + part).slice(-12000); });
    child.on('error', fail);
    child.on('close', (code, interrupted) => {
      if (code === 0) done(stdout.trim());
      else fail(new Error([stderr, stdout, `Процесс завершился с кодом ${code ?? interrupted}.`]
        .filter(Boolean).join('\n').trim()));
    });
  });
}

function runPython(script, args, signal) {
  const [command, ...flags] = pythonCommand();
  return run(command, [...flags, resolve(root, script), ...args], signal);
}

function tool(name, description, inputSchema, handler, readOnly = false) {
  server.registerTool(name, {
    description, inputSchema,
    annotations: {readOnlyHint: readOnly, destructiveHint: false, openWorldHint: false},
  }, async (args, context) => {
    try {
      const result = await handler(args, context.signal);
      return {content: [{type: 'text', text: JSON.stringify(result, null, 2)}]};
    } catch (error) {
      return {isError: true, content: [{type: 'text', text: error.message}]};
    }
  });
}

async function serviceUp(url) {
  try {
    return (await fetch(url, {signal: AbortSignal.timeout(1400)})).ok;
  } catch {
    return false;
  }
}

tool('reel_studio_catalog', 'Показывает форматы, голоса и примеры Reel Studio.', {}, async () => ({
  workspace: root,
  formats: [
    {id: 'classic', label: 'Классика', example: 'examples/classic-demo.json'},
    {id: 'white-background', label: 'Белый фон'},
    {id: 'comic', label: 'Комикс'},
    {id: 'talk', label: 'Живой герой', animation: 'Локальный ComfyUI с LTX или готовый клип'},
  ],
  voices: characters.map(id => ({id, sample: `assets/voices/${id}-reference.wav`})),
  music: 'assets/pulse-bed.m4a',
  briefExample: 'examples/classic-demo.json',
  guide: 'TOOLS.txt',
}), true);

tool('reel_studio_doctor', 'Проверяет FFmpeg, Remotion, Voicebox и ComfyUI.', {}, async (_, signal) => {
  const [tools, voicebox, comfyUI] = await Promise.allSettled([
    runPython('studio.py', ['doctor'], signal),
    serviceUp('http://127.0.0.1:17493/health'),
    serviceUp('http://127.0.0.1:8188/system_stats'),
  ]);
  return {
    ready: tools.status === 'fulfilled',
    report: tools.status === 'fulfilled' ? tools.value : tools.reason.message,
    voicebox: voicebox.value,
    comfyUI: comfyUI.value,
  };
}, true);

tool('reel_studio_demo', 'Собирает комплектные демо Reel Studio. Возвращает MP4 и монтажные проекты.', {
  format: z.enum(['all', ...formats]).default('all'),
}, async ({format}, signal) => {
  const output = dirname(await workspacePath('output/mcp-demos/index.json', '.json'));
  await runPython('studio.py', ['quickstart', '--format', format, '--output-dir', output], signal);
  const selected = format === 'all' ? formats : [format];
  return {reels: selected.map(id => ({
    format: id, video: resolve(output, id, id + '.mp4'), project: resolve(output, id, 'project.json'),
  }))};
});

tool('reel_studio_voice', 'Озвучивает русский текст комплектным голосом через локальный Voicebox.', {
  cast: z.enum(characters),
  text: z.string().trim().min(1).max(5000),
  id: reelId,
}, async ({cast, text, id}, signal) => {
  const output = await workspacePath(`output/voice/${id}.wav`, '.wav');
  await runPython('provision.py', ['speak', '--cast', cast, '--text=' + text, output], signal);
  return {wav: output};
});

async function comfyArguments(comfy) {
  if (!comfy) return [];
  const folder = await realpath(resolve(root, comfy));
  if (!(await stat(folder)).isDirectory()) throw new Error('Укажите папку ComfyUI.');
  return ['--comfy', folder];
}

tool('reel_studio_produce', 'Собирает ролики по brief.json. Возвращает MP4 и редактируемые проекты.', {
  brief: workspaceFile,
  comfy: comfyFolder,
}, async ({brief, comfy}, signal) => {
  const input = await workspacePath(brief, '.json', true);
  const output = dirname(await workspacePath('output/reels/index.json', '.json'));
  await runPython('studio.py', ['produce', input, '--output-dir', output,
    ...await comfyArguments(comfy)], signal);
  const plan = JSON.parse((await readFile(input, 'utf8')).replace(/^\uFEFF/, ''));
  return {reels: (plan.reels ?? [plan]).map(({id}) => ({
    id, video: resolve(output, id, 'result.mp4'), project: resolve(output, id, 'project.json'),
  }))};
});

tool('reel_studio_render', 'Экспортирует существующий project.json в новый MP4 после правок монтажа.', {
  project: workspaceFile,
  video: workspaceFile,
  comfy: comfyFolder,
}, async ({project, video, comfy}, signal) => {
  const input = await workspacePath(project, '.json', true);
  const output = await workspacePath(video, '.mp4');
  await runPython('studio.py', ['render', input, output, ...await comfyArguments(comfy)], signal);
  return {video: output, project: input};
});

tool('reel_studio_captions', 'Снимает тайминги русских субтитров с локальной озвучки через Faster Whisper.', {
  audio: workspaceFile,
  id: reelId,
}, async ({audio, id}, signal) => {
  const extension = extname(audio).toLowerCase();
  if (!['.wav', '.m4a', '.mp3', '.flac'].includes(extension)) throw new Error('Нужен WAV, M4A, MP3 или FLAC.');
  const input = await workspacePath(audio, extension, true);
  const output = await workspacePath(`output/captions/${id}.json`, '.json');
  const interpreter = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
  const venv = resolve(root, interpreter);
  const hasVenv = await stat(venv).then(item => item.isFile(), () => false);
  const [command, ...flags] = hasVenv ? [venv] : pythonCommand();
  await run(command, [...flags, resolve(root, 'media_tools.py'), 'captions', input, output], signal);
  return {captions: output};
});

tool('reel_studio_verify', 'Проверяет параметры MP4 и полностью декодирует видео со звуком.', {
  video: workspaceFile,
}, async ({video}, signal) => {
  const file = await workspacePath(video, '.mp4', true);
  const probe = await run('ffprobe', ['-v', 'error', '-show_entries',
    'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate', '-of', 'json', file], signal);
  await run('ffmpeg', ['-nostdin', '-v', 'error', '-xerror', '-i', file, '-f', 'null', '-'], signal);
  return {video: file, decoded: true, ...JSON.parse(probe)};
}, true);

await server.connect(new StdioServerTransport());

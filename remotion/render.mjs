import {existsSync} from 'node:fs';
import {readFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';

const [propsPath, publicDir, output, bundleDir] = process.argv.slice(2);
if (!propsPath || !publicDir || !output || !bundleDir) {
  throw new Error('Usage: node render.mjs <props.json> <public-dir> <output.mp4> <bundle-dir>');
}

const inputProps = JSON.parse(await readFile(propsPath, 'utf8'));
const serveUrl = await bundle({
  entryPoint: fileURLToPath(new URL('./src/index.jsx', import.meta.url)),
  publicDir: resolve(publicDir),
  outDir: resolve(bundleDir),
  enableCaching: false,
});
function findInstalledBrowser() {
  if (process.platform === 'win32') {
    const locations = [process.env.ProgramW6432, process.env.ProgramFiles,
      process.env['ProgramFiles(x86)'], process.env.LOCALAPPDATA].filter(Boolean);
    return locations.flatMap((location) => [
      join(location, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      join(location, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]).find(existsSync);
  }
  return undefined;
}

const browserExecutable = process.env.REEL_BROWSER_EXECUTABLE || findInstalledBrowser();
const composition = await selectComposition({
  serveUrl, inputProps, id: 'Reel', browserExecutable,
});
const classicEncoding = inputProps.scenes.some(scene => scene.layout === 'classic') ? {
  gopSize: 30,
  encodingMaxRate: '3800k',
  encodingBufferSize: '4800k',
  x264Preset: 'fast',
  ffmpegOverride: ({args}) => [...args.slice(0, -1), '-bf', '0', args.at(-1)],
} : {};
await renderMedia({
  serveUrl,
  composition,
  inputProps,
  browserExecutable,
  codec: 'h264',
  audioCodec: 'aac',
  pixelFormat: 'yuv420p',
  outputLocation: resolve(output),
  concurrency: 2,
  disallowParallelEncoding: true,
  ...classicEncoding,
});

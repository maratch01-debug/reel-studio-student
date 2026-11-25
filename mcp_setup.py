"""Generate checkout-local MCP launchers with the tools found by the installer."""
import json
import os
import shutil
import tempfile
from pathlib import Path


CODEX_BEGIN = '# BEGIN REEL STUDIO MCP'
CODEX_END = '# END REEL STUDIO MCP'


def write_config(path, contents):
    if path.exists() and path.read_text(encoding='utf-8') == contents:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        staged = Path(folder) / path.name
        staged.write_text(contents, encoding='utf-8')
        if path.exists():
            staged.chmod(path.stat().st_mode & 0o777)
        staged.replace(path)


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def configure_mcp(root, node, python):
    node = os.path.abspath(node)
    args = [str(root / 'mcp' / 'server.mjs')]
    tool_dirs = dict.fromkeys(Path(path).parent for name in ('node', 'npm', 'ffmpeg', 'ffprobe')
                              if (path := shutil.which(name)))
    env = {
        'REEL_STUDIO_PYTHON': os.path.abspath(python),
        'REEL_STUDIO_TOOL_PATH': os.pathsep.join(map(str, tool_dirs)),
    }
    claude = root / '.mcp.json'
    config = json.loads(claude.read_text(encoding='utf-8')) if claude.exists() else {}
    config.setdefault('mcpServers', {})['reel-studio'] = {
        'type': 'stdio', 'command': node, 'args': args, 'env': env, 'timeout': 10800000,
    }

    codex = root / '.codex' / 'config.toml'
    old = codex.read_text(encoding='utf-8') if codex.exists() else ''
    environment = ', '.join(f'{key} = {quote(value)}' for key, value in env.items())
    block = (
        f'{CODEX_BEGIN}\n'
        '[mcp_servers.reel-studio]\n'
        f'command = {quote(node)}\n'
        f'args = {quote(args)}\n'
        f'cwd = {quote(str(root))}\n'
        f'env = {{ {environment} }}\n'
        'startup_timeout_sec = 20\n'
        'tool_timeout_sec = 10800\n'
        f'{CODEX_END}'
    )
    if CODEX_BEGIN in old and CODEX_END in old:
        before, _, tail = old.partition(CODEX_BEGIN)
        _, _, after = tail.partition(CODEX_END)
        old = before + block + after
    elif 'reel-studio' not in old and CODEX_BEGIN not in old and CODEX_END not in old:
        old = old.rstrip() + ('\n\n' if old.strip() else '') + block + '\n'
    else:
        print('Сохранён ваш существующий блок reel-studio в .codex/config.toml.', flush=True)

    write_config(claude, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    write_config(codex, old)

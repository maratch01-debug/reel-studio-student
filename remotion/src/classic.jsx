import React, {useEffect} from 'react';
import {AbsoluteFill, Easing, Img, cancelRender, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {loadFont} from '@remotion/fonts';

const hand = 'Neucha';
const ink = '#22241f';
const red = '#a24837';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const letters = {fontFamily: 'Neucha, sans-serif', textAlign: 'center', color: ink};

let fontReady;
function loadClassicFont() {
  const cyrillic = 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116';
  const latin = 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD';
  fontReady ??= Promise.all([
    loadFont({family: hand, url: staticFile('classic-neucha-cyrillic.woff2'), unicodeRange: cyrillic}),
    loadFont({family: hand, url: staticFile('classic-neucha-latin.woff2'), unicodeRange: latin}),
  ]);
  return fontReady;
}

function random(index, seed) {
  const value = Math.sin(index * 127.1 + seed * 311.7) * 43758.5453;
  return value - Math.floor(value);
}

const puffs = Array.from({length: 16}, (_, index) => ({
  x: 60 + random(index, 1) * 960,
  period: 8 + random(index, 2) * 5,
  offset: random(index, 3),
  size: (300 + random(index, 4) * 220) * 1.65,
  sway: 30 + random(index, 5) * 60,
  spin: random(index, 6) < .5 ? -1 : 1,
}));

export function ClassicSmoke() {
  useEffect(() => { loadClassicFont().catch(cancelRender); }, []);
  const time = useCurrentFrame() / 30;
  return <AbsoluteFill style={{background: '#fff'}}>
    {puffs.map((puff, index) => {
      const progress = (time / puff.period + puff.offset) % 1;
      const x = puff.x + Math.sin(time * .5 + index) * puff.sway;
      const y = 2150 - progress * 2100;
      const opacity = Math.min(1, progress * 5) * Math.max(0, Math.min(1, (y - 380) / 700)) * .73;
      return <Img key={index} src={staticFile('classic-smoke.png')} style={{
        position: 'absolute',
        left: x - puff.size / 2, top: y - puff.size / 2,
        width: puff.size, height: puff.size, opacity,
        transform: `scale(${.55 + progress * 1.3}) rotate(${puff.spin * time * 6}deg)`,
      }} />;
    })}
  </AbsoluteFill>;
}

function Plate({value, label, accent = false}) {
  return <div style={{
    ...letters, minWidth: 275, padding: '18px 27px', borderRadius: 25,
    background: accent ? '#fff1cc' : '#fffdf6',
    border: `4px solid ${accent ? red : '#4a4c43'}`, boxShadow: '0 10px 0 #d3c8af',
  }}>
    {label && <div style={{fontSize: 31, color: red}}>{label}</div>}
    <div style={{fontSize: value.length > 10 ? 63 : 76, lineHeight: 1.06, whiteSpace: 'nowrap'}}>{value}</div>
  </div>;
}

function Poll() {
  return <svg width="760" height="373" viewBox="0 0 550 270" aria-hidden="true">
    {[0, 1].map(index => <g key={index} transform={`translate(${150 + index * 250} 128)`}>
      <path d="M101-5A101 95 0 1 0-27 86l36 23-4-20A101 95 0 0 0 101-5Z" fill="#fffefa" stroke={ink} strokeWidth="7" />
      {index === 0
        ? <path d="M-51 1l30 31 61-62" stroke="#3e8363" strokeWidth="22" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        : <path d="M-36-35l68 68m0-68-68 68" stroke="#cf5852" strokeWidth="20" strokeLinecap="round" fill="none" />}
    </g>)}
  </svg>;
}

function ClassicVisual({scene, frame}) {
  const beat = scene.classic;
  const revealAt = Math.round((beat.revealAt ?? 0.13) * 30);
  const reveal = interpolate(frame, [revealAt, revealAt + 8], [0, 1], clamp);
  const accentStyle = {opacity: reveal, transform: `scale(${0.93 + 0.07 * reveal})`};
  if (beat.kind === 'compare') return <div style={{display: 'flex', alignItems: 'center', gap: 24}}>
    <Plate value={beat.before} label="НА ПРОБУ" />
    <div style={{...letters, fontSize: 62, color: red}}>→</div>
    <div style={accentStyle}><Plate value={beat.after} label="ЦЕЛЬ ПО ВЫРУЧКЕ" accent /></div>
  </div>;
  if (beat.kind === 'total') return <div style={{display: 'grid', justifyItems: 'center', gap: 22}}>
    {beat.formula && <div style={{...letters, fontSize: 54, padding: '7px 27px',
      borderRadius: 20, color: red, background: '#fff8e8'}}>{beat.formula}</div>}
    <div style={accentStyle}><Plate value={beat.value} label={beat.label || 'ПРИМЕР ВЫРУЧКИ'} accent /></div>
  </div>;
  if (beat.kind === 'poll') return <Poll />;
  if (beat.kind === 'steps') return <div style={{display: 'grid', gap: 16, justifyItems: 'center'}}>
    {scene.diagram.steps.map((step, index) => {
      const visible = interpolate(frame, [index * 7, index * 7 + 6], [0, 1], clamp);
      return <div key={index} style={{
        ...letters, fontSize: 49, padding: '10px 38px', borderRadius: 17,
        border: '3px solid #ded8c7', background: '#fffdf6', opacity: visible,
        transform: `translateY(${(1 - visible) * 14}px)`,
      }}>{step}</div>;
    })}
  </div>;
  return <div style={{display: 'grid', justifyItems: 'center'}}>
    <Img src={staticFile(scene.art)} style={{width: 760, height: 429, objectFit: 'contain'}} />
    {beat.label && <div style={{
      ...letters, fontSize: 37, padding: '8px 24px', borderRadius: 16,
      color: red, background: '#fffdf8', border: '2px solid #ded8c7',
    }}>{beat.label}</div>}
  </div>;
}

export function Classic({scene, frame, caption, speaking}) {
  const opening = scene.classic.kind === 'hero';
  const mouth = scene.mouthFrames?.[frame];
  const pose = scene.mouthFrames
    ? (mouth ? scene.mouths[Math.min(mouth, scene.mouths.length) - 1] : scene.src)
    : (speaking ? scene.mouths[Math.floor(frame / 3) % scene.mouths.length] : scene.src);
  const entry = interpolate(frame, [0, 7], [.91, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const height = opening ? 670 * interpolate(frame, [0, 6], [.93, 1], clamp) : 435;
  const text = caption?.toLocaleUpperCase('ru-RU');
  return <AbsoluteFill>
    {!opening && <div style={{
      position: 'absolute', top: 410, left: 0, width: 1080, height: 665,
      display: 'grid', placeItems: 'center',
      transform: `translateY(${Math.sin(frame * .06) * 6}px) scale(${entry})`,
    }}>
      <ClassicVisual scene={scene} frame={frame} />
    </div>}
    <Img src={staticFile(pose)} style={{
      position: 'absolute', left: (1080 - height) / 2, top: (opening ? 880 : 1430) - height / 2,
      width: height, height, objectFit: 'contain',
    }} />
    {text && <div style={{
      ...letters, position: 'absolute', top: 212, left: 52, right: 52,
      lineHeight: 1.07, fontSize: text.length > 44 ? 51 : text.length > 24 ? 58 : 67,
      transform: 'skewX(-10deg)', textWrap: 'balance',
    }}>{text}</div>}
  </AbsoluteFill>;
}

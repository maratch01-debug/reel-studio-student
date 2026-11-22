import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame} from 'remotion';

const paths = {
  spark: 'M12 2l2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8z',
  target: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 5a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm0 4v2',
  clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4v6l4 2',
  chart: 'M3 3v18h18M7 16l5-5 4 2 5-7m-5 0h5v5',
  layers: 'm12 3 10 5-10 5L2 8zm-10 9 10 5 10-5M2 16l10 5 10-5',
  check: 'm4 12 5 5L20 6',
  camera: 'M2 7h4l2-3h8l2 3h4v14H2zm10 2a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  bolt: 'm13 2-9 12h7l-1 8 10-12h-7z',
  chat: 'M3 4h18v13H9l-6 4zm4 5h10m-10 4h7',
  arrow: 'M3 12h17m-7-7 7 7-7 7',
  play: 'm7 3 15 9-15 9z',
  image: 'M3 3h18v18H3zm0 14 6-6 5 5 3-3 4 4M16 8h.01',
  audio: 'M3 10v4m4-7v10m5-14v18m5-14v10m4-7v4',
  globe: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2c5 4 5 16 0 20-5-4-5-16 0-20z',
  book: 'M3 4h6l3 2 3-2h6v15h-6l-3 2-3-2H3zm9 2v15',
  link: 'm10 13 4-4m-5 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
};

export function Icon({name, size = 72, color = '#96f7db'}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[name] || paths.spark} fill="none" stroke={color}
        strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const palettes = {
  mint: ['#101c24', '#153a3b', '#96f7db'],
  blue: ['#131a32', '#233664', '#acc8ff'],
  sunset: ['#251b30', '#523349', '#ffc693'],
};

const enter = (frame, delay = 0) => spring({
  frame: frame - delay, fps: 30, config: {damping: 18, stiffness: 128, mass: 0.75},
});

function Rows({items, variant, frame, accent}) {
  return items.map((item, index) => {
    const reveal = enter(frame, 8 + index * 5);
    const value = Math.min(100, Math.max(0, Number(item.value) || 0));
    const size = variant === 'bars' ? Math.round(value * Math.min(1, reveal)) : 0;
    return (
      <div key={index} style={{
        display: 'flex', alignItems: 'center', gap: 24, padding: '24px 28px',
        borderRadius: 26, border: '1px solid #ffffff33', background: '#ffffff10',
        opacity: Math.min(1, reveal), transform: 'translateY(' + (1 - reveal) * 36 + 'px)',
      }}>
        {variant === 'timeline' ?
          <div style={{minWidth: 88, color: accent, fontWeight: 800}}>{item.mark || index + 1}</div> :
          <Icon name={item.icon} size={50} color={accent} />}
        <div style={{flex: 1, minWidth: 0}}>
          <div style={{fontSize: 40, fontWeight: 720, overflowWrap: 'anywhere'}}>{item.label}</div>
          {item.detail && <div style={{fontSize: 28, color: '#d4dfed', marginTop: 8}}>{item.detail}</div>}
          {variant === 'bars' && <div style={{height: 16, borderRadius: 10, background: '#ffffff22', marginTop: 16}}>
            <div style={{width: size + '%', height: '100%', borderRadius: 10, background: accent}} />
          </div>}
        </div>
        {variant === 'bars' && <div style={{fontSize: 42, color: accent, fontWeight: 800}}>{size}%</div>}
      </div>
    );
  });
}

export function Graphic({data}) {
  const frame = useCurrentFrame();
  const reveal = enter(frame);
  const [base, glow, accent] = palettes[data.palette] || palettes.mint;
  const variant = data.variant || 'cards';
  return (
    <AbsoluteFill style={{
      background: 'radial-gradient(circle at 74% 22%, ' + glow + ', ' + base + ' 74%)',
      color: '#f7fafc', fontFamily: 'Arial, sans-serif', justifyContent: 'center', padding: '150px 95px 390px',
    }}>
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 28,
        opacity: Math.min(1, reveal), transform: 'translateY(' + (1 - reveal) * 52 + 'px)',
      }}>
        <Icon name={data.icon} size={104} color={accent} />
        {data.eyebrow && <div style={{color: accent, fontSize: 27, fontWeight: 700, letterSpacing: 4}}>{data.eyebrow}</div>}
        <div style={{fontSize: variant === 'title' ? 98 : 76, lineHeight: 1.04, fontWeight: 800, overflowWrap: 'anywhere'}}>
          {data.title}
        </div>
        {data.body && <div style={{fontSize: 38, lineHeight: 1.25, color: '#d4dfed'}}>{data.body}</div>}
        <div style={{display: 'flex', flexDirection: 'column', gap: 14}}>
          <Rows items={data.items || []} variant={variant} frame={frame} accent={accent} />
        </div>
      </div>
    </AbsoluteFill>
  );
}

export function Badge({badge}) {
  const frame = useCurrentFrame();
  if (frame < badge.fromFrame || frame >= badge.toFrame) return null;
  const reveal = enter(frame, badge.fromFrame);
  const opacity = interpolate(reveal, [0, 1], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <div style={{
      position: 'absolute', left: 84, top: 205, display: 'flex', alignItems: 'center', gap: 18,
      padding: '18px 28px', borderRadius: 20, color: '#fff', background: '#172534ef',
      fontFamily: 'Arial, sans-serif', fontWeight: 700, fontSize: 40,
      maxWidth: 860, opacity, transform: 'translateX(' + (reveal - 1) * 32 + 'px)',
    }}>
      <Icon name={badge.icon} size={48} />{badge.text}
    </div>
  );
}

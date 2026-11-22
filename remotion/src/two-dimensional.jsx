import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile} from 'remotion';
import {Icon} from './graphics';

const ink = '#202641';
const font = 'Arial, sans-serif';

function Art({name, style}) {
  return name ? <Img src={staticFile(name)} style={{width: '100%', height: '100%', ...style}} /> : null;
}

function Diagram({data, frame, compact = false}) {
  const colors = {plum: '#71458c', amber: '#a44b20', blue: '#315f89'};
  const accent = colors[data.color] || colors.plum;
  const reveal = (index) => Math.max(0, Math.min(1, (frame - index * 5) / 7));
  const steps = data.steps || [];
  return (
    <AbsoluteFill style={{background: '#fff', color: ink, fontFamily: font,
      justifyContent: 'center', alignItems: 'center', padding: compact ? '10px 36px' : '34px 65px',
      gap: compact ? 3 : 8, textAlign: 'center'}}>
      {steps.length ? steps.map((step, index) => (
        <React.Fragment key={index}>
          {index > 0 && <div style={{opacity: reveal(index), transform: 'rotate(90deg)', height: compact ? 25 : 37}}>
            <Icon name="arrow" size={compact ? 26 : 38} color={accent} />
          </div>}
          <div style={{boxSizing: 'border-box', width: '100%', padding: compact ? '9px 20px' : '19px 24px',
            background: '#f7f4f9', border: '2px solid #ded4e7', borderRadius: compact ? 12 : 24,
            color: ink, fontSize: compact ? 35 : 52, fontWeight: 800, lineHeight: 1.05,
            opacity: reveal(index), transform: 'translateY(' + (1 - reveal(index)) * 18 + 'px)'}}>
            {step}
          </div>
        </React.Fragment>
      )) : (
        <div style={{opacity: reveal(0), transform: 'scale(' + (0.88 + reveal(0) * 0.12) + ')'}}>
          <div style={{color: accent, fontSize: compact ? 65 : 104, fontWeight: 900, lineHeight: 1.05,
            overflowWrap: 'anywhere'}}>{data.value}</div>
          {data.label && <div style={{fontSize: compact ? 31 : 46, marginTop: 14, textWrap: 'balance'}}>{data.label}</div>}
        </div>
      )}
    </AbsoluteFill>
  );
}

function Panel({scene, frame}) {
  return scene.diagram ? <Diagram data={scene.diagram} frame={frame} /> :
    <Art name={scene.art} style={{objectFit: 'cover'}} />;
}

function Speaker({scene, frame, speaking, style, animated = false}) {
  const poses = [scene.src, ...scene.mouths, scene.mouths[0]];
  const pose = speaking ? poses[Math.floor(frame / 3) % poses.length] : scene.src;
  const entrance = spring({frame, fps: 30, config: {damping: 18, stiffness: 120}});
  const rise = (1 - entrance) * (animated ? 106 : 18);
  const bob = Math.sin(frame / 8) * (animated ? 9 : 4);
  const direction = scene.gesture === 'left' ? -1 : scene.gesture === 'right' ? 1 : 0;
  const walk = interpolate(frame, [0, Math.max(1, scene.frames - 1)], [-95, 95]) * direction;
  const tilt = scene.gesture === 'nod' ? Math.sin(frame / 7) * 3.5 : direction * 3;
  return (
    <div style={{position: 'absolute', ...style}}>
      <Art name={pose} style={{objectFit: 'contain',
        transform: scene.lockHead ? undefined : `translate(${walk}px, ${rise + bob}px) rotate(${tilt}deg)`}} />
    </div>
  );
}

function WhiteBackground({scene, frame, caption, speaking}) {
  const show = spring({frame, fps: 30, config: {damping: 16, stiffness: 138}});
  const imageBox = scene.lockHead
    ? {left: 122, top: 461, width: 836, height: 627}
    : {left: 133, top: 510, width: 814, height: 610};
  const headBox = scene.lockHead
    ? {left: 280, top: 1155, width: 520, height: 520}
    : {left: 303, top: 1040, width: 474, height: 552};
  return (
    <AbsoluteFill style={{background: '#fff', color: ink, fontFamily: font}}>
      {caption && <div style={{position: 'absolute', left: 94, right: 94, top: 224, textAlign: 'center',
        fontSize: 66, fontWeight: 800, lineHeight: 1.07, textWrap: 'balance'}}>{caption}</div>}
      {(scene.art || scene.diagram) && <div style={{position: 'absolute', ...imageBox,
        overflow: 'hidden', borderRadius: 32, transform: `scale(${0.92 + 0.08 * show})`}}>
        <Panel scene={scene} frame={frame} />
      </div>}
      <Speaker scene={scene} frame={frame} speaking={speaking} style={headBox} />
    </AbsoluteFill>
  );
}

function Comic({scene, frame, caption, speaking}) {
  const reveal = interpolate(frame, [0, 6], [0.94, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: '#f8ebd3', fontFamily: font, color: '#242136',
      backgroundImage: 'radial-gradient(#36224e20 1.8px, transparent 1.8px)', backgroundSize: '19px 19px'}}>
      <div style={{position: 'absolute', left: 76, right: 76, top: 183, height: 775,
        transform: `rotate(-1deg) scale(${reveal})`, background: '#fff2d9', overflow: 'hidden',
        border: '8px solid #242136', boxShadow: '12px 12px 0 #242136'}}>
        <Panel scene={scene} frame={frame} />
        {!scene.diagram && <div style={{position: 'absolute', top: 28, left: 28, background: '#ffda6f',
          padding: '10px 22px', border: '5px solid #242136', fontSize: 40, fontWeight: 900}}>
          {String(scene.panel).padStart(2, '0')}
        </div>}
      </div>
      <div style={{position: 'absolute', left: 76, right: 76, top: 1002, height: 550,
        overflow: 'hidden', background: '#e2d9fa', border: '8px solid #242136', boxShadow: '12px 12px 0 #242136'}}>
        <Speaker scene={scene} frame={frame} speaking={speaking}
          style={{left: 42, top: 40, width: 420, height: 490}} />
        {caption && <div style={{position: 'absolute', right: 43, top: 108, width: 410,
          boxSizing: 'border-box', padding: '32px 24px', background: 'white', border: '5px solid #242136',
          borderRadius: '36px 36px 36px 9px', fontWeight: 800, fontSize: 49, lineHeight: 1.1,
          textAlign: 'center', textWrap: 'balance'}}>{caption}</div>}
      </div>
    </AbsoluteFill>
  );
}

function CartoonStory({scene, frame, caption, speaking}) {
  const progress = interpolate(frame, [0, Math.max(1, scene.frames - 1)], [0, 1]);
  return (
    <AbsoluteFill style={{background: scene.background, fontFamily: font, color: '#fff'}}>
      <Art name={scene.art} style={{objectFit: 'cover', position: 'absolute',
        transform: `scale(${1.04 + progress * 0.08})`}} />
      <AbsoluteFill style={{background: 'linear-gradient(180deg,#18243855,transparent 30%,transparent 62%,#142337b0)'}} />
      {scene.diagram && <div style={{position: 'absolute', left: 122, right: 122, top: 244, height: 300,
        borderRadius: 32, overflow: 'hidden'}}>
        <Diagram data={scene.diagram} frame={frame} compact />
      </div>}
      {scene.heading && <div style={{position: 'absolute', left: 90, top: 178, right: 90,
        fontSize: 65, fontWeight: 900, lineHeight: 1.03, textAlign: 'center',
        textShadow: '0 3px 14px #142337b0', textWrap: 'balance'}}>{scene.heading}</div>}
      <Speaker scene={scene} frame={frame} speaking={speaking} animated
        style={{left: 214, top: 593, width: 652, height: 782}} />
      {caption && <div style={{position: 'absolute', bottom: 301, left: 100, right: 100,
        textAlign: 'center', fontSize: 62, fontWeight: 900, textWrap: 'balance',
        WebkitTextStroke: '8px #182438', paintOrder: 'stroke fill'}}>{caption}</div>}
    </AbsoluteFill>
  );
}

export function TwoDimensional(props) {
  switch (props.scene.layout) {
    case 'white-background': return <WhiteBackground {...props} />;
    case 'comic': return <Comic {...props} />;
    case 'cartoon-story': return <CartoonStory {...props} />;
    default: throw new Error('Unknown 2D layout: ' + props.scene.layout);
  }
}

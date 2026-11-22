import React from 'react';
import {
  AbsoluteFill,
  Composition,
  Html5Audio,
  Img,
  OffthreadVideo,
  Sequence,
  Series,
  interpolate,
  registerRoot,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import {Badge, Graphic} from './graphics.jsx';
import {TwoDimensional} from './two-dimensional.jsx';

function Sprite({scene, frame, speaking}) {
  const image = speaking ? scene.mouths[Math.floor(frame / 3) % scene.mouths.length] : scene.src;
  const offset = Math.sin(frame / 14) * 8;
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', background: scene.background}}>
      <Img src={staticFile(image)} style={{
        width: 820, height: 1060, objectFit: 'contain', transform: 'translateY(' + offset + 'px)',
      }} />
    </AbsoluteFill>
  );
}

function Visual({scene, frame, speaking}) {
  if (scene.kind === 'graphic') return <Graphic data={scene.graphic} />;
  if (scene.kind === 'sprite') return <Sprite scene={scene} frame={frame} speaking={speaking} />;
  const progress = interpolate(frame, [0, Math.max(1, scene.frames - 1)], [0, 1]);
  const moving = scene.motion === 'push' || scene.motion === 'pull' || scene.motion === 'pan';
  const zoom = scene.motion === 'push' ? 1 + 0.12 * progress :
    scene.motion === 'pull' ? 1.12 - 0.12 * progress : moving ? 1.12 : 1;
  const x = scene.motion === 'pan' ? 48 - 96 * progress : 0;
  return <OffthreadVideo src={staticFile(scene.src)} style={{
    width: '100%', height: '100%', transform: 'translateX(' + x + 'px) scale(' + zoom + ')',
  }} />;
}

function Scene({scene, captionStyle, dip}) {
  const frame = useCurrentFrame();
  const accent = captionStyle === 'accent';
  const cue = scene.cues?.find(({fromFrame, toFrame}) => frame >= fromFrame && frame < toFrame);
  const caption = scene.cues?.length ? cue?.text : scene.caption;
  const speaking = scene.cues?.length ? Boolean(cue) : frame < (scene.voiceFrames || 0);
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {scene.layout ?
        <TwoDimensional scene={scene} frame={frame} speaking={speaking} caption={caption} /> :
        <Visual scene={scene} frame={frame} speaking={speaking} />}
      {scene.voice && <Html5Audio src={staticFile(scene.voice)} />}
      {scene.sound && (
        <Sequence from={scene.soundFrom} layout="none">
          <Html5Audio src={staticFile(scene.sound)} volume={0.45} />
        </Sequence>
      )}
      {scene.badge && <Badge badge={scene.badge} />}
      {scene.sticker && <Img src={staticFile(scene.sticker)} style={{
        position: 'absolute', width: 180, height: 180, objectFit: 'contain', top: 205, right: 84,
      }} />}
      {caption && !scene.layout && captionStyle === 'talk' && <TalkCaption text={caption} />}
      {caption && !scene.layout && captionStyle !== 'talk' && (
        <div style={{
          position: 'absolute',
          left: 84,
          right: 84,
          bottom: 332,
          display: 'flex',
          justifyContent: 'center',
          textAlign: 'center',
          fontFamily: 'Arial, sans-serif',
          fontWeight: 700,
          fontSize: 58,
          lineHeight: 1.12,
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
          color: accent ? '#ffe269' : '#ffffff',
          textShadow: '0 2px 4px #000',
        }}>
          <span style={{padding: '16px 28px', borderRadius: 16, background: 'rgba(12, 15, 20, 0.78)'}}>
            {caption}
          </span>
        </div>
      )}
      {dip && frame < 5 && (
        <AbsoluteFill style={{backgroundColor: '#000', opacity: 1 - frame / 5}} />
      )}
    </AbsoluteFill>
  );
}

function TalkCaption({text}) {
  const words = text.trim().split(/\s+/u);
  return (
    <div style={{
      position: 'absolute', left: 90, right: 90, bottom: 410,
      textAlign: 'center', textWrap: 'balance', color: '#fff',
      fontFamily: 'Arial, sans-serif', fontWeight: 900, fontSize: 72, lineHeight: 1.02,
      textTransform: 'uppercase', WebkitTextStroke: '11px #15110e',
      paintOrder: 'stroke fill', textShadow: '0 4px 2px #0009',
    }}>
      {words.slice(0, -1).join(' ')}{' '}
      <span style={{color: '#ffe065'}}>{words.at(-1)}</span>
    </div>
  );
}

function Reel({scenes, music, musicVolume = 0.12, captionStyle, transition}) {
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <Series>
        {scenes.map((scene, index) => (
          <Series.Sequence key={index} durationInFrames={scene.frames}>
            <Scene scene={scene} captionStyle={captionStyle} dip={index > 0 && transition === 'dip'} />
          </Series.Sequence>
        ))}
      </Series>
      {music && <Html5Audio src={staticFile(music)} volume={musicVolume} loop />}
    </AbsoluteFill>
  );
}

function Root() {
  return (
    <Composition
      id="Reel"
      component={Reel}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1}
      defaultProps={{scenes: [], music: null, captionStyle: 'clean', transition: 'cut'}}
      calculateMetadata={({props}) => ({
        durationInFrames: Math.max(1, props.scenes.reduce((total, scene) => total + scene.frames, 0)),
      })}
    />
  );
}

registerRoot(Root);

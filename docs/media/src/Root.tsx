import React from 'react';
import {Composition, Still} from 'remotion';
import {Demo, FPS, H, TOTAL, W} from './Demo';
import {Shot, type ShotName} from './shots';

/** Each shot is as tall as its own content, so the README has no letterboxing. */
export const SHOTS: Partial<Record<ShotName, number>> = {
  rate: 1276,
  small: 1276,
  rates: 780,
  diff: 730,
  errors: 600,
};
const SHOT_W = 1000;

export const Root: React.FC = () => (
  <>
    <Composition
      id="demo"
      component={Demo}
      durationInFrames={TOTAL}
      fps={FPS}
      width={W}
      height={H}
    />
    {(Object.keys(SHOTS) as ShotName[]).map((name) => (
      <Still
        key={name}
        id={`shot-${name}`}
        component={() => <Shot name={name} />}
        width={SHOT_W}
        height={SHOTS[name]!}
      />
    ))}
  </>
);

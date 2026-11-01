/**
 * The demo GIF: type a question, get the chart, tap the app stores' rate, watch it redraw.
 * Both replies are the bot's real output (shots.json: `rate` and `rate_app`).
 */
import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import data from './shots.json';
import {TgHtml} from './html';
import type {Reply} from './shots';
import {DayDivider, In, Out, Window} from './telegram';

export const FPS = 30;
export const W = 1000;
export const H = 1276;
export const TOTAL = 11 * FPS;

const QUESTION = data.rate[0]!.out as string;
const TYPE_END = Math.round(1.8 * FPS);
const SENT = TYPE_END + 6;
const ANSWER = SENT + Math.round(0.7 * FPS);
const TAP = Math.round(6 * FPS);
const EDITED = TAP + 8;

const site = (data.rate[1] as {in: Reply}).in;
const stores = (data.rate_app[1] as {in: Reply}).in;

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const typed = QUESTION.slice(
    0,
    Math.floor(
      interpolate(frame, [6, TYPE_END], [0, QUESTION.length], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      }),
    ),
  );
  const answerIn = spring({frame: frame - ANSWER, fps, config: {damping: 18}});
  const reply = frame >= EDITED ? stores : site;
  const pressed = frame >= TAP && frame < EDITED + 6;
  const keyboard = reply.keyboard.map((row) =>
    row.map((label) => ({label: pressed && frame < EDITED ? `👆 ${label}` : label})),
  );

  return (
    <AbsoluteFill>
      <Window composer={frame < SENT ? typed || undefined : undefined}>
        <DayDivider>November 1</DayDivider>
        {frame >= SENT ? <Out time="21:30">{QUESTION}</Out> : null}
        {frame >= ANSWER ? (
          <div style={{opacity: answerIn, transform: `translateY(${(1 - answerIn) * 24}px)`}}>
            <In time="21:30" width="82%" keyboard={keyboard} photo={reply.photo}>
              <TgHtml html={reply.html} />
            </In>
          </div>
        ) : null}
      </Window>
    </AbsoluteFill>
  );
};

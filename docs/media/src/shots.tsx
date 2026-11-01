/**
 * The README screenshots: real replies from shots.json (written by scripts/export_shots.py),
 * drawn in a Telegram Desktop window. Nothing here is retyped by hand.
 */
import React from 'react';
import {AbsoluteFill} from 'remotion';
import data from './shots.json';
import {TgHtml} from './html';
import {DayDivider, In, Out, Window} from './telegram';

export type Reply = {html: string; keyboard: string[][]; photo?: string};
type Item = {out: string} | {in: Reply};
export type ShotName = keyof typeof data;

const time = (i: number) => `21:${String(30 + i).padStart(2, '0')}`;

export const Conversation: React.FC<{items: Item[]; width?: string}> = ({items, width = '82%'}) => (
  <AbsoluteFill>
    <Window>
      <DayDivider>November 1</DayDivider>
      {items.map((item, i) =>
        'out' in item ? (
          <Out key={i} time={time(i)}>
            {item.out}
          </Out>
        ) : (
          <In
            key={i}
            time={time(i)}
            width={width}
            photo={item.in.photo}
            keyboard={
              item.in.keyboard.length
                ? item.in.keyboard.map((row) => row.map((label) => ({label})))
                : undefined
            }
          >
            <TgHtml html={item.in.html} />
          </In>
        ),
      )}
    </Window>
  </AbsoluteFill>
);

export const Shot: React.FC<{name: ShotName}> = ({name}) => (
  <Conversation items={data[name] as Item[]} />
);

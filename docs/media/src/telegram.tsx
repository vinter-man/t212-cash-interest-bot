/**
 * Telegram Desktop, dark theme, close enough that a reader recognises it instantly.
 *
 * The palette is Telegram's own "Night" theme, not an interpretation of it: a screenshot that
 * is almost Telegram is worse than a diagram, because the reader spends their attention on
 * what looks wrong instead of on what the bot said.
 */
import React from 'react';
import {Img, staticFile} from 'remotion';
import avatar from '../../assets/avatar.png';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

const inter = loadInter();
const mono = loadMono();

export const SANS = inter.fontFamily;
export const MONO = mono.fontFamily;

export const TG = {
  header: '#17212B',
  chat: '#0E1621',
  bubble: '#182533',
  out: '#2B5278',
  text: '#FFFFFF',
  meta: '#6C8299',
  dim: '#7D8E9E',
  link: '#71BAF2',
  button: 'rgba(255,255,255,0.08)',
  buttonLine: 'rgba(255,255,255,0.06)',
  divider: 'rgba(0,0,0,0.32)',
  accent: '#5288C1',
} as const;

/** The bot's avatar: a one-cent cup (docs/assets/avatar.png), round as Telegram crops it. */
const Avatar: React.FC<{size?: number}> = ({size = 42}) => (
  <Img
    src={avatar}
    style={{width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'block'}}
  />
);

/** The window: title bar, the chat, and the composer nobody types into. */
export const Window: React.FC<{
  children: React.ReactNode;
  title?: string;
  composer?: React.ReactNode;
}> = ({children, title = 'Cash Interest Buddy', composer}) => (
  <div
    style={{
      position: 'absolute',
      inset: 0,
      backgroundColor: TG.chat,
      fontFamily: SANS,
      display: 'flex',
      flexDirection: 'column',
    }}
  >
    <div
      style={{
        backgroundColor: TG.header,
        padding: '11px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        borderBottom: '1px solid rgba(0,0,0,0.35)',
        flexShrink: 0,
      }}
    >
      <Avatar />
      <div style={{flex: 1}}>
        <div style={{fontSize: 16, fontWeight: 600, color: TG.text}}>{title}</div>
        <div style={{fontSize: 13.5, color: TG.dim, marginTop: 2}}>bot</div>
      </div>
      <div style={{display: 'flex', gap: 22, color: TG.dim, fontSize: 19}}>
        <span>⌕</span>
        <span>⋮</span>
      </div>
    </div>

    <div
      style={{
        flex: 1,
        padding: '16px 20px 10px',
        display: 'flex',
        flexDirection: 'column',
        // A short conversation sits on the floor of the window, as it does in the real client.
        justifyContent: 'flex-end',
        gap: 10,
        overflow: 'hidden',
      }}
    >
      {children}
    </div>

    <div
      style={{
        backgroundColor: TG.header,
        padding: '14px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flexShrink: 0,
      }}
    >
      <span style={{color: TG.dim, fontSize: 19}}>📎</span>
      <span style={{flex: 1, color: composer ? TG.text : TG.dim, fontSize: 16}}>
        {composer ?? 'Message'}
      </span>
      <span style={{color: TG.dim, fontSize: 18}}>☺</span>
      <span style={{color: TG.dim, fontSize: 18}}>🎤</span>
    </div>
  </div>
);

export const DayDivider: React.FC<{children?: React.ReactNode}> = ({children = 'Today'}) => (
  <div style={{display: 'flex', justifyContent: 'center', margin: '2px 0 6px'}}>
    <span
      style={{
        backgroundColor: TG.divider,
        color: '#C8D6E2',
        fontSize: 13,
        padding: '4px 12px',
        borderRadius: 12,
      }}
    >
      {children}
    </span>
  </div>
);

/** A message the reader sent: right-hand side, blue, with the two ticks. */
export const Out: React.FC<{children: React.ReactNode; time: string}> = ({children, time}) => (
  <div style={{display: 'flex', justifyContent: 'flex-end'}}>
    <div
      style={{
        backgroundColor: TG.out,
        borderRadius: '12px 12px 4px 12px',
        padding: '8px 12px 7px',
        maxWidth: '62%',
        fontSize: 16.5,
        color: TG.text,
        display: 'flex',
        alignItems: 'flex-end',
        gap: 10,
      }}
    >
      <span>{children}</span>
      <span style={{fontSize: 12.5, color: '#8FB3DC', whiteSpace: 'nowrap', paddingBottom: 1}}>
        {time} ✓✓
      </span>
    </div>
  </div>
);

export type Key = {label: string; wide?: boolean};

/** A message the bot sent, with its inline keyboard hanging underneath; with `photo` (a file in
 * public/), a picture on top and the text as its caption, as Telegram draws a captioned photo. */
export const In: React.FC<{
  children: React.ReactNode;
  time: string;
  keyboard?: Key[][];
  width?: number | string;
  photo?: string;
}> = ({children, time, keyboard, width = '78%', photo}) => (
  <div
    style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start', maxWidth: width}}
  >
    <div
      style={{
        backgroundColor: TG.bubble,
        borderRadius: keyboard ? '12px 12px 12px 4px' : '12px 12px 12px 4px',
        padding: '9px 13px 7px',
        fontSize: 16.5,
        lineHeight: 1.45,
        color: TG.text,
        width: '100%',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      {photo ? (
        <Img
          src={staticFile(photo)}
          style={{display: 'block', width: 'calc(100% + 26px)', margin: '-9px -13px 8px'}}
        />
      ) : null}
      {children}
      <div style={{textAlign: 'right', fontSize: 12.5, color: TG.meta, marginTop: 2}}>{time}</div>
    </div>
    {keyboard ? (
      <div style={{width: '100%', marginTop: 3, display: 'flex', flexDirection: 'column', gap: 3}}>
        {keyboard.map((row, i) => (
          <div key={i} style={{display: 'flex', gap: 3}}>
            {row.map((k) => (
              <div
                key={k.label}
                style={{
                  flex: k.wide ? 2 : 1,
                  backgroundColor: TG.button,
                  border: `1px solid ${TG.buttonLine}`,
                  borderRadius: 7,
                  padding: '9px 8px',
                  textAlign: 'center',
                  fontSize: 15,
                  color: TG.text,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {k.label}
              </div>
            ))}
          </div>
        ))}
      </div>
    ) : null}
  </div>
);

/** Telegram renders <code> in a monospace face at the same size as the text around it. */
export const Code: React.FC<{children: React.ReactNode}> = ({children}) => (
  <span style={{fontFamily: MONO, fontSize: 15, color: '#E8EFF5'}}>{children}</span>
);

/** A <pre> block: Telegram draws it as its own box, monospaced, with an accent stripe. */
export const Pre: React.FC<{children: React.ReactNode}> = ({children}) => (
  <span
    style={{
      display: 'block',
      fontFamily: MONO,
      fontSize: 14.5,
      lineHeight: 1.5,
      color: '#E8EFF5',
      whiteSpace: 'pre',
      backgroundColor: 'rgba(113,186,242,0.07)',
      borderLeft: `3px solid ${TG.link}`,
      borderRadius: 6,
      padding: '7px 12px',
      margin: '6px 0',
    }}
  >
    {children}
  </span>
);

export const Link: React.FC<{children: React.ReactNode}> = ({children}) => (
  <span style={{color: TG.link}}>{children}</span>
);

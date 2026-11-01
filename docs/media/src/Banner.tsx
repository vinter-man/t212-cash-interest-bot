/**
 * The README's cover, in the bot's own drawing language: ink on paper, a pencil wobble on every
 * stroke (an SVG turbulence filter, so text stays crisp), one-cent cups like the chart's.
 */
import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Fonts} from './Fonts';
import {faint, grey, ink, mono, paper, sans} from './theme';

export const BANNER = {width: 2560, height: 1280};

const STACK = [
  'Python',
  'Telegram',
  'aiogram',
  'pydantic',
  'httpx',
  'SQLite',
  'APScheduler',
  'matplotlib',
  'hypothesis',
  'Docker',
  'mypy',
  'GitHub Actions',
];
// A $10 balance at 5%: what each day carries, as a share of a cent. Day 8 makes the first cent.
const CARRIED = [0.13, 0.27, 0.4, 0.53, 0.67, 0.8, 0.94];

const Defs: React.FC = () => (
  <defs>
    {/* In user space: a straight line has a zero-height box, and a box-relative region would
        swallow it. */}
    <filter id="pencil" filterUnits="userSpaceOnUse" x={-100} y={-100} width={2800} height={1500}>
      <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves={2} seed={7} />
      <feDisplacementMap in="SourceGraphic" scale={4.5} />
    </filter>
    <pattern
      id="hatch"
      width={11}
      height={11}
      patternUnits="userSpaceOnUse"
      patternTransform="rotate(45)"
    >
      <rect width={2.4} height={11} fill={ink} />
    </pattern>
  </defs>
);

/** A rate as one source publishes it: a sketched card with a big number. */
const Card: React.FC<{x: number; source: string; rate: string; dim?: boolean}> = ({
  x,
  source,
  rate,
  dim,
}) => (
  <g>
    <rect
      x={x}
      y={40}
      width={420}
      height={250}
      rx={6}
      fill="none"
      stroke={ink}
      strokeWidth={4}
      filter="url(#pencil)"
    />
    <text x={x + 34} y={98} fontFamily={mono} fontSize={28} fill={grey}>
      {source}
    </text>
    <text
      x={x + 30}
      y={238}
      fontFamily={sans}
      fontSize={132}
      fontWeight={500}
      letterSpacing="-0.04em"
      fill={dim ? grey : ink}
    >
      {rate}
    </text>
  </g>
);

/** One cent's worth of carry, drawn as a cup filling up. */
const Cup: React.FC<{x: number; level: number; day: number}> = ({x, level, day}) => (
  <g>
    {level > 0 ? (
      <rect x={x} y={560 - 130 * level} width={78} height={130 * level} fill="url(#hatch)" />
    ) : null}
    {/* Open at the top, like the bot's chart: what does not fit spills into a payment. */}
    <path
      d={`M ${x} 424 L ${x} 560 L ${x + 78} 560 L ${x + 78} 424`}
      fill="none"
      stroke={ink}
      strokeWidth={4}
      strokeLinejoin="round"
      filter="url(#pencil)"
    />
    <text x={x + 39} y={606} textAnchor="middle" fontFamily={mono} fontSize={26} fill={grey}>
      {day}
    </text>
  </g>
);

const Illustration: React.FC = () => (
  <svg width={1120} height={860} style={{position: 'absolute', left: 1360, top: 182}}>
    <Defs />
    <Card x={40} source="website" rate="2.5%" />
    <text
      x={530}
      y={200}
      textAnchor="middle"
      fontFamily={sans}
      fontSize={110}
      fill={ink}
      fontWeight={400}
    >
      ≠
    </text>
    <Card x={620} source="app stores" rate="2.2%" dim />
    <text x={40} y={352} fontFamily={mono} fontSize={28} fill={grey}>
      EUR · EU view · 1 November 2026
    </text>

    {CARRIED.map((level, i) => (
      <Cup key={i} x={40 + i * 108} level={level} day={i + 1} />
    ))}
    {/* Day 8: the cup fills, one cent is paid, and the carry starts again. */}
    <Cup x={40 + 7 * 108} level={0.07} day={8} />
    <text
      x={40 + 7 * 108 + 39}
      y={404}
      textAnchor="middle"
      fontFamily={sans}
      fontSize={56}
      fontWeight={600}
      fill={ink}
    >
      1¢
    </text>
    <path
      d="M 912 398 C 960 392, 1000 420, 1024 470"
      fill="none"
      stroke={ink}
      strokeWidth={4}
      filter="url(#pencil)"
    />
    <path
      d="M 1004 462 L 1026 476 L 1034 450"
      fill="none"
      stroke={ink}
      strokeWidth={4}
      filter="url(#pencil)"
    />
    {[0, 1, 2, 3, 4].map((n) => (
      <ellipse
        key={n}
        cx={1036}
        cy={604 - n * 24}
        rx={62}
        ry={17}
        fill={ink}
        stroke={paper}
        strokeWidth={3}
        filter="url(#pencil)"
      />
    ))}
    <text x={40} y={690} fontFamily={mono} fontSize={28} fill={grey}>
      $10 at 5%: carried until it makes a cent, then paid
    </text>
    <line
      x1={40}
      x2={1060}
      y1={740}
      y2={740}
      stroke={faint}
      strokeWidth={3}
      filter="url(#pencil)"
    />
    <text x={40} y={800} fontFamily={mono} fontSize={28} fill={ink}>
      balance × ((1 + AER)^(1/365.25) − 1), rounded down
    </text>
  </svg>
);

const Stack: React.FC = () => (
  <div
    style={{
      position: 'absolute',
      left: 128,
      right: 128,
      bottom: 92,
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
    }}
  >
    {STACK.map((name) => (
      <span
        key={name}
        style={{
          fontFamily: mono,
          fontSize: 25,
          color: ink,
          border: `2.5px solid ${ink}`,
          borderRadius: 4,
          padding: '6px 14px',
          whiteSpace: 'nowrap',
        }}
      >
        {name}
      </span>
    ))}
  </div>
);

export const Banner: React.FC = () => (
  <Fonts>
    <AbsoluteFill style={{background: paper, color: ink, fontFamily: sans}}>
      <div
        style={{
          position: 'absolute',
          left: 128,
          top: 128,
          fontFamily: mono,
          fontSize: 30,
          color: grey,
        }}
      >
        github.com/vinter-man/t212-cash-interest-bot
      </div>
      <div
        style={{
          position: 'absolute',
          left: 120,
          top: 206,
          fontSize: 196,
          lineHeight: 0.94,
          fontWeight: 500,
          letterSpacing: '-0.055em',
        }}
      >
        interest,
        <br />
        to the cent
      </div>
      <div
        style={{
          position: 'absolute',
          left: 128,
          top: 626,
          width: 1210,
          fontSize: 41,
          lineHeight: 1.32,
          color: grey,
        }}
      >
        Daily interest on uninvested cash by Trading 212&apos;s published formula, and where their
        site and app stores disagree.
      </div>
      <div style={{position: 'absolute', left: 128, top: 800, fontFamily: mono, fontSize: 36}}>
        balance → rate → daily cents →{' '}
        <span style={{borderBottom: `4px solid ${ink}`, paddingBottom: 3}}>diff</span>
      </div>
      <div
        style={{
          position: 'absolute',
          left: 128,
          top: 888,
          fontFamily: mono,
          fontSize: 28,
          color: grey,
        }}
      >
        unofficial · not affiliated with Trading 212 · not financial advice
      </div>
      <Illustration />
      <Stack />
      <svg width={2560} height={40} style={{position: 'absolute', left: 0, bottom: 44}}>
        <Defs />
        <line
          x1={118}
          x2={2442}
          y1={20}
          y2={20}
          stroke={ink}
          strokeWidth={5}
          filter="url(#pencil)"
        />
      </svg>
    </AbsoluteFill>
  </Fonts>
);

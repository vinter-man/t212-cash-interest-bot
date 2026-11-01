/**
 * Builds the README's banner, screenshots and demo GIF into ../assets.
 *
 * Run `uv run python scripts/export_shots.py` first: the shots and the demo are drawn from the
 * bot's real replies in src/shots.json, so a wording change in the bot is a re-render here, not
 * a screenshot somebody has to retake. Needs ffmpeg on PATH for the GIF.
 */
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';

const OUT = '../assets';
const TMP = 'out';
const SHOTS = ['rate', 'small', 'rates', 'diff', 'subscribe', 'errors'];

const run = (cmd, args) => execFileSync(cmd, args, {stdio: 'inherit'});

mkdirSync(OUT, {recursive: true});
mkdirSync(TMP, {recursive: true});

run('npx', ['remotion', 'still', 'banner', `${OUT}/banner.png`, '--log=error']);
for (const shot of SHOTS) {
  run('npx', ['remotion', 'still', `shot-${shot}`, `${OUT}/${shot}.png`, '--log=error']);
}

run('npx', [
  'remotion',
  'render',
  'demo',
  `${TMP}/demo.mp4`,
  '--log=error',
  '--codec=h264',
  '--crf=16',
]);
// Two passes: one palette for the whole clip, then dither against it. A GIF made without this
// is both uglier and several times larger.
const FILTER = 'fps=12,scale=820:-1:flags=lanczos';
run('ffmpeg', [
  '-y',
  '-v',
  'error',
  '-i',
  `${TMP}/demo.mp4`,
  '-vf',
  `${FILTER},palettegen=max_colors=128:stats_mode=diff`,
  `${TMP}/palette.png`,
]);
run('ffmpeg', [
  '-y',
  '-v',
  'error',
  '-i',
  `${TMP}/demo.mp4`,
  '-i',
  `${TMP}/palette.png`,
  '-lavfi',
  `${FILTER}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle`,
  `${OUT}/demo.gif`,
]);

console.log('\nWrote', OUT);

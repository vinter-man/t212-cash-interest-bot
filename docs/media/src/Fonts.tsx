/** Loads the banner's faces from public/fonts before the first frame is taken. */
import React, {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';

const faces = [
  {family: 'Onest', file: 'fonts/onest-latin.woff2', weight: '100 900'},
  {family: 'IBM Plex Mono', file: 'fonts/IBMPlexMono-Regular.woff2', weight: '400'},
  {family: 'IBM Plex Mono', file: 'fonts/IBMPlexMono-SemiBold.woff2', weight: '600'},
];

export const Fonts: React.FC<{children: React.ReactNode}> = ({children}) => {
  const [handle] = useState(() => delayRender('fonts'));
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.all(
      faces.map(async ({family, file, weight}) => {
        const face = new FontFace(family, `url(${staticFile(file)})`, {weight});
        (document.fonts as unknown as {add(font: FontFace): void}).add(await face.load());
      }),
    ).then(() => {
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);

  return ready ? <>{children}</> : null;
};

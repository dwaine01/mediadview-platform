import { ScrollViewStyleReset } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

/**
 * Web-only HTML shell. Used to kill the browser's default focus outline
 * (the black line users saw while typing) and to smooth fonts.
 */
export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="es">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
        <ScrollViewStyleReset />
        <style dangerouslySetInnerHTML={{ __html: globalCss }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

const globalCss = `
html, body { background-color: #ffffff; }
body {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
input, textarea, select, button, [tabindex] {
  outline: none !important;
  -webkit-tap-highlight-color: transparent;
}
input:focus, textarea:focus, select:focus, button:focus,
input:focus-visible, textarea:focus-visible, button:focus-visible {
  outline: none !important;
  box-shadow: none !important;
}
`;

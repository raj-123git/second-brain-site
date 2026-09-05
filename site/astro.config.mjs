// @ts-check
import { defineConfig } from 'astro/config';

import sitemap from '@astrojs/sitemap';

// Lightning CSS is Vite's CSS transformer AND its final minifier, and the two passes take their
// browser targets from different places: the transformer from `css.lightningcss.targets`, the
// bundle minifier from `build.cssTarget`. Left at Vite's defaults the minify pass re-targets the
// bundle at Safari 16.4+ and drops the `-webkit-backdrop-filter` form that Safari ≤ 17 needs. One
// browser list feeds both, so global.css carries no hand-written vendor duplicates and the build
// asserts both `backdrop-filter` forms land in dist.
const BROWSERS = ['chrome100', 'edge100', 'firefox100', 'safari15', 'ios15', 'opera86'];
// Lightning CSS encodes versions as major << 16 | minor << 8; esbuild names → Lightning CSS keys.
const KEYS = { chrome: 'chrome', edge: 'edge', firefox: 'firefox', safari: 'safari', ios: 'ios_saf', opera: 'opera' };
const targets = Object.fromEntries(BROWSERS.map(b => {
  const [, name, major, minor = '0'] = /^([a-z]+)(\d+)(?:\.(\d+))?$/.exec(b) ?? [];
  return [KEYS[name], (Number(major) << 16) | (Number(minor) << 8)];
}));

// https://astro.build/config
export default defineConfig({
  site: 'https://rajranpariya.com',
  vite: {
    css: { transformer: 'lightningcss', lightningcss: { targets } },
    build: { cssTarget: BROWSERS },
  },

  integrations: [sitemap()]
});
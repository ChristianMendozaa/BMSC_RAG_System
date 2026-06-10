// All plugins are string keys → PostCSS resolves them via Node.js require(), not Turbopack.
// process.cwd() gives an absolute path for the local plugin so it resolves correctly
// regardless of the directory from which Turbopack evaluates this config.
const config = {
  plugins: {
    '@tailwindcss/postcss': {},
    [process.cwd() + '/postcss-translate-plugin.cjs']: {},
    'postcss-logical': { inlineDirection: 'left-to-right', blockDirection: 'top-to-bottom' },
    '@csstools/postcss-oklab-function': { subFeatures: { displayP3: false } },
    '@csstools/postcss-cascade-layers': {},
    [process.cwd() + '/postcss-where-plugin.cjs']: {},
    '@csstools/postcss-is-pseudo-class': {},
  },
};

export default config;

const config = {
  plugins: {
    "@tailwindcss/postcss": {},
    "@csstools/postcss-oklab-function": { subFeatures: { displayP3: false } },
    "@csstools/postcss-cascade-layers": {},
  },
};

export default config;

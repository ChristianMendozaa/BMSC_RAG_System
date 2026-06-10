// Edge 86 no soporta la propiedad individual `translate` (Chromium 104+).
// Reescribe `translate: <x> <y>?` al equivalente `transform: translate(...)`.
// Los valores de Tailwind (porcentajes, calc(), var()) son válidos dentro de translate().
// Divide solo por espacios de nivel superior para no romper var()/calc().
const splitTopLevel = (value) => {
  const parts = [];
  let depth = 0;
  let current = '';
  for (const ch of value) {
    if (ch === '(') depth++;
    else if (ch === ')') depth--;
    if (depth === 0 && /\s/.test(ch)) {
      if (current) parts.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  if (current) parts.push(current);
  return parts;
};

const plugin = () => ({
  postcssPlugin: 'postcss-translate-to-transform',
  Declaration: {
    translate: (decl) => {
      if (decl.value.trim() === 'none') {
        decl.assign({ prop: 'transform', value: 'none' });
        return;
      }
      const parts = splitTopLevel(decl.value.trim());
      const fn = parts.length === 3 ? 'translate3d' : 'translate';
      decl.assign({ prop: 'transform', value: `${fn}(${parts.join(', ')})` });
    },
  },
});
plugin.postcss = true;

module.exports = plugin;

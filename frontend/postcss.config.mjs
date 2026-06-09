import tailwindcss from '@tailwindcss/postcss';
import oklabFunction from '@csstools/postcss-oklab-function';
import cascadeLayers from '@csstools/postcss-cascade-layers';
import isPseudoClass from '@csstools/postcss-is-pseudo-class';

// Converts :where() → :is() so the isPseudoClass plugin can expand both.
// Edge 86 supports neither; the specificity change is acceptable for intranet use.
function whereToIs() {
  return {
    postcssPlugin: 'postcss-where-to-is',
    Rule(rule) {
      if (rule.selector?.includes(':where(')) {
        rule.selector = rule.selector.replace(/:where\(/g, ':is(');
      }
    },
  };
}
whereToIs.postcss = true;

export default {
  plugins: [
    tailwindcss(),
    oklabFunction({ subFeatures: { displayP3: false } }),
    cascadeLayers(),
    whereToIs(),
    isPseudoClass(),
  ],
};

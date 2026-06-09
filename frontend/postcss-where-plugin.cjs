// Converts :where() to :is() so @csstools/postcss-is-pseudo-class can expand both.
// :where() and :is() have identical syntax; only specificity differs (zero for :where).
// Edge 86 supports neither, so the specificity change is acceptable.
const plugin = () => ({
  postcssPlugin: 'postcss-where-to-is',
  Rule(rule) {
    if (rule.selector?.includes(':where(')) {
      rule.selector = rule.selector.replace(/:where\(/g, ':is(');
    }
  },
});
plugin.postcss = true;

module.exports = plugin;

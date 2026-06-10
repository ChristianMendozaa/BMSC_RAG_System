// Verifica que el CSS emitido por `next build` sea compatible con Edge 86 (Chromium 86),
// el navegador más viejo de la intranet del banco. Corre como parte de `npm run build`.
//
// Si este script falla, alguna utilidad/feature nueva emitió sintaxis moderna que ni la
// cadena PostCSS (postcss.config.mjs) ni Lightning CSS (targets de "browserslist" en
// package.json) están bajando. Agregar el plugin/transformación que corresponda antes
// de desplegar.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import process from 'node:process';

const STATIC_DIR = join(process.cwd(), '.next', 'static');

// Sintaxis no soportada por Edge 86 que nunca debe llegar al CSS final.
const FORBIDDEN = [
  { name: 'oklch()', regex: /oklch\(/ },
  { name: 'oklab() (fuera de color-mix con @supports)', regex: /[\s:,(]oklab\(/ },
  { name: '@layer', regex: /@layer[\s{]/ },
  { name: ':is()', regex: /:is\(/ },
  { name: ':where()', regex: /:where\(/ },
  // Propiedades: solo el nombre exacto seguido de ':' al inicio de una declaración.
  // Las variantes -start/-end (padding-inline-start, etc.) sí existen en Edge 86.
  { name: 'inset / inset-inline / inset-block', regex: /[{;}]inset[a-z-]*:/ },
  { name: 'shorthands lógicos (padding/margin/border -inline/-block)', regex: /[{;}](?:padding|margin|border)-(?:inline|block):/ },
  { name: 'propiedades de transform individuales (translate/scale/rotate)', regex: /[{;}](?:translate|scale|rotate):/ },
  { name: 'aspect-ratio', regex: /[{;}]aspect-ratio:/ },
];

const cssFiles = [];
const walk = (dir) => {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (entry.endsWith('.css')) cssFiles.push(full);
  }
};

try {
  walk(STATIC_DIR);
} catch {
  console.error(`[check-edge86-css] No existe ${STATIC_DIR} — ejecutar después de \`next build\`.`);
  process.exit(1);
}

if (cssFiles.length === 0) {
  console.error('[check-edge86-css] No se encontró ningún .css en .next/static — ¿cambió la estructura del build?');
  process.exit(1);
}

// color-mix() (Edge 111+) solo se permite dentro de @supports (Tailwind lo emite
// guardado y con fallback hex). Recorre el CSS rastreando si cada ocurrencia está
// dentro de un bloque @supports o de su propia condición.
const colorMixOutsideSupports = (css) => {
  const offenders = [];
  const stack = [];
  let pendingSupports = false;
  for (let i = 0; i < css.length; i++) {
    if (css.startsWith('@supports', i)) pendingSupports = true;
    if (css[i] === '{') {
      stack.push(pendingSupports || stack.includes(true));
      pendingSupports = false;
    } else if (css[i] === '}') {
      stack.pop();
    } else if (css.startsWith('color-mix(', i) && !pendingSupports && !stack.includes(true)) {
      offenders.push(css.slice(i, i + 80));
    }
  }
  return offenders;
};

let failed = false;
for (const file of cssFiles) {
  const css = readFileSync(file, 'utf8');
  for (const { name, regex } of FORBIDDEN) {
    const match = css.match(regex);
    if (match) {
      const at = match.index ?? 0;
      console.error(`✗ ${file}\n  ${name}: …${css.slice(Math.max(0, at - 40), at + 60)}…`);
      failed = true;
    }
  }
  for (const sample of colorMixOutsideSupports(css)) {
    console.error(`✗ ${file}\n  color-mix() sin @supports: ${sample}…`);
    failed = true;
  }
}

if (failed) {
  console.error('\n[check-edge86-css] FALLO: el CSS del build contiene sintaxis incompatible con Edge 86.');
  process.exit(1);
}
console.log(`[check-edge86-css] OK: ${cssFiles.length} archivo(s) CSS compatibles con Edge 86.`);

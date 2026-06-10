import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Nota: NO usar experimental.lightningCssFeatures.include ['logical-properties'] —
  // el polyfill de dirección de Lightning CSS reintroduce :is(:lang(...)) DESPUÉS de
  // que la cadena PostCSS ya expandió :is(), rompiendo Edge 86 de nuevo. La bajada de
  // propiedades lógicas se hace en PostCSS (postcss-logical en postcss.config.mjs).
};

export default nextConfig;

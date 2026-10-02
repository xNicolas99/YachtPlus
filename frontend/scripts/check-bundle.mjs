import { readFileSync, statSync } from 'node:fs';
import { dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const budgets = Object.freeze({ entry: 300_000, initialJavaScript: 550_000, initialCss: 700_000 });

export function verifyBuildVersion(metadata, expected) {
  if (!metadata || metadata.version !== expected || !/^\d+\.\d+\.\d+$/.test(expected)) {
    throw new Error('Build version differs from the configured SemVer');
  }
}

export function auditBundle(manifest, sizeOf) {
  if (!manifest || !manifest['index.html']?.isEntry) throw new Error('Missing application entry');
  const sizes = new Map();
  function size(file) {
    if (typeof file !== 'string' || !file.startsWith('assets/') || file.includes('..') || file.includes('\\')) {
      throw new Error('Invalid asset path');
    }
    if (!sizes.has(file)) {
      const bytes = sizeOf(file);
      if (!Number.isSafeInteger(bytes) || bytes < 0) throw new Error(`Invalid asset size: ${file}`);
      sizes.set(file, bytes);
    }
    return sizes.get(file);
  }
  function dependencies(entry) {
    const visited = new Set();
    function visit(key) {
      if (visited.has(key)) return;
      const chunk = manifest[key];
      if (!chunk || typeof chunk !== 'object') throw new Error(`Missing chunk: ${key}`);
      visited.add(key);
      for (const dependency of chunk.imports || []) visit(dependency);
    }
    visit(entry);
    return visited;
  }
  // Validate every emitted chunk, including lazy features, before accepting a build.
  for (const [key, chunk] of Object.entries(manifest)) {
    size(chunk.file);
    for (const file of [...(chunk.css || []), ...(chunk.assets || [])]) size(file);
    for (const dependency of [...(chunk.imports || []), ...(chunk.dynamicImports || [])]) {
      if (!manifest[dependency]) throw new Error(`Missing chunk: ${dependency} (from ${key})`);
    }
  }
  const initial = dependencies('index.html');
  const css = new Set([...initial].flatMap(key => manifest[key].css || []));
  const stats = {
    entry: size(manifest['index.html'].file),
    initialJavaScript: [...initial].reduce((sum, key) => sum + size(manifest[key].file), 0),
    initialCss: [...css].reduce((sum, file) => sum + size(file), 0),
  };
  for (const [kind, limit] of Object.entries(budgets)) {
    if (stats[kind] > limit) throw new Error(`${kind} exceeds bundle budget: ${stats[kind]} > ${limit} bytes`);
  }
  for (const feature of [
    'src/components/ContainerTerminal.vue',
    'src/components/compose/ProjectEditor.vue',
    'src/components/applications/ApplicationDetailsComponents/AppStats.vue',
  ]) {
    if (!manifest[feature]) throw new Error(`Missing lazy feature: ${feature}`);
    if (initial.has(feature)) throw new Error(`Feature loaded at startup: ${feature}`);
  }
  const apps = 'src/components/applications/ApplicationsList.vue';
  if (!manifest[apps]) throw new Error('Missing applications route');
  if (dependencies(apps).has('src/components/ContainerTerminal.vue')) {
    throw new Error('Terminal must load only when opened');
  }
  return stats;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dist = resolve(dirname(fileURLToPath(import.meta.url)), '../dist');
  const manifest = JSON.parse(readFileSync(resolve(dist, '.vite/manifest.json'), 'utf8'));
  const packageVersion = JSON.parse(readFileSync(resolve(dist, '../package.json'), 'utf8')).version;
  verifyBuildVersion(JSON.parse(readFileSync(resolve(dist, 'version.json'), 'utf8')), process.env.VITE_VERSION || packageVersion);
  const stats = auditBundle(manifest, file => {
    const target = resolve(dist, file);
    if (!target.startsWith(dist + sep)) throw new Error('Asset outside build directory');
    return statSync(target).size;
  });
  console.log(`Bundle gates passed: entry ${stats.entry}, initial JS ${stats.initialJavaScript}, initial CSS ${stats.initialCss} bytes`);
}

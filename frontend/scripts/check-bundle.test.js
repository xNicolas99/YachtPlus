import { describe, expect, it } from 'vitest';
import { auditBundle, budgets, verifyBuildVersion } from './check-bundle.mjs';

const terminal = 'src/components/ContainerTerminal.vue';
const apps = 'src/components/applications/ApplicationsList.vue';
function fixture() {
  return {
    'index.html': { isEntry: true, file: 'assets/index.js', imports: ['vendor'], css: ['assets/shared.css'] },
    vendor: { file: 'assets/vendor.js', css: ['assets/shared.css'] },
    [terminal]: { file: 'assets/terminal.js' },
    [apps]: { file: 'assets/apps.js', dynamicImports: [terminal] },
    'src/components/compose/ProjectEditor.vue': { file: 'assets/editor.js' },
    'src/components/applications/ApplicationDetailsComponents/AppStats.vue': { file: 'assets/stats.js' },
  };
}

describe('production bundle failsafe', () => {
  it('checks exact metadata version instead of matching arbitrary dependency text', () => {
    expect(() => verifyBuildVersion({ version: '2.0.2' }, '2.0.2')).not.toThrow();
    expect(() => verifyBuildVersion({ version: '2.0.1' }, '2.0.2')).toThrow('Build version');
    expect(() => verifyBuildVersion(undefined, '2.0.2')).toThrow('Build version');
    expect(() => verifyBuildVersion({ version: 'development' }, 'development')).toThrow('Build version');
  });
  it('counts static dependencies and shared CSS once while excluding lazy features', () => {
    expect(auditBundle(fixture(), () => 100)).toEqual({ entry: 100, initialJavaScript: 200, initialCss: 100 });
  });
  it('rejects a missing entry', () => {
    expect(() => auditBundle({}, () => 100)).toThrow('Missing application entry');
  });
  it.each(['imports', 'dynamicImports'])('rejects a missing %s dependency', kind => {
    const manifest = fixture();
    manifest['index.html'][kind] = ['missing'];
    expect(() => auditBundle(manifest, () => 100)).toThrow('Missing chunk');
  });
  it('rejects missing assets even for unopened features', () => {
    expect(() => auditBundle(fixture(), file => {
      if (file === 'assets/terminal.js') throw new Error('ENOENT');
      return 100;
    })).toThrow('ENOENT');
  });
  it.each(['../secret.js', 'assets/../../secret.js', 'assets\\secret.js'])('rejects unsafe asset path %s', file => {
    const manifest = fixture();
    manifest[terminal].file = file;
    expect(() => auditBundle(manifest, () => 100)).toThrow('Invalid asset path');
  });
  it.each(['entry', 'initialJavaScript', 'initialCss'])('fails when the %s budget is exceeded', kind => {
    expect(() => auditBundle(fixture(), file => {
      if (kind === 'entry' && file === 'assets/index.js') return budgets.entry + 1;
      if (kind === 'initialJavaScript' && file === 'assets/vendor.js') return budgets.initialJavaScript;
      if (kind === 'initialCss' && file === 'assets/shared.css') return budgets.initialCss + 1;
      return 100;
    })).toThrow(`${kind} exceeds bundle budget`);
  });
  it('rejects an eagerly imported terminal in the apps route', () => {
    const manifest = fixture();
    manifest[apps].imports = [terminal];
    expect(() => auditBundle(manifest, () => 100)).toThrow('Terminal must load only when opened');
  });
  it('rejects editor loading at startup through an indirect import', () => {
    const manifest = fixture();
    manifest.vendor.imports = ['src/components/compose/ProjectEditor.vue'];
    expect(() => auditBundle(manifest, () => 100)).toThrow('Feature loaded at startup');
  });
});

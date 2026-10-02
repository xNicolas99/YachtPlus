import { describe, it, expect, vi } from 'vitest';

// vuetify.js runs at import time: it reads from localStorage and calls
// createVuetify(). Neither exists in the default Vitest (Node) environment,
// so we stub localStorage and mock the heavy vuetify imports BEFORE importing.
vi.mock('@mdi/font/css/materialdesignicons.css', () => ({}));
vi.mock('vuetify/styles', () => ({}));
vi.mock('vuetify/components', () => ({}));
vi.mock('vuetify/directives', () => ({}));
vi.mock('vuetify', () => ({
  createVuetify: (opts) => ({ options: opts }),
}));

if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  };
}

const { updateTheme } = await import('./vuetify.js');

function makeVuetifyMock({ withDark = true, withLight = true } = {}) {
  const themes = {};
  if (withDark) {
    themes.dark = { dark: true, colors: { primary: '#000000', secondary: '#111111' } };
  }
  if (withLight) {
    themes.light = { dark: false, colors: { primary: '#222222', secondary: '#333333' } };
  }
  return { theme: { themes: { value: themes } } };
}

describe('updateTheme', () => {
  it('updates primary and secondary on both light and dark themes', () => {
    const vuetify = makeVuetifyMock();
    updateTheme(vuetify, '#FF0000', '#00FF00');

    expect(vuetify.theme.themes.value.dark.colors.primary).toBe('#FF0000');
    expect(vuetify.theme.themes.value.dark.colors.secondary).toBe('#00FF00');
    expect(vuetify.theme.themes.value.light.colors.primary).toBe('#FF0000');
    expect(vuetify.theme.themes.value.light.colors.secondary).toBe('#00FF00');
  });

  it('returns early without throwing when vuetifyInstance is null', () => {
    expect(() => updateTheme(null, '#FF0000', '#00FF00')).not.toThrow();
  });

  it('returns early without throwing when vuetifyInstance is undefined', () => {
    expect(() => updateTheme(undefined, '#FF0000', '#00FF00')).not.toThrow();
  });

  it('only updates primary when secondaryColor is omitted', () => {
    const vuetify = makeVuetifyMock();
    const originalSecondaryDark = vuetify.theme.themes.value.dark.colors.secondary;
    const originalSecondaryLight = vuetify.theme.themes.value.light.colors.secondary;

    updateTheme(vuetify, '#ABCDEF');

    expect(vuetify.theme.themes.value.dark.colors.primary).toBe('#ABCDEF');
    expect(vuetify.theme.themes.value.light.colors.primary).toBe('#ABCDEF');
    expect(vuetify.theme.themes.value.dark.colors.secondary).toBe(originalSecondaryDark);
    expect(vuetify.theme.themes.value.light.colors.secondary).toBe(originalSecondaryLight);
  });

  it('only updates secondary when primaryColor is falsy', () => {
    const vuetify = makeVuetifyMock();
    const originalPrimaryDark = vuetify.theme.themes.value.dark.colors.primary;
    const originalPrimaryLight = vuetify.theme.themes.value.light.colors.primary;

    updateTheme(vuetify, '', '#123456');

    expect(vuetify.theme.themes.value.dark.colors.secondary).toBe('#123456');
    expect(vuetify.theme.themes.value.light.colors.secondary).toBe('#123456');
    expect(vuetify.theme.themes.value.dark.colors.primary).toBe(originalPrimaryDark);
    expect(vuetify.theme.themes.value.light.colors.primary).toBe(originalPrimaryLight);
  });

  it('does not update anything when both colors are falsy', () => {
    const vuetify = makeVuetifyMock();
    const snapshot = JSON.parse(JSON.stringify(vuetify.theme.themes.value));

    updateTheme(vuetify, '', undefined);

    expect(vuetify.theme.themes.value).toEqual(snapshot);
  });

  it('skips a theme key that does not exist on the instance', () => {
    const vuetify = makeVuetifyMock({ withLight: false });
    expect(() => updateTheme(vuetify, '#FF0000', '#00FF00')).not.toThrow();

    expect(vuetify.theme.themes.value.dark.colors.primary).toBe('#FF0000');
    expect(vuetify.theme.themes.value.dark.colors.secondary).toBe('#00FF00');
    expect(vuetify.theme.themes.value.light).toBeUndefined();
  });
});

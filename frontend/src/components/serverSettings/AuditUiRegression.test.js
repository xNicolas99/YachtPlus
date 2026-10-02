import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import Theme from './Theme.vue';
import ServerSettings from '@/views/ServerSettings.vue';
import RegistryBrowser from '@/components/templates/RegistryBrowser.vue';
import ProjectDetails from '@/components/compose/ProjectDetails.vue';
import { containerPortLink } from '@/utils/containerLinks';

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn(), defaults: {} } }));
vi.mock('@/router/index', () => ({ default: { push: vi.fn().mockResolvedValue() } }));
const storage = new Map();
vi.stubGlobal('localStorage', {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
});
const { default: apps } = await import('@/store/modules/apps');
beforeEach(() => { vi.clearAllMocks(); storage.clear(); });

describe('browser-observed audit UI regressions', () => {
  it.each([true, false])('persists switch event %s even before the model setter runs', value => {
    Theme.methods.setDarkmode.call({ isDark: !value }, value);
    expect(storage.get('dark_theme')).toBe(String(value));
  });

  it.each([
    ['/settings/info', 1], ['/settings/theme', 2], ['/settings/templateVariables', 3],
    ['/settings/prune', 4], ['/settings/update', 5], ['/settings/smtp', 6],
    ['/settings/security', 7], ['/settings/audit', 8],
  ])('selects the visible settings tab for %s', (path, tab) => {
    const context = { SettingsTab: 1 };
    ServerSettings.watch['$route.path'].handler.call(context, path);
    expect(context.SettingsTab).toBe(tab);
  });

  it('updates the deep link on tab changes without pushing duplicates or navigating Back twice', () => {
    const context = { $route: { path: '/settings/info' }, $router: { replace: vi.fn() } };
    ServerSettings.watch.SettingsTab.call(context, 2);
    expect(context.$router.replace).toHaveBeenCalledWith('/settings/theme');
    context.$router.replace.mockClear();
    ServerSettings.watch.SettingsTab.call(context, 1);
    ServerSettings.watch.SettingsTab.call(context, 0);
    expect(context.$router.replace).not.toHaveBeenCalled();
  });

  it('keeps a failed Compose deletion open and navigates only after a successful action', async () => {
    const context = { selectedProject: { name: 'demo' }, ProjectAction: vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true), postDelete: vi.fn() };
    await ProjectDetails.methods.confirmDelete.call(context);
    expect(context.postDelete).not.toHaveBeenCalled();
    await ProjectDetails.methods.confirmDelete.call(context);
    expect(context.postDelete).toHaveBeenCalledTimes(1);
  });

  it('retains the newest registry results when an older response arrives last', async () => {
    let resolveOld, resolveNew;
    const oldRequest = new Promise(resolve => { resolveOld = resolve; });
    const newRequest = new Promise(resolve => { resolveNew = resolve; });
    const context = { loading: false, images: [], currentRegistryName: 'dockerhub', search: 'old', fetchRegistryImages: vi.fn().mockReturnValueOnce(oldRequest).mockReturnValueOnce(newRequest) };
    const old = RegistryBrowser.methods.fetchImages.call(context);
    context.search = 'new';
    const latest = RegistryBrowser.methods.fetchImages.call(context);
    resolveNew([{ name: 'new-result' }]);
    await latest;
    resolveOld([{ name: 'stale-result' }]);
    await old;
    expect(context.images).toEqual([{ name: 'new-result' }]);
    expect(context.loading).toBe(false);
  });
});

describe('preserved remote application action contracts', () => {
  it.each([
    { shape: 'list', response: [{ Id: 'a', name: 'web' }] },
    { shape: 'individual', response: { Id: 'a', name: 'web' } },
  ])('accepts $shape app responses', async ({ response }) => {
    const commit = vi.fn();
    axios.post.mockResolvedValueOnce({ data: response });
    await apps.actions.AppAction({ commit }, { Name: 'web', Action: 'start' });
    expect(commit).toHaveBeenCalledWith(Array.isArray(response) ? 'setApps' : 'setApp', response);
  });
});

describe('container port links', () => {
  it.each([
    [{ hip: '0.0.0.0', hport: '8080' }, { hostname: 'host.local', protocol: 'https:' }, 'https://host.local:8080'],
    [{ hip: '127.0.0.1', hport: '8080' }, { hostname: 'host.local', protocol: 'http:' }, 'http://127.0.0.1:8080'],
    [{ hip: '10.0.0.2', hport: '8443' }, { hostname: 'host.local', protocol: 'http:' }, 'https://10.0.0.2:8443'],
    [{ hip: '2001:db8::1', hport: 443 }, { hostname: 'host.local', protocol: 'http:' }, 'https://[2001:db8::1]:443'],
    [{ hip: '::', hport: '8080' }, { hostname: '[::1]', protocol: 'http:' }, 'http://[::1]:8080'],
  ])('builds protocol and IPv6-safe published links', (port, location, expected) => {
    expect(containerPortLink(port, location)).toBe(expected);
  });
});

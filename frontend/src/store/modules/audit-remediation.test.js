import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import router from '@/router/index';
import VueUtils from '@/plugins/vueutils';

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn(), defaults: {} } }));
vi.mock('@/router/index', () => ({ default: { push: vi.fn().mockResolvedValue() } }));

const storage = new Map();
vi.stubGlobal('localStorage', {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
});

const { default: auth } = await import('./auth');
const { default: apps } = await import('./apps');
const { default: store } = await import('../index');

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  storage.clear();
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('audit authentication regressions', () => {
  it('shares one bounded refresh across simultaneous timer and request calls', async () => {
    const response = deferred();
    axios.post.mockReturnValueOnce(response.promise);
    const first = auth.actions.AUTH_REFRESH();
    const second = auth.actions.AUTH_REFRESH();

    expect(second).toBe(first);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('/auth/refresh', {}, expect.objectContaining({
      timeout: 15000, skipAuthRefresh: true, withCredentials: true,
      xsrfCookieName: 'csrf_access_token', xsrfHeaderName: 'X-CSRF-TOKEN',
    }));
    response.resolve({ data: { success: true } });
    await expect(first).resolves.toEqual({ data: { success: true } });
    await second;
  });

  it('releases a failed refresh so the next session can try again', async () => {
    const response = deferred();
    axios.post.mockReturnValueOnce(response.promise);
    const first = auth.actions.AUTH_REFRESH();
    const second = auth.actions.AUTH_REFRESH();
    const settled = Promise.allSettled([first, second]);
    response.reject(new Error('expired'));
    expect((await settled).map(result => result.status)).toEqual(['rejected', 'rejected']);
    axios.post.mockResolvedValueOnce({ data: { success: true } });
    await expect(auth.actions.AUTH_REFRESH()).resolves.toEqual({ data: { success: true } });
    expect(axios.post).toHaveBeenCalledTimes(2);
  });

  it('clears account and temporary 2FA secrets when logout fails on the server', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    store.state.auth.username = 'captain';
    store.state.auth.setupSecret = 'temporary-secret';
    store.state.auth.setupQrCode = 'temporary-qr';
    store.state.auth.setupStep = 3;
    storage.set('username', 'captain');
    store.state.projects.projects = [{ name: 'private', content: 'PASSWORD=secret' }];
    store.state.apps.logs = ['sensitive log'];
    store.state.apps.action = 'Reading private container';
    store.state.templates.templateVariables = [{ value: 'secret-variable' }];
    store.state.snackbar.content = 'private state';
    store.state.snackbar.visible = true;
    axios.post.mockRejectedValueOnce(new Error('offline'));

    await store.dispatch('auth/AUTH_LOGOUT');

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('/auth/logout', {}, expect.objectContaining({ skipAuthRefresh: true }));
    expect(storage.has('username')).toBe(false);
    expect(store.state.auth).toMatchObject({ username: '', setupSecret: null, setupQrCode: null, setupStep: 1 });
    expect(store.state.projects.projects).toEqual([]);
    expect(store.state.apps.logs).toEqual([]);
    expect(store.state.apps.action).toBe('');
    expect(store.state.templates.templateVariables).toEqual([]);
    expect(store.state.snackbar).toMatchObject({ content: '', visible: false });
    expect(router.push).toHaveBeenCalledWith({ path: '/login' });
  });
});

describe('audit container identity regressions', () => {
  it('replaces the same ID and retains different containers without names', () => {
    const state = { apps: [{ Id: 'one' }, { Id: 'two' }] };
    apps.mutations.setApp(state, { Id: 'two', state: 'running' });
    expect(state.apps).toEqual([{ Id: 'one' }, { Id: 'two', state: 'running' }]);
    apps.mutations.setApp(state, { Id: 'three' });
    expect(state.apps).toHaveLength(3);
  });

  it('updates a recreated container by its normalized persisted name', () => {
    const state = { apps: [{ Id: 'old', Name: '/web' }, { Id: 'db', name: 'db' }] };
    apps.mutations.setApp(state, { Id: 'new', name: 'web' });
    expect(state.apps).toEqual([{ Id: 'new', name: 'web' }, { Id: 'db', name: 'db' }]);
  });
});

describe('audit Docker timestamp regressions', () => {
  it('formats seconds, milliseconds and ISO values as the same date', () => {
    const app = { config: { globalProperties: {} } };
    VueUtils.install(app);
    const format = app.config.globalProperties.$formatDate;
    const instant = new Date('2026-10-02T10:00:00Z');
    expect(format(instant.getTime() / 1000)).toBe(format(instant.getTime()));
    expect(format(instant.toISOString())).toBe(format(instant.getTime()));
  });

  it('uses Unix seconds consistently for relative times', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-02T10:01:00Z'));
    const app = { config: { globalProperties: {} } };
    VueUtils.install(app);
    const ago = app.config.globalProperties.$timeAgo;
    const instant = new Date('2026-10-02T10:00:00Z');
    expect(ago(instant.getTime() / 1000)).toBe(ago(instant.getTime()));
    expect(ago(instant.toISOString())).toBe('a minute ago');
  });
});

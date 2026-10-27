import { afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import router from '@/router/index';

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }));
vi.mock('@/router/index', () => ({ default: { push: vi.fn().mockResolvedValue() } }));

const storage = new Map();
vi.stubGlobal('localStorage', {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
});

const { default: auth } = await import('./auth.js');
afterEach(() => vi.restoreAllMocks());

describe('auth session actions', () => {
  it.each([null, true, false])('retains setup state %s after a failed status request', async isSetup => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const commit = vi.fn();
    axios.get.mockRejectedValueOnce(new Error('Server unavailable'));

    await expect(auth.actions.CHECK_SETUP({ commit, state: { isSetup } })).resolves.toBe(isSetup);

    expect(commit).not.toHaveBeenCalled();
  });

  it('enters setup only after the backend confirms it is incomplete', async () => {
    const commit = vi.fn();
    axios.get.mockResolvedValueOnce({ data: { is_setup: false } });

    await expect(auth.actions.CHECK_SETUP({ commit, state: { isSetup: null } })).resolves.toBe(false);

    expect(commit).toHaveBeenCalledWith('SET_SETUP_STATUS', false);
  });

  it('rejects failed refreshes so requests cannot wait forever', async () => {
    axios.post.mockRejectedValueOnce(new Error('expired'));
    await expect(auth.actions.AUTH_REFRESH()).rejects.toThrow('expired');
  });

  it('clears the saved username when the session ends', () => {
    storage.set('username', 'captain');
    const state = { username: 'captain', authDisabled: true, status: 'success' };

    auth.mutations.AUTH_CLEAR(state);

    expect(storage.has('username')).toBe(false);
    expect(state.username).toBe('');
    expect(state.authDisabled).toBeNull();
  });

  it('keeps the account form open when the update fails', async () => {
    vi.clearAllMocks();
    axios.post.mockRejectedValueOnce(new Error('server rejected update'));
    const commit = vi.fn();

    await expect(auth.actions.AUTH_CHANGE_PASS({ commit }, { username: 'captain' }))
      .rejects.toThrow('server rejected update');

    expect(router.push).not.toHaveBeenCalled();
    expect(commit).toHaveBeenCalledWith('AUTH_ERROR');
  });
});

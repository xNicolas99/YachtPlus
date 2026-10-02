import { describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import router from '@/router/index';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));
vi.mock('@/router/index', () => ({ default: { push: vi.fn().mockResolvedValue() } }));

const storage = new Map();
vi.stubGlobal('localStorage', {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
});

const { default: auth } = await import('./auth.js');

describe('auth session actions', () => {
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

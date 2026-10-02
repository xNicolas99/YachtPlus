import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import router from '@/router/index';
import images from './images';
import networks from './networks';
import volumes from './volumes';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock('@/router/index', () => ({ default: { push: vi.fn().mockResolvedValue() } }));
beforeEach(() => vi.clearAllMocks());

describe.each([
  ['Images', images], ['Networks', networks], ['Volumes', volumes],
])('%s resource lists', (name, module) => {
  it('loads API envelopes and subsequent pages into one array', async () => {
    const commit = vi.fn();
    axios.get.mockResolvedValueOnce({ data: { items: [{ Id: 'one' }], total: 2 } });
    axios.get.mockResolvedValueOnce({ data: { items: [{ Id: 'two' }], total: 2 } });

    const result = await module.actions[`read${name}`]({ commit });

    expect(result).toEqual([{ Id: 'one' }, { Id: 'two' }]);
    expect(commit).toHaveBeenCalledWith(`set${name}`, result);
    expect(axios.get).toHaveBeenLastCalledWith(`/resources/${name.toLowerCase()}/`, { params: { offset: 1, limit: 500 } });
    expect(commit).toHaveBeenLastCalledWith('setLoading', false);
  });

  it('keeps the previous list intact when a later page fails', async () => {
    const commit = vi.fn();
    const error = new Error('Docker unavailable');
    axios.get.mockResolvedValueOnce({ data: { items: [{ Id: 'one' }], total: 2 } });
    axios.get.mockRejectedValueOnce(error);

    expect(await module.actions[`read${name}`]({ commit })).toBe(false);

    expect(commit).not.toHaveBeenCalledWith(`set${name}`, expect.anything());
    expect(commit).toHaveBeenCalledWith('snackbar/setErr', error, { root: true });
    expect(commit).toHaveBeenLastCalledWith('setLoading', false);
  });

  it('does not navigate away from a failed creation', async () => {
    axios.post.mockRejectedValueOnce(new Error('permission denied'));
    const dispatch = vi.fn();
    const commit = vi.fn();

    expect(await module.actions[`write${name.slice(0, -1)}`]({ commit, dispatch }, {})).toBe(false);

    expect(router.push).not.toHaveBeenCalled();
    expect(dispatch).not.toHaveBeenCalled();
    expect(commit).toHaveBeenLastCalledWith('setLoading', false);
  });

  it('does not remove a row when deletion fails', async () => {
    axios.delete.mockRejectedValueOnce(new Error('resource in use'));
    const commit = vi.fn();

    expect(await module.actions[`delete${name.slice(0, -1)}`]({ commit }, 'one')).toBe(false);

    expect(commit).not.toHaveBeenCalledWith(`remove${name.slice(0, -1)}`, expect.anything());
    expect(commit).toHaveBeenLastCalledWith('setLoading', false);
  });
});

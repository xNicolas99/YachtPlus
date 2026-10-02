import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import UserInfo from './UserInfo.vue';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

describe('API key UI', () => {
  it('replaces the key list with the server response instead of duplicating rows', async () => {
    const context = { ...UserInfo.data(), apiKeys: [{ id: 99 }] };
    axios.get.mockResolvedValueOnce({ data: [{ id: 1, key_name: 'deploy' }] });

    await UserInfo.methods.get_api_keys.call(context);

    expect(context.apiKeys).toEqual([{ id: 1, key_name: 'deploy' }]);
  });

  it('keeps the key row visible if revocation fails', async () => {
    const context = { ...UserInfo.data(), apiKeys: [{ id: 1, key_name: 'deploy' }] };
    axios.delete.mockRejectedValueOnce(new Error('offline'));

    await UserInfo.methods.revoke_api_key.call(context, context.apiKeys[0]);

    expect(context.apiKeys).toHaveLength(1);
    expect(context.error).toMatch(/Could not revoke/);
    expect(context.isLoading).toBe(false);
  });
});

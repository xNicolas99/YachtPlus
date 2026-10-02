import { describe, expect, it, vi } from 'vitest';
import { createRouter, createMemoryHistory } from 'vue-router';
import { createChunkRecovery } from './chunkRecovery';

const view = { render: () => null };
async function fixture(loader) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: view },
    { path: '/lazy', component: loader },
    { path: '/other', component: view }
  ] });
  const recovery = createChunkRecovery(router);
  await router.push('/');
  return { router, recovery };
}

describe('lazy route recovery', () => {
  it.each([
    'Failed to fetch dynamically imported module: private-host/file.js',
    'error loading dynamically imported module',
    'Importing a module script failed.',
    'Unable to preload CSS for /assets/lazy.css'
  ])('retains the current page on chunk failure and can retry (%s)', async message => {
    const loader = vi.fn().mockRejectedValueOnce(new TypeError(message)).mockResolvedValueOnce(view);
    const { router, recovery } = await fixture(loader);
    await expect(router.push('/lazy')).rejects.toThrow(message);
    expect(router.currentRoute.value.fullPath).toBe('/');
    expect(recovery.state).toMatchObject({ failed: true, target: '/lazy' });
    expect(await recovery.retry()).toBe(true);
    expect(router.currentRoute.value.fullPath).toBe('/lazy');
    expect(recovery.state.failed).toBe(false);
    recovery.dispose();
  });
  it('preserves recovery after another failure without automatically reloading', async () => {
    const { router, recovery } = await fixture(() => Promise.reject(new Error('Failed to fetch dynamically imported module')));
    await expect(router.push('/lazy')).rejects.toThrow();
    expect(await recovery.retry()).toBe(false);
    expect(recovery.state).toMatchObject({ failed: true, retrying: false, target: '/lazy' });
    recovery.dispose();
  });
  it('prevents duplicate retry navigation while loading', async () => {
    let finish;
    const loader = vi.fn().mockRejectedValueOnce(new Error('error loading dynamically imported module')).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { router, recovery } = await fixture(loader);
    await expect(router.push('/lazy')).rejects.toThrow();
    const retry = recovery.retry();
    expect(await recovery.retry()).toBe(false);
    for (let i = 0; i < 20 && !finish; i++) await Promise.resolve();
    finish(view);
    expect(await retry).toBe(true);
    expect(loader).toHaveBeenCalledTimes(2);
    recovery.dispose();
  });
  it('does not treat authentication or other application errors as chunk failures', async () => {
    const { router, recovery } = await fixture(() => Promise.reject(new Error('Authentication rejected')));
    await expect(router.push('/lazy')).rejects.toThrow();
    expect(recovery.state.failed).toBe(false);
    expect(await recovery.retry()).toBe(false);
    recovery.dispose();
  });
  it('clears the warning on successful alternate navigation', async () => {
    const { router, recovery } = await fixture(() => Promise.reject(new Error('error loading dynamically imported module')));
    await expect(router.push('/lazy')).rejects.toThrow();
    await router.push('/other');
    expect(recovery.state.failed).toBe(false);
    recovery.dispose();
  });
  it('removes router subscriptions when disposed', async () => {
    const { router, recovery } = await fixture(() => Promise.reject(new Error('error loading dynamically imported module')));
    recovery.dispose();
    const capture = router.onError(() => {});
    await expect(router.push('/lazy')).rejects.toThrow();
    expect(recovery.state.failed).toBe(false);
    capture();
  });
});

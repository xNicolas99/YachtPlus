import { reactive } from 'vue';

const chunkError = /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|unable to preload css|loading (?:css )?chunk .* failed/i;

export function createChunkRecovery(router) {
  const state = reactive({ failed: false, retrying: false, target: null });
  const removeError = router.onError((error, to) => {
    if (!chunkError.test(String(error?.message || ''))) return;
    state.failed = true;
    state.target = to?.fullPath || null;
  });
  const removeAfter = router.afterEach((to, from, failure) => {
    if (!failure) { state.failed = false; state.target = null; }
  });
  return {
    state,
    async retry() {
      if (state.retrying || !state.target) return false;
      state.retrying = true;
      try {
        const failure = await router.push(state.target);
        return !failure;
      } catch {
        return false;
      } finally {
        state.retrying = false;
      }
    },
    dispose() { removeError(); removeAfter(); }
  };
}

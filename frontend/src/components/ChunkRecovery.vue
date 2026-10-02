<template>
  <v-alert v-if="state.failed" type="error" class="mb-4" role="alert">
    This page could not be loaded. Check your connection and retry.
    <div class="mt-2 d-flex flex-wrap ga-2">
      <v-btn :loading="state.retrying" :disabled="state.retrying || !state.target" @click="recovery.retry()">Retry page</v-btn>
      <v-btn variant="text" @click="reload">Reload application</v-btn>
    </div>
    <small>Reloading the application discards unsaved inputs.</small>
  </v-alert>
</template>

<script>
import { createChunkRecovery } from '@/utils/chunkRecovery';
export default {
  data() {
    const recovery = createChunkRecovery(this.$router);
    return { recovery, state: recovery.state };
  },
  beforeUnmount() { this.recovery.dispose(); },
  methods: { reload() { window.location.reload(); } }
};
</script>

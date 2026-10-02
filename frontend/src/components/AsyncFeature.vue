<template>
  <component v-if="feature" :is="feature" v-bind="$attrs" @close="close" />
  <v-dialog v-else :model-value="true" max-width="480" @update:model-value="close" @keydown.esc="close">
    <v-card>
      <v-card-title>{{ name }}</v-card-title>
      <v-card-text>
        <div v-if="loading" role="status" aria-live="polite">Loading {{ name }}…</div>
        <v-alert v-else type="error" role="alert">
          {{ name }} could not be loaded. Check your connection and try again.
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-btn v-if="!loading" @click="load">Retry loading {{ name }}</v-btn>
        <v-btn @click="close">Close {{ name }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { markRaw } from 'vue';

export default {
  inheritAttrs: false,
  props: {
    loader: { type: Function, required: true },
    name: { type: String, required: true },
    timeout: { type: Number, default: 15000 }
  },
  emits: ['close'],
  data: () => ({ feature: null, loading: false, generation: 0, timer: null, abortLoad: null }),
  created() { this.load(); },
  beforeUnmount() { this.cancel(); },
  methods: {
    cancel() {
      this.generation += 1;
      clearTimeout(this.timer);
      this.timer = null;
      this.abortLoad?.();
      this.abortLoad = null;
      this.loading = false;
    },
    close() {
      this.cancel();
      this.$emit('close');
    },
    async load() {
      if (this.loading) return;
      const generation = ++this.generation;
      this.loading = true;
      const deadline = new Promise((_, reject) => {
        this.abortLoad = () => reject(new Error('Feature loading cancelled'));
        this.timer = setTimeout(() => reject(new Error('Feature loading timed out')), this.timeout);
      });
      try {
        const module = await Promise.race([Promise.resolve().then(this.loader), deadline]);
        const feature = module?.default || module;
        if (!feature || !(typeof feature === 'function' || feature.render || feature.setup || feature.template)) {
          throw new Error('Invalid feature');
        }
        if (generation === this.generation) this.feature = markRaw(feature);
      } catch {
        // Do not expose network URLs or exception details in the UI.
      } finally {
        if (generation === this.generation) {
          clearTimeout(this.timer);
          this.timer = null;
          this.abortLoad = null;
          this.loading = false;
        }
      }
    }
  }
};
</script>

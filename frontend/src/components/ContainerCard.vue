<template>
  <v-card tag="article" class="container-card d-flex flex-column fill-height" :class="{ 'container-card--attention': needsAttention }" :aria-label="`${container.name}: ${statusLabel}`">
    <div class="card-header d-flex align-start px-4 pt-4 pb-2">
      <div class="d-flex align-center flex-grow-1" style="min-width: 0">
        <span class="status-indicator mr-3" :class="statusClass" aria-hidden="true" />
        <div class="container-card__identity">
          <h3 class="text-subtitle-1 font-weight-bold text-truncate">
            <router-link :to="{ path: `/apps/${encodeURIComponent(container.name)}/info` }" :title="container.name">{{ container.name }}</router-link>
          </h3>
          <div class="container-card__status">
            <span>{{ statusLabel }}</span><span v-if="stale" class="yp-tag">Snapshot</span>
          </div>
        </div>
      </div>
      <div class="actions d-flex ml-2">
        <v-btn icon size="small" variant="text" :aria-label="`View logs for ${container.name}`" title="View logs" @click.stop="$emit('logs', container.name)"><v-icon>mdi-file-document-outline</v-icon></v-btn>
        <v-menu location="bottom end">
          <template #activator="{ props }">
            <v-btn v-bind="props" icon size="small" variant="text" :disabled="busy" :loading="busy" :aria-label="`Actions for ${container.name}`" title="Container actions" @click.stop><v-icon>mdi-dots-vertical</v-icon></v-btn>
          </template>
          <v-list density="compact" width="180">
            <v-list-item :disabled="busy" prepend-icon="mdi-restart" @click="$emit('action', 'restart')">Restart</v-list-item>
            <v-list-item :disabled="busy" :prepend-icon="state.Status === 'running' ? 'mdi-stop' : 'mdi-play'" @click="$emit('action', state.Status === 'running' ? 'stop' : 'start')">{{ state.Status === 'running' ? 'Stop' : 'Start' }}</v-list-item>
            <v-divider />
            <v-list-item :disabled="busy" prepend-icon="mdi-delete" color="error" @click="$emit('action', 'remove')">Remove</v-list-item>
          </v-list>
        </v-menu>
      </div>
    </div>
    <p v-if="problemDescription" class="container-card__problem px-4 pb-2">{{ problemDescription }}</p>
    <v-divider class="mx-4" />
    <v-card-text class="flex-grow-1 py-4">
      <template v-if="stats">
        <div v-for="metric in metrics" :key="metric.label" class="stat-row">
          <div class="d-flex justify-space-between text-caption mb-1"><span class="yp-muted">{{ metric.label }}</span><strong :class="usageColor(metric.value, true)">{{ metric.value.toFixed(1) }}%</strong></div>
          <v-progress-linear :model-value="Math.min(100, metric.value)" :color="usageColor(metric.value)" height="6" rounded :aria-label="`${metric.label} usage`" />
        </div>
        <p class="text-caption yp-muted mt-2">{{ stats.mem_current }} / {{ stats.mem_total }} memory</p>
        <p v-if="stale" class="text-caption yp-muted mt-2">Usage from the last successful update.</p>
      </template>
      <div v-else class="container-card__no-stats yp-muted">
        <v-progress-circular v-if="loading && !stale && state.Status === 'running'" indeterminate size="20" width="2" color="primary" />
        <v-icon v-else size="22" aria-hidden="true">{{ state.Status === 'running' ? 'mdi-chart-line' : 'mdi-power-off' }}</v-icon>
        <span>{{ state.Status !== 'running' ? 'No live usage while stopped' : loading && !stale ? 'Loading usage…' : 'Usage unavailable' }}</span>
      </div>
    </v-card-text>
    <div class="card-footer px-4 pb-4 yp-muted text-caption"><v-icon size="small" class="mr-1" aria-hidden="true">mdi-image-outline</v-icon><span :title="imageName">{{ imageName }}</span></div>
  </v-card>
</template>

<script>
import { containerHealth } from "@/utils/containerViews";

export default {
  name: "ContainerCard",
  props: {
    container: { type: Object, required: true }, stats: { type: Object, default: null },
    stale: { type: Boolean, default: false }, loading: { type: Boolean, default: false }, busy: { type: Boolean, default: false },
  },
  emits: ["logs", "action"],
  computed: {
    state() { return this.container.State || {}; },
    needsAttention() {
      return containerHealth(this.container) === "unhealthy" || ["restarting", "dead"].includes(this.state.Status) || this.state.OOMKilled ||
        (this.state.Status === "exited" && Number(this.state.ExitCode) > 0);
    },
    statusLabel() {
      const status = this.state.Status || "Unknown";
      const health = containerHealth(this.container);
      return health !== 'none' ? `${status} · ${health}` : status;
    },
    statusClass() {
      if (this.needsAttention) return "warning";
      return this.state.Status === "running" ? "running" : "stopped";
    },
    problemDescription() {
      if (this.state.OOMKilled) return "Stopped because the container ran out of memory.";
      if (containerHealth(this.container) === "unhealthy") return "The health check is failing. Open the logs to investigate.";
      if (this.state.Status === "restarting") return "The container is restarting. Check the logs if this continues.";
      if (this.state.Status === "dead") return "Docker reports this container as dead.";
      if (this.state.Status === "exited" && Number(this.state.ExitCode) > 0) return `Exited with code ${this.state.ExitCode}.`;
      return "";
    },
    imageName() { return this.container.Config?.Image || this.container.Image || "Unknown image"; },
    metrics() {
      return [{ label: "CPU", value: this.stats?.cpu_percent }, { label: "Memory", value: this.stats?.mem_percent }]
        .map(metric => ({ ...metric, value: Number.isFinite(Number(metric.value)) ? Math.max(0, Number(metric.value)) : 0 }));
    },
  },
  methods: {
    usageColor(value, text = false) {
      const color = value < 50 ? "success" : value < 80 ? "warning" : "error";
      return text ? `text-${color}` : color;
    },
  },
};
</script>

<style scoped>
.container-card { border: 1px solid var(--yp-border-soft); border-radius: var(--yp-radius-lg); background: var(--yp-surface); box-shadow: var(--yp-shadow-1); }
.container-card--attention { border-color: var(--yp-warn); }
.container-card__identity { flex: 1; min-width: 0; }
.container-card__identity h3 a { color: var(--yp-text); text-decoration: none; border-radius: 3px; }
.container-card__identity h3 a:hover { color: var(--yp-accent); text-decoration: underline; }
.container-card__status { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: var(--yp-muted); font-size: 12px; text-transform: capitalize; }
.container-card__problem { font-size: 12px; color: var(--yp-muted); }
.status-indicator { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--yp-muted); }
.status-indicator.running { background: var(--yp-ok); box-shadow: 0 0 0 3px var(--yp-ok-soft); }
.status-indicator.warning { background: var(--yp-warn); box-shadow: 0 0 0 3px var(--yp-warn-soft); }
.stat-row + .stat-row { margin-top: 14px; }
.card-footer { display: flex; align-items: center; min-width: 0; }.card-footer span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.container-card__no-stats { min-height: 105px; display: flex; flex-direction: column; gap: 8px; justify-content: center; align-items: center; font-size: 12px; text-align: center; }
</style>

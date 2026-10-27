<template>
  <section class="yp-dashboard yp-page" aria-label="Dashboard">
    <PageHeader title="Dashboard">
      <template #subtitle>
        Overview of <span class="yp-mono">{{ hostLabel }}</span>
        <template v-if="hasSnapshot"> · {{ overview.containers.total }} {{ overview.containers.total === 1 ? 'container' : 'containers' }} across {{ overview.projects.total }} {{ overview.projects.total === 1 ? 'stack' : 'stacks' }}</template>
      </template>
      <template #actions>
        <v-menu>
          <template #activator="{ props }">
            <v-btn v-bind="props" variant="outlined" size="small" prepend-icon="mdi-clock-outline" append-icon="mdi-chevron-down" aria-label="Change dashboard refresh interval">
              {{ pollingIntervalText }}
            </v-btn>
          </template>
          <v-list density="compact">
            <v-list-item v-for="interval in pollingOptions" :key="interval.value" :active="pollingInterval === interval.value" @click="setPollingInterval(interval.value)">
              <v-list-item-title>{{ interval.text }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        <v-btn :icon="polling && pollingInterval ? 'mdi-pause' : 'mdi-play'" variant="tonal" size="small" :aria-label="polling && pollingInterval ? 'Pause automatic refresh' : 'Resume automatic refresh'" @click="togglePolling" />
        <v-btn variant="outlined" size="small" prepend-icon="mdi-refresh" :loading="loading" :disabled="loading" @click="refresh">Refresh</v-btn>
        <v-btn color="primary" size="small" prepend-icon="mdi-plus" to="/apps/deploy">New container</v-btn>
      </template>
    </PageHeader>

    <div class="yp-dashboard-status" role="status" aria-live="polite" aria-atomic="true">
      <span class="yp-chip" :class="connectionError ? 'err' : isStale ? 'warn' : hasSnapshot ? 'run' : 'idle'">
        <span class="d" aria-hidden="true" />{{ connectionLabel }}
      </span>
      <span v-if="lastUpdatedAt" class="yp-muted">Last successful update: <time :datetime="new Date(lastUpdatedAt).toISOString()">{{ lastUpdatedText }}</time></span>
      <span v-else class="yp-muted">No verified data available yet.</span>
      <span v-if="loading && hasSnapshot" class="yp-muted">Refreshing…</span>
    </div>

    <v-alert v-if="connectionError" :type="hasSnapshot ? 'warning' : 'error'" variant="tonal" class="mb-5">
      <strong>{{ hasSnapshot ? 'Dashboard update failed.' : 'Cannot load the dashboard.' }}</strong>
      {{ errorReason }} {{ hasSnapshot ? 'The values below are from the last successful update and may be outdated.' : 'Try again after the connection is restored.' }}
      <template #append><v-btn variant="text" :disabled="loading" @click="refresh">Retry</v-btn></template>
    </v-alert>
    <v-alert v-else-if="hasSnapshot && isStale" type="info" variant="tonal" class="mb-5">
      {{ polling && pollingInterval ? 'A fresh update is overdue. These values are a previous snapshot.' : 'Automatic refresh is paused. These values are a snapshot, not live readings.' }}
    </v-alert>

    <div v-if="loading && !hasSnapshot" class="yp-dashboard-loading" role="status" aria-live="polite">
      <v-progress-linear indeterminate color="primary" class="mb-3" />
      Loading containers and resource usage…
    </div>

    <div class="yp-kpi-grid" :aria-busy="loading">
      <article class="yp-card yp-card-pad">
        <div class="yp-kpi-heading"><h2>Containers</h2><v-icon size="18" aria-hidden="true">mdi-package-variant-closed</v-icon></div>
        <router-link to="/apps" class="yp-kpi-link" aria-label="View all containers"><span class="yp-kpi-num yp-tnum">{{ count(overview.containers.total) }}</span></router-link>
        <div class="yp-kpi-breakdown">
          <router-link :to="{ path: '/apps', query: { status: 'running' } }"><span class="yp-dot running" aria-hidden="true" />Running <strong>{{ count(overview.containers.running) }}</strong></router-link>
          <router-link :to="{ path: '/apps', query: { health: 'unhealthy' } }"><span class="yp-dot unhealthy" aria-hidden="true" />Unhealthy <strong>{{ count(overview.containers.unhealthy) }}</strong></router-link>
          <router-link :to="{ path: '/apps', query: { status: 'stopped' } }"><span class="yp-dot stopped" aria-hidden="true" />Stopped <strong>{{ count(overview.containers.stopped) }}</strong></router-link>
        </div>
      </article>
      <article class="yp-card yp-card-pad">
        <div class="yp-kpi-heading"><h2>Images</h2><v-icon size="18" aria-hidden="true">mdi-layers</v-icon></div>
        <router-link to="/resources/images" class="yp-kpi-link" aria-label="View images"><span class="yp-kpi-num yp-tnum">{{ count(overview.images.total) }}</span></router-link>
        <p class="yp-kpi-label">Total size <strong>{{ hasSnapshot ? formatBytes(overview.images.total_size) : '—' }}</strong></p>
      </article>
      <article class="yp-card yp-card-pad">
        <div class="yp-kpi-heading"><h2>Volumes</h2><v-icon size="18" aria-hidden="true">mdi-database</v-icon></div>
        <router-link to="/resources/volumes" class="yp-kpi-link" aria-label="View volumes"><span class="yp-kpi-num yp-tnum">{{ count(overview.volumes.total) }}</span></router-link>
        <p class="yp-kpi-label">{{ count(overview.volumes.unused) }} unused · {{ count(overview.volumes.in_use) }} in use</p>
      </article>
      <article class="yp-card yp-card-pad">
        <div class="yp-kpi-heading"><h2>Networks</h2><v-icon size="18" aria-hidden="true">mdi-lan</v-icon></div>
        <router-link to="/resources/networks" class="yp-kpi-link" aria-label="View networks"><span class="yp-kpi-num yp-tnum">{{ count(overview.networks.total) }}</span></router-link>
        <p class="yp-kpi-label">{{ count(overview.networks.custom) }} custom · {{ count(overview.networks.default) }} default</p>
      </article>
    </div>

    <v-alert v-if="hasSnapshot && attentionContainers.length" type="warning" variant="tonal" class="mt-6 yp-attention-alert" title="Containers need attention">
      {{ attentionContainers.length }} {{ attentionContainers.length === 1 ? 'container is' : 'containers are' }} unhealthy, restarting, or stopped after an error. They appear first below.
      <template #append><v-btn variant="text" to="/apps">Review containers</v-btn></template>
    </v-alert>
    <div class="yp-section-head mt-7 mb-4"><h2 class="yp-section-title">Containers</h2><span class="yp-tag">{{ hasSnapshot ? inventory.length : '—' }}</span></div>
    <div v-if="hasSnapshot && !inventory.length" class="yp-empty-state text-center pa-8">
      <v-icon size="48" color="medium-emphasis" class="mb-3" aria-hidden="true">mdi-docker</v-icon>
      <h3 class="text-h6 mb-2">No containers yet</h3>
      <p class="yp-muted mb-5">Deploy a template or create a container to start managing your services.</p>
      <div class="yp-empty-actions"><v-btn color="primary" to="/templates">Browse templates</v-btn><v-btn variant="outlined" to="/apps/deploy">New container</v-btn></div>
    </div>
    <div v-if="inventory.length" class="yp-container-grid">
      <ContainerCard v-for="app in sortedContainers" :key="app.Id || app.name" :container="app" :stats="stats[app.name]" :stale="isStale" :loading="loading" :busy="Boolean(pendingActions[app.name])" @logs="handleLogs(app.name)" @action="action => handleContainerAction(action, app.name)" />
    </div>
  </section>
</template>

<script>
import axios from "axios";
import { runTrackedOperation } from "@/utils/operations";
import ContainerCard from "@/components/ContainerCard.vue";
import PageHeader from "@/components/PageHeader.vue";
import { containerHealth } from "@/utils/containerViews";

const EMPTY_OVERVIEW = () => ({
  containers: { total: 0, running: 0, stopped: 0, unhealthy: 0 },
  projects: { total: 0 }, images: { total: 0, total_size: 0 },
  volumes: { total: 0, in_use: 0, unused: 0 }, networks: { total: 0, custom: 0, default: 0 },
});

export default {
  components: { ContainerCard, PageHeader },
  data() {
    return {
      inventory: [], stats: {}, overview: EMPTY_OVERVIEW(), pendingActions: Object.create(null),
      loading: false, connectionError: false, errorReason: '', lastUpdatedAt: null, now: Date.now(),
      statsInterval: null, ageInterval: null, polling: true, pollingInterval: 5000,
      hostLabel: window.location.hostname || "localhost",
      pollingOptions: [
        { text: "2 seconds", value: 2000 }, { text: "5 seconds", value: 5000 },
        { text: "10 seconds", value: 10000 }, { text: "30 seconds", value: 30000 },
        { text: "60 seconds", value: 60000 }, { text: "Off", value: 0 },
      ],
    };
  },
  computed: {
    hasSnapshot() { return this.lastUpdatedAt !== null; },
    isStale() {
      return this.hasSnapshot && (this.connectionError || !this.polling || !this.pollingInterval ||
        this.now - this.lastUpdatedAt > Math.max(15000, this.pollingInterval * 2 + 2000));
    },
    connectionLabel() {
      if (this.connectionError) return "Connection unavailable";
      if (!this.hasSnapshot) return this.loading ? "Connecting…" : "Not connected";
      if (!this.polling || !this.pollingInterval) return "Automatic refresh paused";
      return this.isStale ? "Update overdue" : "Connected";
    },
    lastUpdatedText() {
      return this.lastUpdatedAt === null ? "Never" : new Date(this.lastUpdatedAt).toLocaleTimeString();
    },
    pollingIntervalText() { return this.pollingInterval ? `${this.pollingInterval / 1000}s` : "Off"; },
    attentionContainers() { return this.inventory.filter(this.needsAttention); },
    sortedContainers() {
      return [...this.inventory].sort((a, b) => Number(this.needsAttention(b)) - Number(this.needsAttention(a)) || a.name.localeCompare(b.name));
    },
  },
  methods: {
    count(value) { return this.hasSnapshot ? value : "—"; },
    needsAttention(container) {
      const state = container.State || {};
      return containerHealth(container) === "unhealthy" || ["restarting", "dead"].includes(state.Status) ||
        state.OOMKilled || (state.Status === "exited" && Number(state.ExitCode) > 0);
    },
    normalizeSnapshot(inventory, overview, readings) {
      if (!Array.isArray(inventory) || !readings || typeof readings !== "object" || Array.isArray(readings)) throw new Error("Invalid dashboard response");
      if (overview?.availability && Object.values(overview.availability).some(available => available === false)) {
        throw Object.assign(new Error("Dashboard sources unavailable"), { code: "DASHBOARD_PARTIAL" });
      }
      const nextOverview = EMPTY_OVERVIEW();
      for (const [group, fields] of Object.entries(nextOverview)) {
        for (const key of Object.keys(fields)) {
          const value = overview?.[group]?.[key];
          if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw new Error("Incomplete dashboard response");
          fields[key] = value;
        }
      }
      const nextStats = {};
      for (const app of inventory) {
        if (typeof app?.name !== "string" || !app.State || typeof app.State.Status !== "string") throw new Error("Invalid container response");
        const stat = readings[app.name];
        if (!stat) continue;
        const cpu = stat.cpu_percent;
        const memory = stat.memory_percent;
        if (!Number.isFinite(cpu) || !Number.isFinite(memory)) continue;
        nextStats[app.name] = {
          cpu_percent: Math.max(0, cpu), mem_percent: Math.max(0, memory),
          mem_current: this.formatBytes(stat.memory_usage ?? stat.memory_usage_mb * 1024 * 1024),
          mem_total: this.formatBytes(stat.memory_limit ?? stat.memory_limit_mb * 1024 * 1024),
        };
      }
      return { inventory, overview: nextOverview, stats: nextStats };
    },
    pollAll() {
      if (this._disposed) return Promise.resolve(false);
      if (this._refreshPromise) return this._refreshPromise;
      this.loading = true;
      const controller = new AbortController();
      this._requestController = controller;
      const options = { timeout: 15000, signal: controller.signal };
      this._refreshPromise = Promise.all([
        axios.get("/apps/", options), axios.get("/dashboard/stats", options), axios.get("/containers/stats", options),
      ]).then(([apps, overview, readings]) => {
        if (this._disposed) return false;
        const snapshot = this.normalizeSnapshot(apps.data, overview.data, readings.data);
        this.inventory = snapshot.inventory;
        this.overview = snapshot.overview;
        this.stats = snapshot.stats;
        this.lastUpdatedAt = Date.now();
        this.now = this.lastUpdatedAt;
        this.connectionError = false;
        this.errorReason = '';
        return true;
      }).catch(error => {
        controller.abort();
        if (!this._disposed) {
          this.connectionError = true;
          this.errorReason = error.code === 'DASHBOARD_PARTIAL'
            ? 'Some resource or stack data is unavailable.'
            : 'A complete dashboard update could not be verified.';
        }
        return false;
      }).finally(() => {
        if (!this._disposed) this.loading = false;
        this._refreshPromise = null;
        this._requestController = null;
      });
      return this._refreshPromise;
    },
    startStatsPolling() {
      if (this.statsInterval) clearInterval(this.statsInterval);
      this.statsInterval = null;
      if (!this.pollingInterval || !this.polling) return;
      this.statsInterval = setInterval(() => { if (!document.hidden) this.pollAll(); }, this.pollingInterval);
    },
    togglePolling() {
      if (!this.pollingInterval) return this.setPollingInterval(5000);
      this.polling = !this.polling;
      this.startStatsPolling();
      if (this.polling) this.pollAll();
    },
    setPollingInterval(value) {
      if (!this.pollingOptions.some(option => option.value === value)) return;
      this.pollingInterval = value;
      this.polling = value !== 0;
      try { localStorage.setItem("dashboard_polling_interval", String(value)); } catch (_) { /* Storage is optional. */ }
      this.startStatsPolling();
      if (this.polling) this.pollAll();
    },
    refresh() { return this.pollAll(); },
    handleLogs(name) { this.$router.push({ path: `/apps/${encodeURIComponent(name)}/logs` }); },
    async handleContainerAction(action, name) {
      if (!["start", "stop", "restart", "remove"].includes(action) || this.pendingActions[name]) return;
      if (action === "remove" && !window.confirm(`Remove container ${name}? Data outside mounted volumes will be lost.`)) return;
      this.pendingActions[name] = action;
      try {
        await runTrackedOperation(axios, { kind: "container.action", resource: name, action });
        const messages = { start: "started", stop: "stopped", restart: "restarted", remove: "removed" };
        this.$store.commit("snackbar/setMessage", `${name} ${messages[action]}.`);
        await this.refresh();
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally { delete this.pendingActions[name]; }
    },
    formatBytes(value) {
      const bytes = Number(value);
      if (!Number.isFinite(bytes) || bytes < 0) return "Unavailable";
      if (bytes === 0) return "0 B";
      const unit = Math.min(5, Math.max(0, Math.floor(Math.log(bytes) / Math.log(1024))));
      return `${Number((bytes / 1024 ** unit).toFixed(1))} ${["B", "KB", "MB", "GB", "TB", "PB"][unit]}`;
    },
  },
  created() {
    this._disposed = false;
    try {
      const saved = Number(localStorage.getItem("dashboard_polling_interval"));
      if (localStorage.getItem("dashboard_polling_interval") !== null && this.pollingOptions.some(option => option.value === saved)) this.pollingInterval = saved;
    } catch (_) { /* Storage is optional. */ }
    this.polling = this.pollingInterval !== 0;
    this.refresh();
    this.startStatsPolling();
    this.ageInterval = setInterval(() => { this.now = Date.now(); }, 1000);
    this._onVisibility = () => { if (!document.hidden && this.polling && this.pollingInterval) this.pollAll(); };
    document.addEventListener("visibilitychange", this._onVisibility);
  },
  beforeUnmount() {
    this._disposed = true;
    this._requestController?.abort();
    clearInterval(this.statsInterval);
    clearInterval(this.ageInterval);
    document.removeEventListener("visibilitychange", this._onVisibility);
  },
};
</script>

<style scoped>
.yp-dashboard-status, .yp-section-head, .yp-empty-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.yp-dashboard-status { margin-bottom: 20px; font-size: 13px; }
.yp-dashboard-loading { padding: 18px 0; color: var(--yp-muted); }
.yp-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.yp-kpi-heading { display: flex; align-items: center; justify-content: space-between; color: var(--yp-muted); margin-bottom: 14px; }
.yp-kpi-heading h2 { font-size: 13px; font-weight: 600; }
.yp-kpi-link { display: inline-block; padding: 3px 0; text-decoration: none; border-radius: 4px; }
.yp-kpi-link:hover { text-decoration: underline; text-decoration-color: var(--yp-accent); }
.yp-kpi-breakdown { display: flex; gap: 5px 12px; flex-wrap: wrap; margin-top: 12px; }
.yp-kpi-breakdown a { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--yp-muted); text-decoration: none; padding: 3px 0; }
.yp-kpi-breakdown a:hover { color: var(--yp-text); text-decoration: underline; }
.yp-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--yp-muted); }
.yp-dot.running { background: var(--yp-ok); }.yp-dot.unhealthy { background: var(--yp-warn); }.yp-dot.stopped { background: var(--yp-muted); }
.yp-section-title { color: var(--yp-text); font-size: 18px; font-weight: 600; }
.yp-container-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: 16px; }
.yp-empty-state { background: var(--yp-surface); border: 1px dashed var(--yp-border); border-radius: var(--yp-radius-lg); }
.yp-empty-actions { justify-content: center; }
@media (max-width: 1200px) { .yp-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .yp-kpi-grid { grid-template-columns: 1fr; }.yp-dashboard-status { align-items: flex-start; flex-direction: column; gap: 7px; } }
@media (max-width: 600px) {
  .yp-attention-alert { grid-template-areas: 'prepend content' '. append'; grid-template-columns: min-content minmax(0, 1fr); }
  .yp-attention-alert :deep(.v-alert__append) { margin: 12px 0 0; justify-self: start; }
  .yp-attention-alert :deep(.v-alert-title) { white-space: normal; overflow-wrap: normal; }
}
</style>

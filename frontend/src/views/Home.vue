<template>
  <v-container fluid class="pa-6 yp-dashboard">
    <!-- Page head -->
    <div class="yp-page-head">
      <div>
        <h1 class="yp-page-title">Dashboard</h1>
        <p class="yp-page-sub">
          Overview of <span class="yp-mono">{{ hostLabel }}</span>
          ·
          <span class="yp-mono">{{ overview.containers.total }}</span> containers
          across
          <span class="yp-mono">{{ overview.projects.total }}</span> stacks
        </p>
      </div>

      <div class="d-flex align-center" style="gap:8px;">
        <!-- Polling cadence -->
        <v-menu>
          <template v-slot:activator="{ props }">
            <v-btn
              variant="outlined"
              color="primary"
              class="text-none yp-action-btn"
              v-bind="props"
              prepend-icon="mdi-clock-outline"
              append-icon="mdi-chevron-down"
              size="small"
              aria-label="Change dashboard polling interval"
            >
              {{ pollingIntervalText }}
            </v-btn>
          </template>
          <v-list density="compact">
            <v-list-item
              v-for="interval in pollingOptions"
              :key="interval.value"
              @click="setPollingInterval(interval.value)"
              :active="pollingInterval === interval.value"
              color="primary"
            >
              <v-list-item-title>{{ interval.text }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>

        <v-btn
          :icon="polling ? 'mdi-pause' : 'mdi-play'"
          :color="polling ? 'warning' : 'success'"
          variant="tonal"
          size="small"
          @click="togglePolling"
          :aria-label="polling ? 'Pause Auto-Refresh' : 'Resume Auto-Refresh'"
        >
          <v-icon>{{ polling ? 'mdi-pause' : 'mdi-play' }}</v-icon>
          <v-tooltip activator="parent" location="bottom">
            {{ polling ? 'Pause Auto-Refresh' : 'Resume Auto-Refresh' }}
          </v-tooltip>
        </v-btn>

        <v-btn
          color="primary"
          variant="flat"
          size="small"
          class="text-none yp-action-btn"
          prepend-icon="mdi-refresh"
          @click="refresh()"
          :loading="loading"
        >
          Refresh
        </v-btn>

        <v-btn
          color="primary"
          variant="flat"
          size="small"
          class="text-none yp-action-btn yp-action-primary"
          prepend-icon="mdi-plus"
          to="/apps/deploy"
        >
          New Container
        </v-btn>
      </div>
    </div>

    <!-- KPI strip -->
    <div class="yp-kpi-grid">
      <!-- Containers -->
      <div class="yp-card yp-card-pad">
        <div class="d-flex align-center justify-space-between mb-3">
          <span class="yp-kpi-eyebrow">Containers</span>
          <v-icon size="16" color="medium-emphasis">mdi-package-variant-closed</v-icon>
        </div>
        <div class="yp-kpi-num yp-tnum">{{ overview.containers.total }}</div>
        <div class="d-flex flex-wrap" style="gap:14px; margin-top:14px;">
          <div class="yp-row" style="gap:6px;">
            <span class="yp-dot" :style="{ background: 'var(--yp-ok)' }"></span>
            <span class="yp-kpi-leg">Running</span>
            <span class="yp-mono yp-tnum yp-kpi-val">{{ overview.containers.running }}</span>
          </div>
          <div class="yp-row" style="gap:6px;">
            <span class="yp-dot" :style="{ background: 'var(--yp-warn)' }"></span>
            <span class="yp-kpi-leg">Unhealthy</span>
            <span class="yp-mono yp-tnum yp-kpi-val">{{ overview.containers.unhealthy }}</span>
          </div>
          <div class="yp-row" style="gap:6px;">
            <span class="yp-dot" :style="{ background: 'var(--yp-err)' }"></span>
            <span class="yp-kpi-leg">Stopped</span>
            <span class="yp-mono yp-tnum yp-kpi-val">{{ overview.containers.stopped }}</span>
          </div>
        </div>
      </div>

      <!-- Images -->
      <div class="yp-card yp-card-pad">
        <div class="d-flex align-center justify-space-between mb-3">
          <span class="yp-kpi-eyebrow">Images</span>
          <v-icon size="16" color="medium-emphasis">mdi-layers</v-icon>
        </div>
        <div class="yp-kpi-num yp-tnum">{{ overview.images.total }}</div>
        <div class="yp-kpi-label">
          Total size
          <span class="yp-mono" style="color: var(--yp-text); margin-left:4px;">
            {{ formatBytes(overview.images.total_size) }}
          </span>
        </div>
      </div>

      <!-- Volumes -->
      <div class="yp-card yp-card-pad">
        <div class="d-flex align-center justify-space-between mb-3">
          <span class="yp-kpi-eyebrow">Volumes</span>
          <v-icon size="16" color="medium-emphasis">mdi-database</v-icon>
        </div>
        <div class="yp-kpi-num yp-tnum">{{ overview.volumes.total }}</div>
        <div class="yp-kpi-label">
          <span class="yp-mono" style="color: var(--yp-warn);">{{ overview.volumes.unused }}</span>
          unused ·
          <span class="yp-mono">{{ overview.volumes.in_use }}</span>
          in use
        </div>
      </div>

      <!-- Networks -->
      <div class="yp-card yp-card-pad">
        <div class="d-flex align-center justify-space-between mb-3">
          <span class="yp-kpi-eyebrow">Networks</span>
          <v-icon size="16" color="medium-emphasis">mdi-lan</v-icon>
        </div>
        <div class="yp-kpi-num yp-tnum">{{ overview.networks.total }}</div>
        <div class="yp-kpi-label">
          <span class="yp-mono">{{ overview.networks.custom }}</span> custom ·
          <span class="yp-mono">{{ overview.networks.default }}</span> default
        </div>
      </div>
    </div>

    <!-- Active containers -->
    <div class="d-flex align-center mt-8 mb-4" style="gap:12px;">
      <h2 class="yp-section-title">Active Containers</h2>
      <span class="yp-tag yp-mono yp-tnum">{{ apps.length }}</span>
    </div>

    <v-fade-transition>
      <div
        v-if="!loading && apps.length === 0"
        class="yp-empty-state text-center pa-8"
      >
        <v-icon size="56" color="medium-emphasis" class="mb-3">mdi-docker</v-icon>
        <h3 class="text-h6 font-weight-medium mb-2">No containers running</h3>
        <p class="text-body-2 yp-muted mb-6">
          Your dashboard looks a bit empty. Start a container to see stats here.
        </p>
        <div class="d-flex justify-center" style="gap:12px;">
          <v-btn color="primary" to="/templates" prepend-icon="mdi-store">
            Deploy from Templates
          </v-btn>
          <v-btn variant="outlined" to="/apps" prepend-icon="mdi-plus">
            Launch New App
          </v-btn>
        </div>
      </div>
    </v-fade-transition>

    <div v-if="apps.length > 0" class="yp-container-grid">
      <ContainerCard
        v-for="app in sortByTitle(apps)"
        :key="app.name"
        :container="app"
        :stats="stats[app.name]"
        @click="handleAppClick(app.name)"
        @logs="handleLogs(app.name)"
        @action="(action) => handleContainerAction(action, app.name)"
        class="cursor-pointer"
      />
    </div>
  </v-container>
</template>

<script>
import { mapActions, mapState } from "vuex";
import axios from "axios";
import ContainerCard from "@/components/ContainerCard.vue";

export default {
  components: {
    ContainerCard
  },
  data() {
    return {
      stats: {},
      statsInterval: null,
      polling: true,
      pollingInterval: 5000,
      loading: false,
      hostLabel: 'prod-01',
      pollingOptions: [
        { text: "2s (Fast)", value: 2000 },
        { text: "5s (Normal)", value: 5000 },
        { text: "10s (Slow)", value: 10000 },
        { text: "30s", value: 30000 },
        { text: "60s", value: 60000 },
        { text: "Off", value: 0 }
      ],
      overview: {
        containers: { total: 0, running: 0, stopped: 0, unhealthy: 0 },
        projects: { total: 0, active: 0, inactive: 0 },
        images: { total: 0, used: 0, dangling: 0, total_size: 0 },
        volumes: { total: 0, in_use: 0, unused: 0 },
        networks: { total: 0, custom: 0, default: 0 }
      }
    };
  },
  computed: {
    ...mapState("apps", ["apps"]),
    pollingIntervalText() {
      if (this.pollingInterval === 0) return "Off";
      return (this.pollingInterval / 1000) + "s";
    }
  },
  methods: {
    ...mapActions({
      readApps: "apps/readApps"
    }),
    async fetchOverviewStats() {
      try {
        const response = await axios.get("/dashboard/stats");
        // Merge into the existing structure rather than replacing it
        // wholesale. If the backend ever returns a partial / older
        // shape, the template still has its initial `{ total, running,
        // stopped, … }` zeros to render against instead of throwing
        // `can't access property "total" of undefined`.
        const data = response.data || {};
        const next = { ...this.overview };
        for (const key of Object.keys(this.overview)) {
          next[key] = { ...this.overview[key], ...(data[key] || {}) };
        }
        // Also pick up unexpected top-level keys (e.g. "resources",
        // "info") so they're still available where consumed.
        for (const key of Object.keys(data)) {
          if (!(key in next)) next[key] = data[key];
        }
        this.overview = next;
      } catch (e) {
        console.error("Failed to fetch dashboard stats", e);
      }
    },
    startStatsPolling() {
      if (this.statsInterval) clearInterval(this.statsInterval);
      if (this.pollingInterval === 0) return;

      this.pollAll();

      this.statsInterval = setInterval(() => {
        if (this.polling) {
          this.pollAll();
        }
      }, this.pollingInterval);
    },
    async pollAll() {
      try {
        const [_, statsResponse] = await Promise.all([
          this.fetchOverviewStats(),
          axios.get("/containers/stats", { skipAuthRefresh: true })
        ]);
        const statsData = statsResponse.data;

        if (this.apps) {
          this.apps.forEach(app => {
            const stat = statsData[app.name];
            if (stat) {
              let memUsage = stat.memory_usage;
              let memLimit = stat.memory_limit;

              if (memUsage === undefined && stat.memory_usage_mb !== undefined) {
                memUsage = stat.memory_usage_mb * 1024 * 1024;
              }
              if (memLimit === undefined && stat.memory_limit_mb !== undefined) {
                memLimit = stat.memory_limit_mb * 1024 * 1024;
              }

              this.stats[app.name] = {
                cpu_percent: stat.cpu_percent,
                mem_percent: stat.memory_percent,
                mem_current: this.formatBytes(memUsage),
                mem_total: this.formatBytes(memLimit),
                name: app.name
              };
            } else if (app.State.Status !== 'running') {
              this.stats[app.name] = null;
            }
          });
        }
      } catch (error) {
        console.error("Failed to fetch global stats", error);
      }
    },
    togglePolling() {
      this.polling = !this.polling;
    },
    setPollingInterval(val) {
      this.pollingInterval = val;
      localStorage.setItem("dashboard_polling_interval", val);
      this.startStatsPolling();
    },
    async refresh() {
      this.loading = true;
      try {
        await this.readApps();
        await this.pollAll();
      } finally {
        this.loading = false;
      }
    },
    sortByTitle(arr) {
      if (!arr) return [];
      return [...arr].sort((a, b) => a.name.localeCompare(b.name));
    },
    handleAppClick(appName) {
      this.$router.push({ path: `/apps/${appName}/info` });
    },
    handleLogs(appName) {
      this.$router.push({ path: `/apps/${appName}/logs` });
    },
    async handleContainerAction(action, appName) {
      try {
        this.loading = true;
        await axios.get(`/containers/${appName}/${action}`);
        setTimeout(() => { this.refresh(); }, 1000);
        this.$store.commit('snackbar/setSnack', { message: `Container ${action}ed successfully.`, color: 'success' }, { root: true });
      } catch (err) {
        this.$store.commit('snackbar/setErr', err, { root: true });
      } finally {
        this.loading = false;
      }
    },
    formatBytes(bytes, decimals = 2) {
      if (!+bytes) return '0 B';
      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
    }
  },
  async created() {
    const stored = localStorage.getItem("dashboard_polling_interval");
    if (stored !== null) {
      this.pollingInterval = parseInt(stored);
    }

    this.loading = true;
    try {
      await Promise.all([
        this.readApps(),
        this.fetchOverviewStats()
      ]);
    } finally {
      this.loading = false;
    }
    this.startStatsPolling();
  },
  beforeUnmount() {
    if (this.statsInterval) {
      clearInterval(this.statsInterval);
    }
  }
};
</script>

<style scoped>
.yp-dashboard {
  background: var(--yp-bg);
  min-height: 100%;
}

.yp-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.yp-kpi-eyebrow {
  color: var(--yp-muted);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.yp-kpi-leg { font-size: 12px; color: var(--yp-muted); }
.yp-kpi-val { font-size: 12px; color: var(--yp-text); }

.yp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.yp-section-title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--yp-text);
  margin: 0;
}

.yp-action-btn {
  letter-spacing: 0;
  font-weight: 500;
}
.yp-action-primary {
  /* primary CTA matches the design's accent button */
  color: #062231 !important;
  font-weight: 600 !important;
}

.yp-container-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.yp-empty-state {
  border: 1px dashed var(--yp-border);
  border-radius: var(--yp-radius-lg);
  background: var(--yp-surface);
}
</style>

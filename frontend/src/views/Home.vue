<template>
  <v-container fluid class="pa-6 dashboard-container">
    <!-- Header Section -->
    <div class="d-flex flex-wrap align-center justify-space-between mb-6 gap-2">
      <div>
        <h1 class="text-h4 font-weight-bold">Dashboard</h1>
        <div class="text-subtitle-2 text-medium-emphasis">Overview of your Docker environment</div>
      </div>

      <div class="d-flex align-center controls-wrapper">
        <!-- Polling Controls -->
        <v-menu>
          <template v-slot:activator="{ props }">
            <v-btn
              variant="outlined"
              color="primary"
              class="mr-2 text-none"
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
          class="mr-2"
          @click="togglePolling"
          :aria-label="polling ? 'Pause Auto-Refresh' : 'Resume Auto-Refresh'"
        >
           <v-icon>{{ polling ? 'mdi-pause' : 'mdi-play' }}</v-icon>
           <v-tooltip activator="parent" location="bottom">
             {{ polling ? 'Pause Auto-Refresh' : 'Resume Auto-Refresh' }}
           </v-tooltip>
        </v-btn>

        <v-btn
          icon="mdi-refresh"
          color="primary"
          variant="flat"
          size="small"
          @click="refresh()"
          :loading="loading"
          aria-label="Refresh Now"
        >
          <v-icon>mdi-refresh</v-icon>
          <v-tooltip activator="parent" location="bottom">Refresh Now</v-tooltip>
        </v-btn>
      </div>
    </div>

    <!-- KPI Cards Grid -->
    <div class="dashboard-grid mb-8">
      <!-- Containers KPI -->
      <v-card class="kpi-card container-kpi" elevation="2">
        <div class="kpi-icon-wrapper">
           <span class="kpi-emoji">🐳</span>
        </div>
        <div class="kpi-content">
          <div class="text-overline font-weight-bold text-medium-emphasis mb-0">Containers</div>
          <div class="text-h3 font-weight-bold text-primary mb-1">{{ overview.containers.total }}</div>
          <div class="d-flex align-center gap-2">
            <v-chip size="x-small" color="success" variant="flat" class="font-weight-bold">
              {{ overview.containers.running }} Running
            </v-chip>
            <v-chip size="x-small" color="medium-emphasis" variant="tonal">
              {{ overview.containers.stopped }} Stopped
            </v-chip>
          </div>
        </div>
      </v-card>

      <!-- Images KPI -->
      <v-card class="kpi-card image-kpi" elevation="2">
        <div class="kpi-icon-wrapper">
           <span class="kpi-emoji">📦</span>
        </div>
        <div class="kpi-content">
          <div class="text-overline font-weight-bold text-medium-emphasis mb-0">Images</div>
          <div class="text-h3 font-weight-bold text-info mb-1">{{ overview.images.total }}</div>
          <div class="text-caption text-medium-emphasis">
            Total Size: <span class="font-weight-bold text-white">{{ formatBytes(overview.images.total_size) }}</span>
          </div>
        </div>
      </v-card>

      <!-- Volumes KPI -->
      <v-card class="kpi-card volume-kpi" elevation="2">
        <div class="kpi-icon-wrapper">
           <span class="kpi-emoji">💾</span>
        </div>
        <div class="kpi-content">
          <div class="text-overline font-weight-bold text-medium-emphasis mb-0">Volumes</div>
          <div class="text-h3 font-weight-bold text-warning mb-1">{{ overview.volumes.total }}</div>
          <div class="text-caption text-medium-emphasis">
             <span class="text-warning font-weight-bold">{{ overview.volumes.unused }}</span> Unused
          </div>
        </div>
      </v-card>

      <!-- Networks KPI -->
      <v-card class="kpi-card network-kpi" elevation="2">
        <div class="kpi-icon-wrapper">
           <span class="kpi-emoji">🌐</span>
        </div>
        <div class="kpi-content">
          <div class="text-overline font-weight-bold text-medium-emphasis mb-0">Networks</div>
          <div class="text-h3 font-weight-bold text-secondary mb-1">{{ overview.networks.total }}</div>
           <div class="text-caption text-medium-emphasis">
             {{ overview.networks.custom }} Custom
          </div>
        </div>
      </v-card>
    </div>

    <!-- Active Containers Section -->
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5 font-weight-bold">Active Containers</h2>
      <v-chip color="primary" size="small" class="ml-3 font-weight-bold" variant="tonal">
        {{ apps.length }}
      </v-chip>
    </div>

    <!-- Empty State -->
    <v-fade-transition>
      <div v-if="!loading && apps.length === 0" class="empty-state-wrapper text-center pa-8 border-dashed rounded-lg">
        <v-icon size="64" color="medium-emphasis" class="mb-4">mdi-docker</v-icon>
        <h3 class="text-h5 font-weight-medium mb-2">No Containers Running</h3>
        <p class="text-body-1 text-medium-emphasis mb-6">
          Your dashboard looks a bit empty. Start a container to see stats here.
        </p>
        <div class="d-flex justify-center gap-4">
          <v-btn color="primary" to="/templates" prepend-icon="mdi-store">
            Deploy from Templates
          </v-btn>
          <v-btn variant="outlined" to="/apps" prepend-icon="mdi-plus">
            Launch New App
          </v-btn>
        </div>
      </div>
    </v-fade-transition>

    <!-- Container Grid -->
    <div v-if="apps.length > 0" class="container-grid">
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
        this.overview = response.data;
      } catch (e) {
        console.error("Failed to fetch dashboard stats", e);
      }
    },
    startStatsPolling() {
      if (this.statsInterval) clearInterval(this.statsInterval);
      if (this.pollingInterval === 0) return;

      this.pollAll(); // Initial

      this.statsInterval = setInterval(() => {
        if (this.polling) {
          this.pollAll();
        }
      }, this.pollingInterval);
    },
    async pollAll() {
      try {
        // Fetch dashboard stats and container stats concurrently
        const [_, statsResponse] = await Promise.all([
          this.fetchOverviewStats(),
          axios.get("/containers/stats", {
            skipAuthRefresh: true
          })
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
            } else {
                if(app.State.Status !== 'running') {
                    this.stats[app.name] = null;
                }
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
       if(!arr) return [];
      return [...arr].sort((a, b) => a.name.localeCompare(b.name));
    },
    handleAppClick(appName) {
      this.$router.push({ path: `/apps/${appName}/info` });
    },
    handleLogs(appName) {
      // Assuming logs route
       this.$router.push({ path: `/apps/${appName}/logs` });
    },
    async handleContainerAction(action, appName) {
        try {
            this.loading = true;
            await axios.get(`/containers/${appName}/${action}`);
            // Wait a bit for state to change then refresh
            setTimeout(() => {
                this.refresh();
            }, 1000);
            this.$store.commit('snackbar/setSnack', { message: `Container ${action}ed successfully.`, color: 'success' }, { root: true });
        } catch(err) {
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
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.5rem;
}

.container-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.kpi-card {
  padding: 1.25rem;
  border-radius: 16px;
  display: flex;
  align-items: flex-start;
  min-height: 140px;
  background: linear-gradient(135deg, rgba(30, 30, 46, 0.9) 0%, rgba(20, 20, 35, 0.95) 100%);
  border: 1px solid rgba(255, 255, 255, 0.05);
  position: relative;
  overflow: hidden;
}

.kpi-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(to bottom right, rgba(255,255,255,0.05), transparent);
  pointer-events: none;
}

.kpi-icon-wrapper {
  margin-right: 1rem;
  padding: 10px;
  background: rgba(0,0,0,0.2);
  border-radius: 12px;
}

.kpi-emoji {
  font-size: 2rem;
}

.kpi-content {
  flex: 1;
  z-index: 1;
}

.gap-2 { gap: 0.5rem; }
.gap-4 { gap: 1rem; }
.cursor-pointer { cursor: pointer; }
.border-dashed { border: 1px dashed rgba(255,255,255,0.15); }
</style>

<template>
  <v-container fluid class="pa-6">
    <!-- Header Section -->
    <div class="d-flex align-center justify-space-between mb-6">
      <h1 class="text-h4 font-weight-bold">Dashboard</h1>

      <div class="d-flex align-center">
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
          class="mr-2"
          @click="togglePolling"
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
          @click="refresh()"
          :loading="loading"
        >
          <v-icon>mdi-refresh</v-icon>
          <v-tooltip activator="parent" location="bottom">Refresh Now</v-tooltip>
        </v-btn>
      </div>
    </div>

    <!-- Overview Stats Cards -->
     <!--
    <v-alert type="info" variant="tonal" class="mb-6 border-dashed">
      Visualization widgets coming soon.
    </v-alert>
    -->

    <div class="dashboard-grid mb-8">
      <v-card class="stat-card" elevation="2">
        <v-card-text>
          <div class="text-overline mb-1 text-medium-emphasis">Containers</div>
          <div class="text-h4 font-weight-bold text-primary">{{ overview.containers.total }}</div>
          <div class="d-flex mt-2">
            <v-chip size="x-small" color="success" class="mr-1">{{ overview.containers.running }} Running</v-chip>
            <v-chip size="x-small" color="error">{{ overview.containers.stopped }} Stopped</v-chip>
          </div>
        </v-card-text>
      </v-card>

      <v-card class="stat-card" elevation="2">
        <v-card-text>
          <div class="text-overline mb-1 text-medium-emphasis">Images</div>
          <div class="text-h4 font-weight-bold text-info">{{ overview.images.total }}</div>
          <div class="text-caption text-medium-emphasis mt-1">
            {{ formatBytes(overview.images.total_size) }} Total Size
          </div>
        </v-card-text>
      </v-card>

      <v-card class="stat-card" elevation="2">
        <v-card-text>
          <div class="text-overline mb-1 text-medium-emphasis">Volumes</div>
          <div class="text-h4 font-weight-bold text-warning">{{ overview.volumes.total }}</div>
          <div class="text-caption text-medium-emphasis mt-1">
             {{ overview.volumes.unused }} Unused
          </div>
        </v-card-text>
      </v-card>

      <v-card class="stat-card" elevation="2">
         <v-card-text>
          <div class="text-overline mb-1 text-medium-emphasis">Networks</div>
          <div class="text-h4 font-weight-bold text-secondary">{{ overview.networks.total }}</div>
           <div class="text-caption text-medium-emphasis mt-1">
             {{ overview.networks.custom }} Custom
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- Containers Section -->
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5 font-weight-bold">Active Containers</h2>
      <v-chip color="primary" size="small" class="ml-3">{{ apps.length }}</v-chip>
    </div>

    <div class="container-grid">
      <v-card
        v-for="app in sortByTitle(apps)"
        :key="app.name"
        class="container-card d-flex flex-column"
        elevation="2"
        @click="handleAppClick(app.name)"
        link
      >
        <v-card-title class="d-flex justify-space-between align-start pt-4 px-4 pb-0">
          <div class="text-truncate pr-2 font-weight-bold text-body-1" :title="app.name">
            {{ app.name }}
          </div>
          <v-chip
            :color="getStatusColor(app.State.Status)"
            size="small"
            variant="flat"
            class="font-weight-bold text-uppercase"
            style="height: 20px; font-size: 0.7rem;"
          >
            {{ app.State.Status }}
          </v-chip>
        </v-card-title>

        <v-card-text class="pt-4 flex-grow-1">
          <!-- Stats Present -->
          <div v-if="stats[app.name]">
            <!-- CPU -->
            <div class="d-flex justify-space-between text-caption mb-1">
              <span class="text-medium-emphasis font-weight-medium">CPU</span>
              <span :class="`text-${getUsageColor(stats[app.name].cpu_percent)}`">{{ stats[app.name].cpu_percent }}%</span>
            </div>
            <v-progress-linear
              :model-value="stats[app.name].cpu_percent"
              :color="getUsageColor(stats[app.name].cpu_percent)"
              height="6"
              rounded
              class="mb-3"
            ></v-progress-linear>

            <!-- MEM -->
            <div class="d-flex justify-space-between text-caption mb-1">
              <span class="text-medium-emphasis font-weight-medium">RAM</span>
              <span :class="`text-${getUsageColor(stats[app.name].mem_percent)}`">{{ stats[app.name].mem_percent }}%</span>
            </div>
            <v-progress-linear
              :model-value="stats[app.name].mem_percent"
              :color="getUsageColor(stats[app.name].mem_percent)"
              height="6"
              rounded
            ></v-progress-linear>

            <div class="d-flex justify-end mt-1">
              <span class="text-caption text-disabled" style="font-size: 0.7rem !important;">
                {{ stats[app.name].mem_current }} / {{ stats[app.name].mem_total }}
              </span>
            </div>
          </div>

          <!-- Stats Loading/Missing -->
          <div v-else-if="app.State.Status === 'running'" class="d-flex align-center justify-center fill-height" style="min-height: 80px;">
            <v-progress-circular indeterminate color="primary" size="24"></v-progress-circular>
            <span class="ml-3 text-caption text-medium-emphasis">Fetching stats...</span>
          </div>

          <!-- Stopped -->
          <div v-else class="d-flex align-center justify-center fill-height" style="min-height: 80px;">
            <v-icon color="disabled" size="large" class="mb-1">mdi-stop-circle-outline</v-icon>
            <span class="text-caption text-disabled ml-2">Container Offline</span>
          </div>
        </v-card-text>

        <!-- Optional Actions Footer could go here -->
      </v-card>
    </div>
  </v-container>
</template>

<script>
import { mapActions, mapState } from "vuex";
import axios from "axios";

export default {
  data() {
    return {
      stats: {},
      statsInterval: null,
      polling: true,
      pollingInterval: 5000, // Default to 5s as requested
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
      // Don't show loading spinner on background polls
      // this.loading = true;
      await this.fetchOverviewStats();
      try {
        const response = await axios.get("/containers/stats", {
          skipAuthRefresh: true
        });
        const statsData = response.data;

        if (this.apps) {
          this.apps.forEach(app => {
            const stat = statsData[app.name];
            if (stat) {
               // Calculate values properly, checking for bytes or MB
               // Fallback logic for memory_usage if raw bytes missing but MB present
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
                // If stopped or no stats yet
                if(app.State.Status !== 'running') {
                    this.stats[app.name] = null;
                }
            }
          });
        }
      } catch (error) {
        console.error("Failed to fetch global stats", error);
      } finally {
        // this.loading = false;
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
    getStatusColor(status) {
        switch(status.toLowerCase()) {
            case 'running': return 'success';
            case 'stopped': return 'grey-darken-1';
            case 'exited': return 'error';
            case 'restarting': return 'warning';
            default: return 'grey';
        }
    },
    getUsageColor(percent) {
        if (percent < 50) return 'success';
        if (percent < 80) return 'warning';
        return 'error';
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
        await this.readApps();
        await this.fetchOverviewStats();
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
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.container-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
}

.stat-card {
  transition: transform 0.2s, box-shadow 0.2s;
  border-radius: 12px;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important;
}

.container-card {
  transition: all 0.2s ease-in-out;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
}

.container-card:hover {
  transform: scale(1.02);
  box-shadow: 0 8px 25px rgba(0,0,0,0.2) !important;
  z-index: 2;
  border-color: rgba(var(--v-theme-primary), 0.3);
}
</style>

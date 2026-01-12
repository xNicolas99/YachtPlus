<template>
  <v-card color="foreground">
    <v-card-title class="primary font-weight-bold">
      Dashboard
      <v-spacer></v-spacer>
      <!-- Polling Interval Dropdown -->
      <v-menu offset-y>
        <template v-slot:activator="{ props }">
          <v-btn text v-bind="props" class="mr-2">
            <v-icon start>mdi-refresh</v-icon>
            {{ pollingIntervalText }}
            <v-icon end>mdi-chevron-down</v-icon>
          </v-btn>
        </template>
        <v-list>
          <v-list-item
            v-for="interval in pollingOptions"
            :key="interval.value"
            @click="setPollingInterval(interval.value)"
          >
            <v-list-item-title>{{ interval.text }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <v-tooltip bottom>
        <template v-slot:activator="{ props }">
          <v-btn
            icon
            @click="togglePolling"
            v-bind="props"
            class="mr-2"
          >
            <v-icon>{{ polling ? "mdi-pause" : "mdi-play" }}</v-icon>
          </v-btn>
        </template>
        <span>{{ polling ? "Pause Stats" : "Resume Stats" }}</span>
      </v-tooltip>
      <v-icon @click="refresh()">mdi-refresh</v-icon>
    </v-card-title>
    <v-card-text class="secondary text-center px-5 py-5">
      <!-- Overview Cards Grid -->
       <v-alert type="info" variant="outlined" class="mb-4">
        Visualization widgets temporarily disabled for migration.
      </v-alert>

      <div class="dashboard-grid">
         <!-- STUBBED STATS CARDS -->
         <v-card v-for="(val, key) in overview" :key="key">
            <v-card-title>{{ key }}</v-card-title>
            <v-card-text>{{ val.total }}</v-card-text>
         </v-card>
      </div>

      <!-- Container Cards Grid -->
      <div class="container-cards mt-5">
        <v-card
          v-for="app in sortByTitle(apps)"
          :key="app.name"
          color="foreground"
          class="flex-grow-1"
          hover
          @click="handleAppClick(app.name)"
        >
          <v-card-title class="pb-0 d-flex justify-space-between">
            <span
              class="AppTitle text-truncate"
              style="max-width: 150px"
              :title="app.name"
              >{{ app.name }}</span
            >
            <v-chip
              size="x-small"
              :color="app.State.Status === 'running' ? 'success' : 'error'"
              >{{ app.State.Status }}</v-chip
            >
          </v-card-title>
          <v-card-text class="text-left pt-2">
            <div v-if="stats[app.name]">
              <div class="d-flex justify-space-between caption">
                <span>CPU</span>
                <span>{{ stats[app.name].cpu_percent }}%</span>
              </div>
              <v-progress-linear
                :model-value="stats[app.name].cpu_percent"
                color="primary"
                height="4"
                rounded
                class="mb-2"
              />

              <div class="d-flex justify-space-between caption">
                <span>MEM</span>
                <span>{{ stats[app.name].mem_percent }}%</span>
              </div>
              <v-progress-linear
                :model-value="stats[app.name].mem_percent"
                color="blue"
                height="4"
                rounded
              />
              <div class="caption grey--text text-right mt-1">
                {{ stats[app.name].mem_current }} /
                {{ stats[app.name].mem_total }}
              </div>
            </div>
            <div v-else-if="app.State.Status === 'running'">
              <div>Loading...</div>
            </div>
            <div v-else class="text-center caption grey--text py-4">
              Container Stopped
            </div>
          </v-card-text>
        </v-card>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { mapActions, mapState } from "vuex";
import axios from "axios";

export default {
  // components: {
  //   StatsCard
  // },
  data() {
    return {
      stats: {},
      statsInterval: null,
      polling: true,
      pollingInterval: 2000,
      pollingOptions: [
        { text: "2s", value: 2000 },
        { text: "5s", value: 5000 },
        { text: "10s", value: 10000 },
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
      if (this.pollingInterval === 0) return; // Off

      // Initial call
      this.pollAll();

      this.statsInterval = setInterval(() => {
        if (this.polling) {
          this.pollAll();
        }
      }, this.pollingInterval);
    },
    async pollAll() {
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
               this.stats[app.name] = {
                 cpu_percent: stat.cpu_percent,
                 mem_percent: stat.memory_percent,
                 mem_current: stat.memory_usage_mb + " MB",
                 mem_total: stat.memory_limit_mb + " MB",
                 name: app.name
               };
            } else {
               this.stats[app.name] = {
                 cpu_percent: 0,
                 mem_percent: 0,
                 mem_current: "0 MB",
                 mem_total: "0 MB",
                 name: app.name,
                 status: "stopped"
               };
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
      await this.readApps();
      await this.pollAll();
    },
    sortByTitle(arr) {
       if(!arr) return [];
      return [...arr].sort((a, b) => a.name.localeCompare(b.name));
    },
    handleAppClick(appName) {
      this.$router.push({ path: `/apps/${appName}/info` });
    }
  },
  computed: {
    ...mapState("apps", ["apps"]),
    pollingIntervalText() {
      if (this.pollingInterval === 0) return "Off";
      return this.pollingInterval / 1000 + "s";
    }
  },
  async created() {
    const stored = localStorage.getItem("dashboard_polling_interval");
    if (stored !== null) {
      this.pollingInterval = parseInt(stored);
    }

    await this.readApps();
    await this.fetchOverviewStats();
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
.AppTitle {
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.container-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}
</style>

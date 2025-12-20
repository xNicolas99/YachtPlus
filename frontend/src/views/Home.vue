<template>
  <v-card color="foreground">
    <v-card-title class="primary font-weight-bold">
      Dashboard
      <v-spacer></v-spacer>
      <!-- Polling Interval Dropdown -->
      <v-menu offset-y>
        <template v-slot:activator="{ on, attrs }">
          <v-btn text v-bind="attrs" v-on="on" class="mr-2">
            <v-icon left>mdi-refresh</v-icon>
            {{ pollingIntervalText }}
            <v-icon right>mdi-chevron-down</v-icon>
          </v-btn>
        </template>
        <v-list>
          <v-list-item v-for="interval in pollingOptions" :key="interval.value" @click="setPollingInterval(interval.value)">
             <v-list-item-title>{{ interval.text }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <v-tooltip bottom>
        <template v-slot:activator="{ on, attrs }">
          <v-btn icon @click="togglePolling" v-bind="attrs" v-on="on" class="mr-2">
            <v-icon>{{ polling ? 'mdi-pause' : 'mdi-play' }}</v-icon>
          </v-btn>
        </template>
        <span>{{ polling ? 'Pause Stats' : 'Resume Stats' }}</span>
      </v-tooltip>
      <v-icon v-on:click="refresh()">mdi-refresh</v-icon>
    </v-card-title>
    <v-card-text class="secondary text-center px-5 py-5">

      <!-- Overview Cards Grid -->
      <div class="dashboard-grid">
         <stats-card
            title="Containers"
            :count="overview.containers.total"
            icon="mdi-cube-outline"
            color="primary"
            to="/apps"
            :items="[
               { label: 'Running', count: overview.containers.running, color: 'success', icon: 'mdi-circle' },
               { label: 'Stopped', count: overview.containers.stopped, color: 'error', icon: 'mdi-pause' },
               { label: 'Unhealthy', count: overview.containers.unhealthy, color: 'warning', icon: 'mdi-alert' }
            ]"
         />
         <stats-card
            title="Projects"
            :count="overview.projects.total"
            icon="mdi-folder-multiple-outline"
            color="info"
            to="/projects"
             :items="[
               { label: 'Active', count: overview.projects.active, color: 'success', icon: 'mdi-circle' },
               { label: 'Inactive', count: overview.projects.inactive, color: 'grey', icon: 'mdi-circle-outline' }
            ]"
         />
         <stats-card
            title="Images"
            :count="overview.images.total"
            icon="mdi-disc"
            color="success"
            to="/resources/images"
             :items="[
               { label: 'Used', count: overview.images.used, color: 'info', icon: 'mdi-check' },
               { label: 'Dangling', count: overview.images.dangling, color: 'warning', icon: 'mdi-delete' }
            ]"
         />
         <stats-card
            title="Volumes"
            :count="overview.volumes.total"
            icon="mdi-database"
            color="warning"
            to="/resources/volumes"
             :items="[
               { label: 'In Use', count: overview.volumes.in_use, color: 'success', icon: 'mdi-check' },
               { label: 'Unused', count: overview.volumes.unused, color: 'grey', icon: 'mdi-delete-outline' }
            ]"
         />
         <stats-card
            title="Networks"
            :count="overview.networks.total"
            icon="mdi-network"
            color="error"
            to="/resources/networks"
             :items="[
               { label: 'Custom', count: overview.networks.custom, color: 'info', icon: 'mdi-creation' },
               { label: 'Default', count: overview.networks.default, color: 'grey', icon: 'mdi-lock' }
            ]"
         />
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
              <span class="AppTitle text-truncate" style="max-width: 150px" :title="app.name">{{ app.name }}</span>
              <v-chip x-small :color="app.State.Status === 'running' ? 'success' : 'error'">{{ app.State.Status }}</v-chip>
            </v-card-title>
            <v-card-text class="text-left pt-2">
                <div v-if="stats[app.name]">
                    <div class="d-flex justify-space-between caption">
                        <span>CPU</span>
                        <span>{{ stats[app.name].cpu_percent }}%</span>
                    </div>
                    <v-progress-linear :value="stats[app.name].cpu_percent" color="primary" height="4" rounded class="mb-2" />

                    <div class="d-flex justify-space-between caption">
                        <span>MEM</span>
                        <span>{{ stats[app.name].mem_percent }}%</span>
                    </div>
                     <v-progress-linear :value="stats[app.name].mem_percent" color="blue" height="4" rounded />
                    <div class="caption grey--text text-right mt-1">{{ stats[app.name].mem_current }} / {{ stats[app.name].mem_total }}</div>
                </div>
                 <div v-else-if="app.State.Status === 'running'">
                    <v-skeleton-loader type="list-item-two-line"></v-skeleton-loader>
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
import StatsCard from "@/components/dashboard/StatsCard";

export default {
  components: {
      StatsCard
  },
  data() {
    return {
      stats: {},
      statsInterval: null,
      polling: true,
      pollingInterval: 5000,
      pollingOptions: [
          { text: '5s', value: 5000 },
          { text: '10s', value: 10000 },
          { text: '30s', value: 30000 },
          { text: '60s', value: 60000 },
          { text: 'Off', value: 0 }
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
            const response = await axios.get('/api/dashboard/stats');
            this.overview = response.data;
        } catch (e) {
            console.error("Failed to fetch dashboard stats", e);
        }
    },
    async fetchContainerStats(containerId) {
        try {
            const response = await axios.get(`/api/containers/${containerId}/stats`, {
                skipAuthRefresh: true // Avoid loop if auth fails during heavy polling
            });
            const data = response.data;

            this.$set(this.stats, containerId, {
                cpu_percent: data.cpu_percent,
                mem_percent: data.memory_percent,
                mem_current: data.memory_usage_mb + " MB",
                mem_total: data.memory_limit_mb + " MB",
                name: containerId
            });

        } catch (error) {
            // Ignore 409 (conflict/stopped) or 401 (handled by interceptor usually, but here skipped)
             if (error.response && error.response.status === 409) {
                 this.$set(this.stats, containerId, {
                    cpu_percent: 0,
                    mem_percent: 0,
                    mem_current: "0 MB",
                    mem_total: "0 MB",
                    name: containerId,
                    status: "stopped"
                });
            }
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
        // Fetch overview
        await this.fetchOverviewStats();

        // Fetch container stats
        if (this.apps) {
            this.apps.forEach(app => {
                if (app.State.Status === 'running') {
                    this.fetchContainerStats(app.name);
                } else {
                     this.$set(this.stats, app.name, {
                        cpu_percent: 0,
                        mem_percent: 0,
                        mem_current: "0 MB",
                        mem_total: "0 MB",
                        name: app.name
                    });
                }
            });
        }
    },
    togglePolling() {
        this.polling = !this.polling;
    },
    setPollingInterval(val) {
        this.pollingInterval = val;
        localStorage.setItem('dashboard_polling_interval', val);
        this.startPolling();
    },
    async refresh() {
      await this.readApps();
      await this.pollAll();
    },
    sortByTitle(arr) {
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
        return (this.pollingInterval / 1000) + "s";
    }
  },
  async created() {
    // Load preference
    const stored = localStorage.getItem('dashboard_polling_interval');
    if (stored !== null) {
        this.pollingInterval = parseInt(stored);
    }

    await this.readApps();
    await this.fetchOverviewStats();
    this.startStatsPolling();
  },
  beforeDestroy() {
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

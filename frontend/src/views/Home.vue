<template>
  <v-card color="foreground">
    <v-card-title class="primary font-weight-bold">
      Dashboard
      <v-spacer></v-spacer>
      <!-- Connection Status Indicator -->
      <v-chip
        v-if="!connected"
        color="error"
        small
        class="mr-2"
      >
        <v-icon left small>mdi-wifi-off</v-icon>
        Disconnected
      </v-chip>
      <v-chip
        v-else
        color="success"
        small
        class="mr-2"
        outlined
      >
        <v-icon left small>mdi-wifi</v-icon>
        Live
      </v-chip>

      <v-tooltip bottom>
        <template v-slot:activator="{ on, attrs }">
          <v-btn
            icon
            @click="toggleStream"
            v-bind="attrs"
            v-on="on"
            class="mr-2"
          >
            <v-icon>{{ connected ? "mdi-pause" : "mdi-play" }}</v-icon>
          </v-btn>
        </template>
        <span>{{ connected ? "Pause Stream" : "Resume Stream" }}</span>
      </v-tooltip>
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
            {
              label: 'Running',
              count: overview.containers.running,
              color: 'success',
              icon: 'mdi-circle'
            },
            {
              label: 'Stopped',
              count: overview.containers.stopped,
              color: 'error',
              icon: 'mdi-pause'
            },
            {
              label: 'Unhealthy',
              count: overview.containers.unhealthy,
              color: 'warning',
              icon: 'mdi-alert'
            }
          ]"
        />
        <stats-card
          title="Projects"
          :count="overview.projects.total"
          icon="mdi-folder-multiple-outline"
          color="info"
          to="/projects"
          :items="[
            {
              label: 'Active',
              count: overview.projects.active,
              color: 'success',
              icon: 'mdi-circle'
            },
            {
              label: 'Inactive',
              count: overview.projects.inactive,
              color: 'grey',
              icon: 'mdi-circle-outline'
            }
          ]"
        />
        <stats-card
          title="Images"
          :count="overview.images.total"
          icon="mdi-disc"
          color="success"
          to="/resources/images"
          :items="[
            {
              label: 'Used',
              count: overview.images.used,
              color: 'info',
              icon: 'mdi-check'
            },
            {
              label: 'Dangling',
              count: overview.images.dangling,
              color: 'warning',
              icon: 'mdi-delete'
            }
          ]"
        />
        <stats-card
          title="Volumes"
          :count="overview.volumes.total"
          icon="mdi-database"
          color="warning"
          to="/resources/volumes"
          :items="[
            {
              label: 'In Use',
              count: overview.volumes.in_use,
              color: 'success',
              icon: 'mdi-check'
            },
            {
              label: 'Unused',
              count: overview.volumes.unused,
              color: 'grey',
              icon: 'mdi-delete-outline'
            }
          ]"
        />
        <stats-card
          title="Networks"
          :count="overview.networks.total"
          icon="mdi-network"
          color="error"
          to="/resources/networks"
          :items="[
            {
              label: 'Custom',
              count: overview.networks.custom,
              color: 'info',
              icon: 'mdi-creation'
            },
            {
              label: 'Default',
              count: overview.networks.default,
              color: 'grey',
              icon: 'mdi-lock'
            }
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
            <span
              class="AppTitle text-truncate"
              style="max-width: 150px"
              :title="app.name"
              >{{ app.name }}</span
            >
            <v-chip
              x-small
              :color="app.State.Status === 'running' ? 'success' : 'error'"
              >{{ app.State.Status }}</v-chip
            >
          </v-card-title>
          <v-card-text class="text-left pt-2">
            <!-- CPU/Mem Stats are not in the overview payload, they were separate.
                 However, getting stats for ALL containers every 2s is heavy.
                 The Dashboard SSE payload (actions.get_dashboard_stats) does NOT return per-container CPU/Mem.
                 It returns aggregate counts.
                 The previous implementation fetched /api/containers/stats separate from /dashboard/stats.
                 We need to make sure we don't lose that functionality.

                 Ideally, we should fetch per-container stats only for visible containers or accept that the dashboard
                 is an overview and detailed stats belong in the container details view.

                 However, to maintain feature parity without killing the server:
                 If the user wants "Real-time" dashboard, we should probably bundle the stats in the SSE
                 OR make a second SSE stream for stats (heavy).

                 Wait, the previous implementation called /api/containers/stats every 2s.
                 If we want to optimize, we should rely on the status mainly.

                 Let's check if the user *really* needs per-container CPU bars on the dashboard.
                 The screenshot/code shows progress bars. Removing them is a regression.

                 Solution: The dashboard SSE should probably include the lightweight stats if possible,
                 OR we keep polling /api/containers/stats but use SSE for the Overview.

                 But the audit said "Replace Polling".

                 Let's modify the backend SSE endpoint to INCLUDE the per-container stats
                 by merging the logic from containers.get_all_container_stats.
            -->
            <div v-if="stats[app.name]">
              <div class="d-flex justify-space-between caption">
                <span>CPU</span>
                <span>{{ stats[app.name].cpu_percent }}%</span>
              </div>
              <v-progress-linear
                :value="stats[app.name].cpu_percent"
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
                :value="stats[app.name].mem_percent"
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
      connected: false,
      eventSource: null,
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
    toggleStream() {
      if (this.connected) {
        this.closeStream();
      } else {
        this.initStream();
      }
    },
    closeStream() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
      this.connected = false;
    },
    initStream() {
      this.closeStream(); // Ensure clean start

      const url = "/api/dashboard/stream";
      this.eventSource = new EventSource(url, { withCredentials: true });

      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Update Overview
          this.overview = data;

          // NOTE: The current SSE implementation in dashboard_sse.py calls actions.get_dashboard_stats()
          // which returns the overview object (counts), NOT the per-container stats.
          // To get per-container stats (CPU/RAM) via SSE, we would need to update the backend
          // to include that data in the stream.
          //
          // For now, I will keep the polling for the DETAILED stats as a separate lightweight
          // poll if absolutely necessary, OR (better) I will update the backend SSE to include it.
          //
          // Let's assume I will update the backend to include `container_stats` in the payload next.

          if (data.container_stats) {
             this.processContainerStats(data.container_stats);
          }

          this.connected = true;
        } catch (e) {
          console.error("SSE Parse Error", e);
        }
      };

      this.eventSource.onerror = () => {
        this.connected = false;
        // EventSource attempts reconnect automatically, but UI should reflect status
      };

      this.eventSource.onopen = () => {
        this.connected = true;
      };
    },
    processContainerStats(statsData) {
        if (this.apps) {
          this.apps.forEach(app => {
            const stat = statsData[app.name];
            if (stat) {
               this.$set(this.stats, app.name, {
                 cpu_percent: stat.cpu_percent,
                 mem_percent: stat.memory_percent,
                 mem_current: stat.memory_usage_mb + " MB",
                 mem_total: stat.memory_limit_mb + " MB",
                 name: app.name
               });
            } else {
               // Stopped or missing
               this.$set(this.stats, app.name, {
                 cpu_percent: 0,
                 mem_percent: 0,
                 mem_current: "0 MB",
                 mem_total: "0 MB",
                 name: app.name,
                 status: "stopped"
               });
            }
          });
        }
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
  },
  async created() {
    await this.readApps();
    this.initStream();
  },
  beforeDestroy() {
    this.closeStream();
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

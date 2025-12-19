<template>
  <v-card color="foreground">
    <v-card-title class="primary font-weight-bold">
      Dashboard
      <v-spacer></v-spacer>
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
      <v-row dense class="mt-3">
        <v-col
          v-for="app in sortByTitle(apps)"
          :key="app.name"
          cols="12"
          xl="2"
          lg="2"
          md="3"
          sm="3"
          class="d-flex"
          style="flex-direction: column"
        >
          <v-card color="foreground" class="flex-grow-1">
            <v-card-title class="pb-0">
              <v-tooltip top transition="scale-transition">
                <template v-slot:activator="{ on, attrs }">
                  <span
                    v-bind="attrs"
                    v-on="on"
                    @click="handleAppClick(app.name)"
                    class="AppTitle"
                    >{{ app.name }}</span
                  >
                </template>
                <span>{{ app.name }}</span>
              </v-tooltip>
            </v-card-title>
            <v-tooltip bottom transition="scale-transition">
              <template v-slot:activator="{ on, attrs }">
                <v-card-text
                  v-bind="attrs"
                  v-on="on"
                  class="text-left pt-0 AppTitle"
                >
                  <div v-if="stats[app.name]">
                    CPU Usage:
                    <v-progress-linear :value="stats[app.name].cpu_percent" color="primary" />
                    {{ stats[app.name].cpu_percent }}%
                    <br />
                    MEM Usage:
                    <v-progress-linear :value="stats[app.name].mem_percent" color="blue" />
                    {{ stats[app.name].mem_percent }}%, {{ stats[app.name].mem_current }} /
                    {{ stats[app.name].mem_total }}
                  </div>
                  <div v-else>
                    <v-skeleton-loader type="list-item-two-line"></v-skeleton-loader>
                  </div>
                </v-card-text>
              </template>
              <span v-if="stats[app.name]"
                >CPU Usage: {{ stats[app.name].cpu_percent }}%
                <br />
                MEM Usage: {{ stats[app.name].mem_percent }}%, {{ stats[app.name].mem_current }}/{{
                  stats[app.name].mem_total
                }}
              </span>
              <span v-else>Loading stats...</span>
            </v-tooltip>
          </v-card>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
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
    };
  },
  methods: {
    ...mapActions({
      readApps: "apps/readApps"
    }),
    formatBytes(bytes, decimals = 2) {
      if (bytes === 0) return "0 Bytes";

      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];

      const i = Math.floor(Math.log(bytes) / Math.log(k));

      return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    },
    async fetchContainerStats(containerId) {
        try {
            const response = await axios.get(`/api/containers/${containerId}/stats`);
            const data = response.data;

            this.$set(this.stats, containerId, {
                cpu_percent: data.cpu_percent,
                mem_percent: data.memory_percent,
                mem_current: data.memory_usage_mb + " MB",
                mem_total: data.memory_limit_mb + " MB",
                name: containerId
            });

        } catch (error) {
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
      this.pollAll();
      this.statsInterval = setInterval(() => {
        this.pollAll();
      }, 5000);
    },
    pollAll() {
        if (this.apps && this.polling) {
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
    async refresh() {
      await this.readApps();
      this.pollAll();
    },
    sortByTitle(arr) {
      return [...arr].sort((a, b) => a.name.localeCompare(b.name));
    },
    handleAppClick(appName) {
      this.$router.push({ path: `/apps/${appName}/info` });
    }
  },
  computed: {
    ...mapState("apps", ["apps"])
  },
  async created() {
    await this.readApps();
    this.startStatsPolling();
  },
  beforeDestroy() {
    if (this.statsInterval) {
        clearInterval(this.statsInterval);
    }
  }
};
</script>

<style>
.AppTitle {
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}
</style>

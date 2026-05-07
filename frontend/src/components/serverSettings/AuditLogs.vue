<template>
  <div>
    <v-card color="foreground">
      <v-card-title class="primary font-weight-bold white--text">
        Audit Logs
      </v-card-title>
      <v-card-text>
        <v-data-table
          :headers="headers"
          :items="logs"
          :loading="loading"
          class="elevation-1"
          sort-by="timestamp"
          sort-desc
        >
          <template v-slot:item.timestamp="{ item }">
            {{ formatDate(item.timestamp) }}
          </template>
          <template v-slot:item.action="{ item }">
            <v-chip :color="getActionColor(item.action)" dark x-small>
              {{ item.action }}
            </v-chip>
          </template>
        </v-data-table>
      </v-card-text>
      <v-card-actions>
         <v-btn icon :loading="loading" :disabled="loading" @click="fetchLogs" aria-label="Refresh audit logs" title="Refresh audit logs"><v-icon>mdi-refresh</v-icon></v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script>
import axios from "axios";
import { format, parseISO } from "date-fns";

export default {
  data() {
    return {
      loading: false,
      logs: [],
      headers: [
        { title: "Timestamp", key: "timestamp", sortable: true },
        { title: "User", key: "user", sortable: true },
        { title: "Action", key: "action", sortable: true },
        { title: "Resource", key: "resource", sortable: true },
        { title: "Details", key: "details", sortable: false }
      ]
    };
  },
  mounted() {
    this.fetchLogs();
  },
  methods: {
    fetchLogs() {
      this.loading = true;
      axios
        .get("/audit/")
        .then(response => {
          this.logs = response.data;
        })
        .catch(error => {
          console.error(error);
          if (this.$notify) {
              this.$notify({
                  title: "Error",
                  text: "Failed to load audit logs",
                  type: "error"
              });
          }
        })
        .finally(() => {
          this.loading = false;
        });
    },
    formatDate(date) {
      try {
        const d = typeof date === 'string' ? parseISO(date) : date;
        return format(d, "yyyy-MM-dd HH:mm:ss");
      } catch (e) {
        return date;
      }
    },
    getActionColor(action) {
      if (action.includes("delete") || action.includes("remove") || action.includes("kill")) return "error";
      if (action.includes("stop")) return "warning";
      if (action.includes("start") || action.includes("deploy")) return "success";
      return "primary";
    }
  }
};
</script>

<style scoped>
</style>

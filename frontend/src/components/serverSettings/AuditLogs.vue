<template>
  <section class="yp-page">
    <PageHeader title="Activity log" :heading-level="2" subtitle="Search who changed what, and when.">
      <template #actions>
        <v-btn prepend-icon="mdi-download" variant="outlined" :loading="exporting" :disabled="loading || exporting || !total" @click="exportLogs">Export CSV</v-btn>
        <v-btn prepend-icon="mdi-refresh" :loading="loading" :disabled="loading" @click="fetchLogs">Refresh</v-btn>
      </template>
    </PageHeader>
    <v-card class="yp-panel mb-4">
      <v-card-text>
        <v-form @submit.prevent="applyFilters">
          <v-row dense>
            <v-col cols="12" sm="6" lg="4"><v-text-field v-model="filters.user" label="User (exact)" maxlength="264" clearable hide-details /></v-col>
            <v-col cols="12" sm="6" lg="4"><v-text-field v-model="filters.action" label="Action (exact)" maxlength="264" clearable hide-details /></v-col>
            <v-col cols="12" sm="6" lg="4"><v-text-field v-model="filters.resource" label="Resource contains" maxlength="255" clearable hide-details /></v-col>
            <v-col cols="12" sm="6" lg="4"><v-text-field v-model="filters.since" type="datetime-local" label="From (local time)" hide-details /></v-col>
            <v-col cols="12" sm="6" lg="4"><v-text-field v-model="filters.until" type="datetime-local" label="Until (local time)" hide-details /></v-col>
            <v-col cols="12" sm="6" lg="4" class="d-flex align-center ga-2 flex-wrap">
              <v-btn type="submit" color="primary" :disabled="loading">Apply filters</v-btn>
              <v-btn variant="text" :disabled="loading" @click="clearFilters">Clear</v-btn>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
    </v-card>
    <v-alert v-if="loadError" type="error" variant="tonal" class="mb-4" role="alert">
      {{ loadError }}<span v-if="logs.length"> Displayed rows are from the last successful request.</span>
      <template #append><v-btn variant="text" :disabled="loading" @click="fetchLogs">Retry</v-btn></template>
    </v-alert>
    <v-alert v-if="total > 5000" type="info" variant="tonal" class="mb-4">CSV exports include the newest 5,000 entries matching the applied filters. Narrow the time range for a complete export.</v-alert>
    <v-card class="yp-panel">
      <v-data-table-server :headers="headers" :items="logs" :items-length="total" :loading="loading"
        :page="page" :items-per-page="pageSize" :items-per-page-options="[25, 50, 100, 200]"
        item-value="id" @update:options="changePage">
        <template #item.timestamp="{ item }">{{ formatDate(item.timestamp) }}</template>
        <template #item.action="{ item }"><v-chip :color="getActionColor(item.action)" size="small" variant="tonal">{{ item.action }}</v-chip></template>
        <template #item.details="{ item }"><span class="audit-details">{{ item.details || '—' }}</span></template>
        <template #no-data>No activity matches the applied filters.</template>
      </v-data-table-server>
    </v-card>
  </section>
</template>

<script>
import axios from "axios";
import PageHeader from "@/components/PageHeader.vue";

const emptyFilters = () => ({ user: "", action: "", resource: "", since: "", until: "" });
export function auditParams(filters) {
  const params = {};
  for (const name of ["user", "action", "resource"]) {
    const value = (filters[name] || "").trim();
    if (value) params[name] = value;
  }
  for (const name of ["since", "until"]) {
    if (!filters[name]) continue;
    const date = new Date(filters[name]);
    if (!Number.isFinite(date.getTime())) throw new Error("Enter a valid date and time.");
    params[name] = date.toISOString();
  }
  if (params.since && params.until && params.since > params.until) throw new Error("From must precede Until.");
  return params;
}

export default {
  components: { PageHeader },
  data: () => ({
    filters: emptyFilters(), appliedFilters: {}, logs: [], total: 0, page: 1, pageSize: 50,
    loading: false, exporting: false, loadError: "", requestGeneration: 0,
    headers: [
      { title: "Time", key: "timestamp", sortable: false },
      { title: "User", key: "user", sortable: false },
      { title: "Action", key: "action", sortable: false },
      { title: "Resource", key: "resource", sortable: false },
      { title: "Details", key: "details", sortable: false },
    ],
  }),
  mounted() { this.fetchLogs(); },
  beforeUnmount() { this.requestGeneration++; this._auditController?.abort(); },
  methods: {
    applyFilters() {
      try { this.appliedFilters = auditParams(this.filters); }
      catch (error) { this.loadError = error.message; return; }
      this.page = 1;
      return this.fetchLogs();
    },
    clearFilters() { this.filters = emptyFilters(); return this.applyFilters(); },
    changePage({ page, itemsPerPage }) {
      if (page === this.page && itemsPerPage === this.pageSize) return;
      this.page = itemsPerPage !== this.pageSize ? 1 : page;
      this.pageSize = itemsPerPage;
      return this.fetchLogs();
    },
    async fetchLogs() {
      const generation = ++this.requestGeneration;
      this._auditController?.abort();
      this._auditController = new AbortController();
      this.loading = true;
      this.loadError = "";
      try {
        const response = await axios.get("/audit/entries", {
          params: { ...this.appliedFilters, limit: this.pageSize, offset: (this.page - 1) * this.pageSize },
          signal: this._auditController.signal,
        });
        if (generation !== this.requestGeneration) return;
        if (!Array.isArray(response.data?.items) || !Number.isInteger(response.data?.total)) throw new Error("Invalid audit response");
        this.logs = response.data.items;
        this.total = response.data.total;
      } catch (error) {
        if (generation !== this.requestGeneration || error.code === "ERR_CANCELED") return;
        this.loadError = "Activity could not be loaded. Check the connection and your permissions, then retry.";
      } finally {
        if (generation === this.requestGeneration) this.loading = false;
      }
    },
    async exportLogs() {
      if (this.exporting) return;
      this.exporting = true;
      let url;
      let anchor;
      try {
        const response = await axios.get("/audit/export", { params: this.appliedFilters, responseType: "blob" });
        url = URL.createObjectURL(response.data);
        anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "yachtplus-audit.csv";
        document.body.appendChild(anchor);
        anchor.click();
      } catch (error) {
        this.loadError = "CSV export failed. Check your connection and permissions, then retry.";
      } finally {
        anchor?.remove();
        if (url) URL.revokeObjectURL(url);
        this.exporting = false;
      }
    },
    formatDate(value) {
      const date = new Date(typeof value === "string" && !/(Z|[+-]\d\d:\d\d)$/.test(value) ? value + "Z" : value);
      return Number.isFinite(date.getTime()) ? date.toLocaleString() : value;
    },
    getActionColor(action = "") {
      if (/delete|remove|kill/.test(action)) return "error";
      if (/stop|fail/.test(action)) return "warning";
      if (/start|deploy|complete/.test(action)) return "success";
      return "primary";
    },
  },
};
</script>

<style scoped>
.audit-details { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>

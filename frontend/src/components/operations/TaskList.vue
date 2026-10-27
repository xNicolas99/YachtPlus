<template>
  <div class="yp-page tasks-page">
    <PageHeader title="Tasks" subtitle="Follow deployments, image pulls, updates and backups across page changes.">
      <template #actions>
        <v-btn prepend-icon="mdi-refresh" :loading="loading" @click="load">Refresh</v-btn>
      </template>
    </PageHeader>
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" role="alert">
      {{ error }} <v-btn variant="text" @click="load">Retry</v-btn>
    </v-alert>
    <v-card>
      <v-card-text>
        <div class="tasks-toolbar">
          <v-select v-model="status" label="Status" :items="statuses" clearable hide-details density="compact" />
          <span class="text-body-2 text-medium-emphasis" role="status">
            {{ lastUpdated ? `Updated ${formatDate(lastUpdated)}` : 'Loading tasks…' }}
          </span>
        </div>
      </v-card-text>
      <v-data-table-server :headers="headers" :items="items" :items-length="total" :loading="loading"
        :items-per-page="25" :page="page" :items-per-page-options="[25]" item-value="id"
        @update:page="page = $event">
        <template #item.kind="{ item }">{{ kindLabel(item) }}</template>
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="tonal">{{ item.status }}</v-chip>
        </template>
        <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
        <template #item.phase="{ item }">
          <v-progress-linear v-if="item.status === 'running'" indeterminate height="2" class="mb-1" aria-label="Task is running" />
          {{ item.phase }}
        </template>
        <template #item.actions="{ item }">
          <v-btn variant="text" size="small" @click="open(item)">Details</v-btn>
        </template>
        <template #no-data>
          <div class="pa-6">{{ error ? 'Tasks could not be loaded.' : 'No tasks match this view.' }}</div>
        </template>
      </v-data-table-server>
    </v-card>
    <v-dialog v-model="detailsOpen" max-width="680" @update:model-value="value => { if (!value) closeDetails(); }">
      <v-card>
        <v-card-title class="d-flex align-center">Task details<v-spacer /><v-btn icon="mdi-close" variant="text" aria-label="Close task details" @click="closeDetails" /></v-card-title>
        <v-card-text v-if="detailLoading"><v-progress-linear indeterminate aria-label="Loading task details" /></v-card-text>
        <v-card-text v-else-if="detailError"><v-alert type="error" variant="tonal">{{ detailError }}</v-alert></v-card-text>
        <v-card-text v-else-if="selected">
          <dl class="task-details">
            <dt>Operation</dt><dd>{{ kindLabel(selected) }}</dd>
            <dt>Resource</dt><dd>{{ selected.resource }}</dd>
            <dt>Started by</dt><dd>{{ selected.actor }}</dd>
            <dt>Status</dt><dd>{{ selected.status }}</dd>
            <dt>Current step</dt><dd>{{ selected.phase }}</dd>
            <dt>Created</dt><dd>{{ formatDate(selected.created_at) }}</dd>
            <dt>Started</dt><dd>{{ formatDate(selected.started_at) }}</dd>
            <dt>Finished</dt><dd>{{ formatDate(selected.finished_at) }}</dd>
          </dl>
          <v-alert v-if="selected.error" type="error" variant="tonal" class="mt-4">{{ selected.error }}</v-alert>
          <v-alert v-if="selected.retryable" type="warning" variant="tonal" class="mt-4">
            Check the resource's current state before retrying. An interrupted task may have applied part of its changes.
          </v-alert>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="closeDetails">Close</v-btn>
          <v-btn v-if="selected?.retryable && !detailLoading" color="primary" :loading="retrying" :disabled="retrying" @click="retry">Retry task</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from "axios";
import PageHeader from "@/components/PageHeader.vue";

export default {
  components: { PageHeader },
  data() {
    return {
      items: [], total: 0, status: null, page: 1, loading: false, error: "", lastUpdated: null,
      selected: null, detailsOpen: false, retrying: false, timer: null, generation: 0, disposed: false,
      detailLoading: false, detailError: "", detailGeneration: 0,
      statuses: ["queued", "running", "succeeded", "failed", "interrupted"],
      headers: [
        { title: "Operation", key: "kind", sortable: false }, { title: "Resource", key: "resource", sortable: false },
        { title: "Status", key: "status", sortable: false }, { title: "Step", key: "phase", sortable: false },
        { title: "Started by", key: "actor", sortable: false }, { title: "Created", key: "created_at", sortable: false },
        { title: "Actions", key: "actions", sortable: false },
      ],
    };
  },
  watch: {
    status() { if (this.page !== 1) this.page = 1; else this.load(); },
    page() { this.load(); },
    "$route.query.operation": {
      immediate: true,
      handler(id) { if (typeof id === "string" && id && (this.selected?.id !== id || !this.detailsOpen)) return this.openRequested(id); },
    },
  },
  mounted() {
    this.load();
    this.timer = setInterval(() => { if (!document.hidden && !this.loading) this.load(); }, 5000);
    document.addEventListener("visibilitychange", this.onVisibility);
  },
  beforeUnmount() {
    this.disposed = true;
    this.generation++;
    this.detailGeneration++;
    clearInterval(this.timer);
    document.removeEventListener("visibilitychange", this.onVisibility);
  },
  methods: {
    onVisibility() { if (!document.hidden) this.load(); },
    async load() {
      const generation = ++this.generation;
      this.loading = true;
      try {
        const response = await axios.get("/operations", {
          params: { limit: 25, offset: (this.page - 1) * 25, ...(this.status ? { status: this.status } : {}) }, timeout: 15000,
        });
        if (this.disposed || generation !== this.generation) return;
        if (!Array.isArray(response.data?.items) || !Number.isInteger(response.data?.total)) throw new Error("Invalid task list");
        this.items = response.data.items;
        this.total = response.data.total;
        this.error = "";
        this.lastUpdated = new Date().toISOString();
        if (this.selected) {
          const updated = this.items.find(item => item.id === this.selected.id);
          if (updated) this.selected = updated;
          else if (this.detailsOpen) {
            const selectedId = this.selected.id;
            const detail = await axios.get(`/operations/${encodeURIComponent(selectedId)}`, { timeout: 15000 });
            if (detail.data?.id !== selectedId) throw new Error("Invalid task detail");
            if (!this.disposed && generation === this.generation && this.selected?.id === selectedId) this.selected = detail.data;
          }
        }
      } catch (error) {
        if (!this.disposed && generation === this.generation) this.error = "Could not load tasks. Displayed results may be out of date.";
      } finally {
        if (!this.disposed && generation === this.generation) this.loading = false;
      }
    },
    open(item) {
      this.detailGeneration++;
      this.selected = item;
      this.detailsOpen = true;
      this.detailLoading = false;
      this.detailError = "";
      this.$router?.replace({ query: { ...this.$route?.query, operation: item.id } });
    },
    closeDetails() {
      this.detailsOpen = false;
      this.detailGeneration++;
      const query = { ...this.$route?.query };
      if (query.operation) {
        delete query.operation;
        this.$router?.replace({ query });
      }
    },
    async openRequested(id) {
      const generation = ++this.detailGeneration;
      this.selected = null;
      this.detailsOpen = true;
      this.detailLoading = true;
      this.detailError = "";
      try {
        const response = await axios.get(`/operations/${encodeURIComponent(id)}`, { timeout: 15000 });
        if (this.disposed || generation !== this.detailGeneration) return;
        if (response.data?.id !== id) throw new Error("Invalid task detail");
        this.selected = response.data;
      } catch (error) {
        if (!this.disposed && generation === this.detailGeneration) this.detailError = "Task details are unavailable or you do not have access to this task.";
      } finally {
        if (!this.disposed && generation === this.detailGeneration) this.detailLoading = false;
      }
    },
    async retry() {
      if (this.retrying || !this.selected?.retryable) return;
      this.retrying = true;
      try {
        const response = await axios.post(`/operations/${encodeURIComponent(this.selected.id)}/retry`, {}, { timeout: 15000 });
        this.open(response.data);
        await this.load();
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally { this.retrying = false; }
    },
    kindLabel(task) {
      const names = { "container.action": "Container", "container.deploy": "Deployment", "compose.action": "Stack", "compose.scheduled-update": "Scheduled stack update", "image.pull": "Image pull", "volume.backup": "Volume backup", "volume.restore": "Volume restore" };
      return [names[task.kind] || task.kind, task.action].filter(Boolean).join(" · ");
    },
    statusColor(status) { return { succeeded: "success", failed: "error", interrupted: "warning", running: "info", queued: "secondary" }[status]; },
    formatDate(value) { return value ? new Date(value).toLocaleString() : "—"; },
  },
};
</script>

<style scoped>
.tasks-toolbar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.tasks-toolbar .v-select { flex: 0 1 240px; min-width: 160px; }
.task-details { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px 16px; }
.task-details dt { color: var(--yp-muted); }
.task-details dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 480px) { .task-details { grid-template-columns: 1fr; gap: 4px; } .task-details dd { margin-bottom: 10px; } }
</style>

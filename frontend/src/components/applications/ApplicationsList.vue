<template lang="html">
  <div class="apps-list component yp-workspace-page">
    <div class="yp-page-head">
      <div>
        <h1 class="yp-page-title">Containers</h1>
        <p class="yp-page-sub">Manage containers and keep your preferred views.</p>
      </div>
      <v-btn color="primary" to="/apps/deploy" prepend-icon="mdi-plus">New container</v-btn>
    </div>
    <v-card color="foreground" class="apps-card">
      <div class="container-toolbar pa-4">
        <div class="apps-search-wrap">
          <UnifiedSearch v-model="search" />
        </div>
        <v-spacer />
        <v-btn @click="checkUpdate(apps)" variant="tonal" prepend-icon="mdi-update" :loading="isCheckingUpdates" :disabled="isCheckingUpdates">
          Check updates
        </v-btn>
        <v-btn @click="refresh()" variant="tonal" prepend-icon="mdi-refresh" :loading="isRefreshing" :disabled="isRefreshing">
          Refresh
        </v-btn>
        <v-menu :close-on-content-click="false" location="bottom end">
          <template v-slot:activator="{ props }">
            <v-btn variant="tonal" v-bind="props" prepend-icon="mdi-view-column-outline">
              Columns
            </v-btn>
          </template>
          <v-list color="foreground">
            <v-list-item
              color="primary"
              v-for="(item, index) in headers"
              :key="index"
            >
              <v-checkbox
                v-model="selectedColumnKeys"
                :label="item.title"
                :value="item.key"
                :disabled="item.key === 'name'"
                density="compact"
                hide-details
                multiple
              >
              </v-checkbox>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>

      <div class="container-filter-grid px-4 pb-2" aria-label="Container filters">
        <v-select v-model="view.status" :items="statusOptions" label="Status" density="compact" variant="outlined" hide-details />
        <v-select v-model="view.health" :items="healthOptions" label="Health" density="compact" variant="outlined" hide-details />
        <v-select v-model="view.stack" :items="stackOptions" label="Stack" density="compact" variant="outlined" hide-details />
        <v-select v-model="view.updates" :items="updateOptions" label="Updates" density="compact" variant="outlined" hide-details />
      </div>
      <p v-if="view.updates === 'unconfirmed'" class="text-caption text-medium-emphasis px-4 mb-2">
        No update confirmed includes containers that have not been checked. Use Check updates to refresh availability.
      </p>
      <div class="container-view-toolbar px-4 pb-3">
        <v-select
          :model-value="selectedView || null" :items="savedViewNames" label="Saved view" clearable
          density="compact" variant="outlined" hide-details @update:model-value="applySavedView"
        />
        <v-chip v-if="selectedView && viewModified" size="small" variant="tonal">Modified</v-chip>
        <v-btn variant="text" prepend-icon="mdi-content-save-outline" @click="openSaveView">Save view</v-btn>
        <v-btn v-if="selectedView" variant="text" color="error" prepend-icon="mdi-delete-outline" @click="deleteSavedView">Delete view</v-btn>
        <v-btn variant="text" prepend-icon="mdi-restore" @click="resetView">Reset view</v-btn>
      </div>
      <div class="container-filter-chips px-4 pb-3" aria-live="polite">
        <span class="text-body-2 text-medium-emphasis">{{ filteredApps.length }} of {{ apps.length }} containers</span>
        <v-chip v-for="filter in activeFilters" :key="filter.key" closable size="small" @click:close="clearFilter(filter.key)">{{ filter.label }}</v-chip>
        <v-btn v-if="activeFilters.length" size="small" variant="text" @click="clearFilters">Clear filters</v-btn>
      </div>
      <v-alert v-if="storageWarning" type="info" density="compact" variant="tonal" class="mx-4 mb-3">{{ storageWarning }}</v-alert>

      <v-card-subtitle v-if="action">{{ action }} </v-card-subtitle>

      <!-- Error State -->
      <div v-if="loadError" class="text-center py-4">
        <v-alert type="error" variant="outlined" text>
          Containers could not be loaded. Retry the request or check the server logs.
        </v-alert>
        <v-btn color="primary" @click="retryLoad">Retry</v-btn>
      </div>

      <v-data-table
        v-if="!loadError"
        class="mx-auto foreground"
        :headers="selectedHeaders"
        :items="filteredApps"
        :items-per-page="25"
        :items-per-page-options="[15, 25, 50, -1]"
        @click:row="handleRowClick"
        single-select
        :loading="isLoading"
      >
        <!-- Custom Loading Slot using Skeleton Loader -->
        <template v-slot:loading>
          <v-skeleton-loader
            v-for="n in 5"
            :key="n"
            type="table-row"
            class="my-2"
          ></v-skeleton-loader>
        </template>

        <template v-slot:item.name="{ item }">
          <div class="namecell">
            <v-menu
              :close-on-click="true"
              :close-on-content-click="true"
             
            >
              <template v-slot:activator="{ props }">
                <v-btn icon size="small" v-bind="props" class="" aria-label="Application Actions" title="Application Actions">
                  <v-icon>mdi-chevron-down</v-icon>
                </v-btn>
              </template>
              <v-list color="foreground" density="compact">
                <!-- Inspect Group -->
                <v-list-subheader>Inspect</v-list-subheader>
                <v-list-item @click="viewLogs(item)">
                  <span>
                    <v-icon>mdi-text-box-search-outline</v-icon>
                  </span>
                  <v-list-item-title>View Logs</v-list-item-title>
                </v-list-item>

                <v-tooltip location="left" v-if="item.State.Status !== 'running'">
                  <template v-slot:activator="{ props }">
                    <div v-bind="props">
                      <v-list-item disabled>
                        <span>
                          <v-icon>mdi-console</v-icon>
                        </span>
                        <v-list-item-title>Open Shell</v-list-item-title>
                      </v-list-item>
                    </div>
                  </template>
                  <span>Container must be running to open shell</span>
                </v-tooltip>
                <v-list-item v-else @click="openTerminal(item)">
                  <span>
                    <v-icon>mdi-console</v-icon>
                  </span>
                  <v-list-item-title>Open Shell</v-list-item-title>
                </v-list-item>

                <v-divider></v-divider>

                <!-- Management Group -->
                <v-list-subheader>Management</v-list-subheader>
                <v-list-item @click="editClick({ Name: item.name })">
                  <span>
                    <v-icon>mdi-file-document-edit-outline</v-icon>
                  </span>
                  <v-list-item-title>Edit</v-list-item-title>
                </v-list-item>
                <v-list-item
                  v-if="!item.Config.Image.includes('yachtplus')"
                  @click="Update(item.name)"
                >
                  <span>
                    <v-icon>mdi-update</v-icon>
                  </span>
                  <v-list-item-title>Update</v-list-item-title>
                </v-list-item>

                <v-divider></v-divider>

                <!-- Control Group -->
                <v-list-subheader>Control</v-list-subheader>
                <v-list-item
                  @click="AppAction({ Name: item.name, Action: 'start' })"
                >
                  <span>
                    <v-icon>mdi-play</v-icon>
                  </span>
                  <v-list-item-title>Start</v-list-item-title>
                </v-list-item>
                <v-list-item
                  @click="AppAction({ Name: item.name, Action: 'stop' })"
                >
                  <span>
                    <v-icon>mdi-stop</v-icon>
                  </span>
                  <v-list-item-title>Stop</v-list-item-title>
                </v-list-item>
                <v-list-item
                  @click="AppAction({ Name: item.name, Action: 'restart' })"
                >
                  <span>
                    <v-icon>mdi-refresh</v-icon>
                  </span>
                  <v-list-item-title>Restart</v-list-item-title>
                </v-list-item>
                <v-list-item
                  @click="AppAction({ Name: item.name, Action: 'kill' })"
                >
                  <span>
                    <v-icon>mdi-fire</v-icon>
                  </span>
                  <v-list-item-title>Kill</v-list-item-title>
                </v-list-item>

                <v-divider></v-divider>

                <!-- Danger Zone Group -->
                <v-list-subheader class="error--text">Danger Zone</v-list-subheader>
                <v-list-item
                  @click="
                    selectedApp = item;
                    removeDialog = true;
                  "
                >
                  <span>
                    <v-icon color="error">mdi-delete</v-icon>
                  </span>
                  <v-list-item-title class="error--text"
                    >Remove</v-list-item-title
                  >
                </v-list-item>
              </v-list>
            </v-menu>

            <span class="nametext ml-1">{{ item.name }}</span>
            <v-tooltip location="right"
              v-if="item.isUpdatable"
              color="primary"
              class="mb-2"
            >
              <template v-slot:activator="{ props }">
                <v-avatar
                  class="ml-1"
                  v-bind="props"
                  color="primary"
                  size="6"
                ></v-avatar>
              </template>
              <span>Update Available</span>
            </v-tooltip>
          </div>
        </template>
        <template v-slot:item.project="{ item }">
          <div class="projectcell">
            <span
              >{{ item.Config.Labels["com.docker.compose.project"] || "-" }}
            </span>
          </div>
        </template>
        <template v-slot:item.status="{ item }">
          <div class="statuscell">
            <span>{{ item.State.Status }} </span>
          </div>
        </template>
        <template v-slot:item.health="{ item }">
          <v-chip :color="healthColor(item)" size="small" variant="tonal">{{ healthLabel(item) }}</v-chip>
        </template>
        <template v-slot:item.ports="{ item }">
          <ins
            v-for="(port, index) in convPorts(item.ports)"
            :key="index"
            style="text-decoration: none;"
          >
            <v-tooltip location="top" transition="scale-transition">
              <template v-slot:activator="{ props }">
                <v-chip
                  v-bind="props"
                  class="mx-1"
                  v-show="port.hip != '::'"
                  v-if="port.hip == '0.0.0.0'"
                  color="primary"
                  style="text-decoration: none;"
                  label
                  small
                  :href="portHref(port)"
                  target="_blank"
                  ><v-icon size="small" class="mr-1">mdi-link-variant</v-icon
                  >{{
                    item.Config.Labels[`local.yacht.port.${port.hport}`] ||
                      port.hport
                  }}</v-chip
                >
                <v-chip
                  v-bind="props"
                  class="ma-1"
                  v-else
                  color="primary"
                  style="text-decoration: none;"
                  label
                  small
                  :href="portHref(port)"
                  target="_blank"
                  ><v-icon size="small" class="mr-1">mdi-link-variant</v-icon
                  >{{
                    item.Config.Labels[`local.yacht.port.${port.hport}`] ||
                      port.hport
                  }}</v-chip
                >
              </template>
              <span>
                {{ port.hport }}
              </span>
            </v-tooltip>
          </ins>
        </template>
        <template v-slot:item.image="{ item }">
          <span class="ImageName">{{ item.Config.Image }}</span>
        </template>
        <template v-slot:item.created="{ item }">
          <span class="CreatedAt"> {{ $formatDate(item.Created) }} </span>
        </template>

        <!-- No Data slot -->
        <template v-slot:no-data>
          <div class="text-center pa-4">
            <p>{{ apps.length ? 'No containers match this view.' : 'No containers found.' }}</p>
            <v-btn v-if="activeFilters.length" variant="text" @click="clearFilters">Clear filters</v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-if="selectedApp" v-model="removeDialog" :persistent="removing" max-width="440">
      <v-card>
        <v-card-title style="word-break: break-word">Remove {{ selectedApp.name }}?</v-card-title>
        <v-card-text>
          This permanently removes the container and its writable layer. Mounted volumes are retained.
          The result will also appear in Tasks.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="removing" @click="removeDialog = false">Cancel</v-btn>
          <v-btn variant="text" color="error" :loading="removing" :disabled="removing" @click="confirmRemove">Remove</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="saveViewDialog" max-width="440">
      <v-card>
        <v-card-title>Save container view</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-3">Save filters, search and columns in this browser for your account.</p>
          <v-text-field v-model="viewName" label="View name" maxlength="60" counter="60" :error-messages="viewNameError" @keydown.enter.prevent="saveNamedView" />
          <p v-if="replacingView" class="text-caption">The existing view with this name will be replaced.</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="saveViewDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="saveNamedView">{{ replacingView ? 'Replace view' : 'Save view' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Logs and Terminal Modals -->
    <ContainerLogs
      :visible="logsDialog"
      :containerId="selectedContainerId"
      :containerName="selectedContainerName"
      @close="logsDialog = false"
    />
    <AsyncFeature
      v-if="terminalDialog"
      :loader="loadTerminal"
      name="Terminal"
      :visible="terminalDialog"
      :containerId="selectedContainerId"
      :containerName="selectedContainerName"
      @close="terminalDialog = false"
    />
  </div>
</template>

<script>
import { containerPortLink } from "@/utils/containerLinks";
import { mapActions, mapState } from "vuex";
import ContainerLogs from "@/components/ContainerLogs.vue";
import AsyncFeature from "@/components/AsyncFeature.vue";
import UnifiedSearch from "@/components/UnifiedSearch.vue";
import {
  CONTAINER_VIEW_VERSION, MAX_SAVED_CONTAINER_VIEWS, NO_STACK,
  normalizeContainerView, containerViewStorageKey, readContainerPreferences, writeContainerPreferences,
  hasContainerViewQuery, containerViewFromQuery, containerViewQuery, containerHealth, containerStatus, containerStack, filterContainers,
} from "@/utils/containerViews";

export default {
  components: {
    ContainerLogs,
    AsyncFeature,
    UnifiedSearch
  },
  data() {
    return {
      view: normalizeContainerView(),
      savedViews: [],
      selectedView: "",
      saveViewDialog: false,
      viewName: "",
      viewNameError: "",
      storageWarning: "",
      preferencesReady: false,
      statusOptions: [
        { title: "All statuses", value: "" }, { title: "Running", value: "running" },
        { title: "Stopped", value: "stopped" }, { title: "Paused", value: "paused" },
        { title: "Restarting", value: "restarting" }, { title: "Created", value: "created" },
        { title: "Dead", value: "dead" },
      ],
      healthOptions: [
        { title: "All health states", value: "" }, { title: "Healthy", value: "healthy" },
        { title: "Unhealthy", value: "unhealthy" }, { title: "Starting", value: "starting" },
        { title: "No health check", value: "none" },
      ],
      updateOptions: [
        { title: "All updates", value: "" }, { title: "Update available", value: "available" },
        { title: "No update confirmed", value: "unconfirmed" },
      ],
      expanded: [],
      removeDialog: false,
      removing: false,
      selectedApp: null,
      isCheckingUpdates: false,
      isRefreshing: false,
      host_ip: location.hostname,
      loadTimeout: null,
      loadError: false,

      // New State for Modals
      logsDialog: false,
      terminalDialog: false,
      selectedContainerId: null,
      selectedContainerName: null,

      headers: [],
      headersMap: {
        name: {
          title: "Name",
          key: "name",
          sortable: true,
          align: "start"
        },
        project: {
          title: "Stack",
          key: "project",
          value: containerStack,
          sortable: true
        },
        status: {
          title: "Status",
          key: "status",
          value: containerStatus,
          sortable: true
        },
        health: {
          title: "Health",
          key: "health",
          sortable: false,
        },
        image: {
          title: "Image",
          key: "image",
          value: "Config.Image",
          sortable: true
        },
        ports: {
          title: "Ports",
          key: "ports",
          sortable: false
        },
        created: {
          title: "Created At",
          key: "created",
          value: "Created",
          sortable: true
        }
      }
    };
  },
  methods: {
    async confirmRemove() {
      if (this.removing || !this.selectedApp) return;
      this.removing = true;
      try {
        const succeeded = await this.AppAction({ Name: this.selectedApp.name, Action: "remove" });
        if (succeeded) this.removeDialog = false;
      } catch (error) {
        this.$store.commit("snackbar/setErr", error);
      } finally {
        this.removing = false;
      }
    },
    preferenceStorage() {
      try { return globalThis.localStorage || null; } catch { return null; }
    },
    restorePreferences() {
      this.preferencesReady = false;
      const stored = readContainerPreferences(this.preferenceStorage(), containerViewStorageKey(this.preferenceOwner));
      this.view = stored.current;
      this.savedViews = stored.savedViews;
      this.selectedView = stored.selectedView;
      if (hasContainerViewQuery(this.$route?.query)) {
        this.view = containerViewFromQuery(this.$route.query, this.view.columns);
      }
      this.preferencesReady = true;
    },
    persistPreferences() {
      if (!this.preferencesReady) return;
      const succeeded = writeContainerPreferences(this.preferenceStorage(), containerViewStorageKey(this.preferenceOwner), {
        version: CONTAINER_VIEW_VERSION, current: this.view, savedViews: this.savedViews, selectedView: this.selectedView,
      });
      this.storageWarning = succeeded ? "" : "Browser storage is unavailable. View changes will only last for this session.";
    },
    syncViewAddress() {
      if (!this.preferencesReady || !this.$router?.replace || !this.$route) return;
      const query = containerViewQuery(this.view, this.$route.query);
      if (JSON.stringify(query) === JSON.stringify(this.$route.query || {})) return;
      const navigation = this.$router.replace({ query });
      navigation?.catch(() => {
        this.storageWarning = "The view is available, but its address could not be updated.";
      });
    },
    applySavedView(name) {
      this.selectedView = name || "";
      const saved = this.savedViews.find(item => item.name === name);
      if (saved) this.view = normalizeContainerView(saved.config);
      this.persistPreferences();
    },
    openSaveView() {
      this.viewName = this.selectedView;
      this.viewNameError = "";
      this.saveViewDialog = true;
    },
    saveNamedView() {
      const name = this.viewName.trim();
      if (!name || name.length > 60) {
        this.viewNameError = "Enter a view name between 1 and 60 characters.";
        return;
      }
      const index = this.savedViews.findIndex(item => item.name.toLowerCase() === name.toLowerCase());
      if (index < 0 && this.savedViews.length >= MAX_SAVED_CONTAINER_VIEWS) {
        this.viewNameError = `You can save up to ${MAX_SAVED_CONTAINER_VIEWS} views. Delete a view first.`;
        return;
      }
      const saved = { name, config: normalizeContainerView(this.view) };
      if (index < 0) this.savedViews.push(saved);
      else this.savedViews.splice(index, 1, saved);
      this.selectedView = name;
      this.saveViewDialog = false;
      this.persistPreferences();
    },
    deleteSavedView() {
      this.savedViews = this.savedViews.filter(item => item.name !== this.selectedView);
      this.selectedView = "";
      this.persistPreferences();
    },
    clearFilter(key) { this.view[key] = ""; },
    clearFilters() {
      this.view = normalizeContainerView({ columns: this.view.columns });
    },
    resetView() {
      this.selectedView = "";
      this.view = normalizeContainerView();
      this.persistPreferences();
    },
    healthLabel(item) {
      return ({ healthy: "Healthy", unhealthy: "Unhealthy", starting: "Starting", none: "No health check" })[containerHealth(item)] || "Unknown";
    },
    healthColor(item) {
      return ({ healthy: "success", unhealthy: "error", starting: "warning" })[containerHealth(item)];
    },
    portHref(port) { return containerPortLink(port, window.location); },
    loadTerminal() {
      return import("@/components/ContainerTerminal.vue");
    },
    ...mapActions({
      readApps: "apps/readApps",
      AppAction: "apps/AppAction",
      Update: "apps/AppUpdate",
      checkUpdateStore: "apps/checkAppUpdate"
    }),
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/apps/${encodeURIComponent(item.name.replace(/^\//, ''))}` });
    },
    editClick(appName) {
      this.$router.push({ path: `/apps/edit/${appName.Name}` });
    },
    viewLogs(item) {
      this.selectedContainerId = item.Id;
      this.selectedContainerName = item.name.replace("/", "");
      this.logsDialog = true;
    },
    openTerminal(item) {
      this.selectedContainerId = item.Id;
      this.selectedContainerName = item.name.replace("/", "");
      this.terminalDialog = true;
    },
    convPorts(data) {
      let o = [];
      for (var k in data) {
        if (data[k]) {
          o = o.concat(
            data[k].map(function(x) {
              return { cport: k, hip: x.HostIp, hport: x.HostPort };
            })
          );
        }
      }
      return o;
    },
    async refresh() {
      this.isRefreshing = true;
      try {
        await this.loadAppsWithTimeout();
      } finally {
        this.isRefreshing = false;
      }
    },
    async checkUpdate(apps) {
      this.isCheckingUpdates = true;
      try {
        await this.checkUpdateStore(apps);
      } finally {
        this.isCheckingUpdates = false;
      }
    },
    async retryLoad() {
      this.loadError = false;
      await this.loadAppsWithTimeout();
    },
    async loadAppsWithTimeout() {
      this.loadError = false;
      // Start timeout timer (10 seconds)
      this.loadTimeout = setTimeout(() => {
        if (this.isLoading) {
          this.loadError = true;
        }
      }, 10000);

      try {
        const succeeded = await this.readApps();
        if (succeeded === false) this.loadError = true;
      } catch (e) {
        this.loadError = true;
      } finally {
        clearTimeout(this.loadTimeout);
      }
    }
  },
  computed: {
    ...mapState("apps", [
      "apps",
      "isLoading",
      "isLoadingValue",
      "action",
      "updatable"
    ]),
    preferenceOwner() { return this.$store.state.auth?.username || ""; },
    search: {
      get() { return this.view.search; },
      set(value) { this.view.search = typeof value === "string" ? value.slice(0, 128) : ""; },
    },
    selectedColumnKeys: {
      get() { return this.view.columns; },
      set(columns) { this.view.columns = normalizeContainerView({ columns }).columns; },
    },
    selectedHeaders() { return this.view.columns.map(key => this.headersMap[key]).filter(Boolean); },
    filteredApps() { return filterContainers(this.apps, this.view, this.updatable); },
    stackOptions() {
      const names = new Set(this.apps.map(containerStack).filter(Boolean));
      if (this.view.stack && this.view.stack !== NO_STACK) names.add(this.view.stack);
      return [
        { title: "All stacks", value: "" }, { title: "No stack", value: NO_STACK },
        ...[...names].sort((a, b) => a.localeCompare(b)).map(name => ({ title: name, value: name })),
      ];
    },
    savedViewNames() { return this.savedViews.map(item => item.name).sort((a, b) => a.localeCompare(b)); },
    replacingView() { return this.savedViews.some(item => item.name.toLowerCase() === this.viewName.trim().toLowerCase()); },
    viewModified() {
      const saved = this.savedViews.find(item => item.name === this.selectedView);
      return !!saved && JSON.stringify(saved.config) !== JSON.stringify(normalizeContainerView(this.view));
    },
    activeFilters() {
      const filters = [];
      if (this.view.search) filters.push({ key: "search", label: `Search: ${this.view.search}` });
      for (const key of ["status", "health", "updates"]) {
        if (this.view[key]) filters.push({ key, label: this[`${key === "updates" ? "update" : key}Options`].find(item => item.value === this.view[key])?.title || this.view[key] });
      }
      if (this.view.stack) filters.push({ key: "stack", label: `Stack: ${this.view.stack === NO_STACK ? "No stack" : this.view.stack}` });
      return filters;
    },
  },
  watch: {
    view: {
      deep: true,
      handler() { this.persistPreferences(); this.syncViewAddress(); },
    },
    preferenceOwner() { this.restorePreferences(); },
    "$route.query": {
      deep: true,
      handler(query) {
        const next = containerViewFromQuery(query, this.view.columns);
        if (JSON.stringify(next) !== JSON.stringify(this.view)) this.view = next;
      },
    },
  },
  created() {
    this.headers = Object.values(this.headersMap);
    this.restorePreferences();
  },
  async mounted() {
    await this.loadAppsWithTimeout();
  },
  beforeUnmount() {
    clearTimeout(this.loadTimeout);
  }
};
</script>

<style>
.apps-list.yp-workspace-page { width: 100%; max-width: 1600px; margin-inline: auto; }
.apps-list > .apps-card {
  overflow: visible;
}
.container-toolbar, .container-view-toolbar, .container-filter-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.container-filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.container-view-toolbar > .v-input { flex: 0 1 300px; min-width: 190px; }
.apps-search-wrap { width: 400px; max-width: 100%; min-width: 0; }
@media (max-width: 600px) {
  .container-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .apps-search-wrap { flex-basis: 100%; width: 100%; }
  .container-view-toolbar > .v-input { flex-basis: 100%; }
  .container-toolbar > .v-spacer { display: none; }
}
.apps-list tr:hover {
  cursor: pointer;
}
.ImageName {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.CreatedAt {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.namecell {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>

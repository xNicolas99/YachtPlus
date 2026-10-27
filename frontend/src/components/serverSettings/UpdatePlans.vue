<template>
  <v-card variant="flat">
    <v-card-title>Project update plans</v-card-title>
    <v-card-text>
      <p class="mb-3">Choose when each Compose project may pull images and recreate its services. All times and weekdays use UTC. A window crossing midnight belongs to its starting weekday.</p>
      <v-alert type="info" variant="tonal" class="mb-4">
        Global daily updates are {{ legacyAutoUpdate ? 'enabled' : 'disabled' }}. Saving a project plan overrides that global setting. New plans stay disabled until you enable and save them.
      </v-alert>
      <v-alert v-if="error" type="error" class="mb-3" role="alert">{{ error }}</v-alert>
      <v-progress-linear v-if="loading" indeterminate aria-label="Loading update plans" />
      <div v-if="loaded && !plans.length" class="py-4">No Compose projects were found. Create a project before configuring its update plan.</div>
      <template v-if="plans.length">
        <v-select v-model="selectedProject" :items="plans" item-title="project_name" item-value="project_name"
          label="Compose project" :disabled="loading || saving" hide-details class="mb-4" />
        <template v-if="selectedPlan">
          <div class="d-flex ga-2 flex-wrap align-center mb-3">
            <v-chip :color="selectedPlan.excluded ? 'warning' : selectedPlan.enabled ? 'success' : 'default'" size="small">
              {{ selectedPlan.excluded ? 'Excluded from automatic updates' : selectedPlan.configured ? selectedPlan.enabled ? 'Plan enabled' : 'Plan disabled' : 'Uses global setting' }}
            </v-chip>
            <v-chip size="small">Last result: {{ selectedPlan.last_status }}</v-chip>
            <router-link v-if="selectedPlan.last_operation_id" to="/tasks">View update task</router-link>
          </div>
          <p class="mb-1">Last attempt: {{ formatTime(selectedPlan.last_run) }}</p>
          <p class="mb-4">Next eligible update: {{ formatTime(selectedPlan.next_due) }}</p>
          <v-alert v-if="selectedPlan.last_error" type="warning" variant="tonal" class="mb-3">{{ selectedPlan.last_error }}</v-alert>
          <v-alert v-if="!selectedPlan.project_exists" type="warning" class="mb-3">This project no longer exists. Remove its saved plan or restore the project.</v-alert>
          <v-checkbox v-model="form.excluded" label="Exclude this project from automatic updates" :disabled="formDisabled" hide-details
            @update:model-value="excludeChanged" />
          <v-checkbox v-model="form.enabled" label="Enable scheduled updates" :disabled="formDisabled || form.excluded" hide-details class="mb-3" />
          <v-select v-model="form.weekdays" :items="weekdayOptions" item-title="title" item-value="value" multiple chips
            label="Starting weekdays (UTC)" :disabled="formDisabled || form.excluded" />
          <v-row>
            <v-col cols="12" sm="4"><v-select v-model="form.window_start_hour" :items="startHours" label="Window starts (UTC)" :disabled="formDisabled || form.excluded" /></v-col>
            <v-col cols="12" sm="4"><v-select v-model="form.window_end_hour" :items="endHours" label="Window ends (UTC)" :disabled="formDisabled || form.excluded" /></v-col>
            <v-col cols="12" sm="4"><v-text-field v-model.number="form.cadence_days" type="number" min="1" max="3650" label="At least this many days between attempts" :disabled="formDisabled || form.excluded" /></v-col>
          </v-row>
          <p v-if="validationError" class="text-error mb-3" role="alert">{{ validationError }}</p>
          <p class="text-body-2 mb-3">If a pull outlasts the window, service recreation waits for a future authorized attempt. Manual updates remain available. Changing the approving administrator's credentials or permissions requires saving the plan again.</p>
          <div class="d-flex ga-2 flex-wrap">
            <v-btn color="primary" :loading="saving" :disabled="formDisabled || !!validationError" @click="savePlan">Save plan</v-btn>
            <v-btn v-if="selectedPlan.configured" variant="outlined" :disabled="loading || saving || !loaded" @click="resetDialog = true">Use global setting</v-btn>
          </div>
        </template>
      </template>
    </v-card-text>
    <v-card-actions>
      <v-btn variant="text" :disabled="loading || saving || dirty" @click="fetchPlans">Refresh status</v-btn>
      <v-btn v-if="dirty" variant="text" :disabled="loading || saving" @click="loadForm">Discard changes</v-btn>
      <span v-if="dirty" class="text-caption">Unsaved changes</span>
    </v-card-actions>
    <v-dialog v-model="resetDialog" max-width="480">
      <v-card>
        <v-card-title>Use global update setting?</v-card-title>
        <v-card-text>This removes the saved schedule and exclusion for {{ selectedProject }}. Global daily automatic updates are {{ legacyAutoUpdate ? 'enabled, so this project will join those updates' : 'disabled, so this project will not update automatically' }}.</v-card-text>
        <v-card-actions>
          <v-btn :disabled="saving" @click="resetDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" :disabled="saving" @click="resetPlan">Use global setting</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import axios from "axios";

const fields = ["enabled", "excluded", "weekdays", "window_start_hour", "window_end_hour", "cadence_days"];
const defaultForm = () => ({ enabled: false, excluded: false, weekdays: [0, 1, 2, 3, 4, 5, 6], window_start_hour: 0, window_end_hour: 24, cadence_days: 1 });
const formFor = plan => Object.fromEntries(fields.map(key => [key, Array.isArray(plan[key]) ? [...plan[key]] : plan[key]]));
const validPlan = plan => plan && typeof plan.project_name === "string" && typeof plan.enabled === "boolean"
  && typeof plan.excluded === "boolean" && typeof plan.project_exists === "boolean" && Array.isArray(plan.weekdays)
  && Number.isInteger(plan.window_start_hour) && Number.isInteger(plan.window_end_hour) && Number.isInteger(plan.cadence_days);

export default {
  data() {
    return {
      plans: [], selectedProject: null, form: defaultForm(), savedForm: "", legacyAutoUpdate: false,
      loading: false, saving: false, loaded: false, error: "", resetDialog: false,
      weekdayOptions: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((title, value) => ({ title, value })),
      startHours: Array.from({ length: 24 }, (_, value) => ({ title: `${String(value).padStart(2, "0")}:00`, value })),
      endHours: Array.from({ length: 25 }, (_, value) => ({ title: `${String(value).padStart(2, "0")}:00`, value })),
    };
  },
  computed: {
    selectedPlan() { return this.plans.find(plan => plan.project_name === this.selectedProject); },
    formDisabled() { return this.loading || this.saving || !this.loaded || !this.selectedPlan?.project_exists; },
    dirty() { return !!this.selectedPlan && JSON.stringify(this.form) !== this.savedForm; },
    validationError() {
      if (!this.form.weekdays.length) return "Choose at least one weekday.";
      if (!Number.isInteger(this.form.cadence_days) || this.form.cadence_days < 1 || this.form.cadence_days > 3650) return "Choose an interval from 1 to 3650 days.";
      if (this.form.window_start_hour === this.form.window_end_hour) return "Start and end must differ. Use 00:00–24:00 for an all-day window.";
      return "";
    },
  },
  watch: {
    selectedProject() { this.loadForm(); },
  },
  mounted() { this.fetchPlans(); },
  methods: {
    loadForm() {
      this.form = this.selectedPlan ? formFor(this.selectedPlan) : defaultForm();
      this.savedForm = JSON.stringify(this.form);
      this.resetDialog = false;
    },
    excludeChanged(excluded) { if (excluded) this.form.enabled = false; },
    async fetchPlans() {
      if (this.loading || this.saving || this.dirty) return;
      this.loading = true;
      this.error = "";
      try {
        const { data } = await axios.get("/update-plans");
        if (!Array.isArray(data.items) || !data.items.every(validPlan) || data.timezone !== "UTC") throw new Error("Invalid update plan response");
        this.plans = data.items;
        this.legacyAutoUpdate = data.legacy_auto_update === true;
        this.loaded = true;
        if (!this.plans.some(plan => plan.project_name === this.selectedProject)) this.selectedProject = this.plans[0]?.project_name || null;
        this.loadForm();
      } catch (error) {
        this.loaded = false;
        this.error = error.response?.data?.detail || "Could not load update plans. Retry to refresh their status.";
      } finally { this.loading = false; }
    },
    async savePlan() {
      if (this.formDisabled || this.validationError) return;
      this.saving = true;
      this.error = "";
      try {
        const { data } = await axios.put(`/update-plans/${encodeURIComponent(this.selectedProject)}`, formFor(this.form));
        if (!validPlan(data) || data.project_name !== this.selectedProject) throw new Error("Invalid saved plan response");
        const index = this.plans.findIndex(plan => plan.project_name === data.project_name);
        if (index >= 0) this.plans.splice(index, 1, data);
        this.loadForm();
      } catch (error) {
        this.error = error.response?.data?.detail || "Could not save the update plan. Your changes are retained.";
      } finally { this.saving = false; }
    },
    async resetPlan() {
      if (this.loading || this.saving || !this.loaded || !this.selectedPlan?.configured) return;
      this.saving = true;
      this.error = "";
      try {
        await axios.delete(`/update-plans/${encodeURIComponent(this.selectedProject)}`);
        this.resetDialog = false;
        this.savedForm = JSON.stringify(this.form);
        this.saving = false;
        await this.fetchPlans();
      } catch (error) {
        this.error = error.response?.data?.detail || "Could not remove the saved plan. Refresh status before retrying.";
      } finally { this.saving = false; }
    },
    formatTime(value) {
      if (!value) return "None";
      if (typeof value !== "string") return "Unavailable";
      const date = new Date(value.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(value) ? value : value + "Z");
      return Number.isNaN(date.getTime()) ? "Unavailable" : date.toISOString().replace("T", " ").replace(".000Z", " UTC");
    },
  },
};
</script>

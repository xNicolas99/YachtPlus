<template>
  <div class="compose-editor">
    <v-progress-linear v-if="isLoading" indeterminate aria-label="Loading stack configuration" />
    <v-alert v-if="loadError" type="error" variant="tonal" class="mb-4" role="alert">
      The stack configuration could not be loaded. Your input is preserved.
      <v-btn class="ml-2" variant="text" @click="populateForm">Retry</v-btn>
    </v-alert>
    <v-card>
      <div class="yp-card-head compose-editor-heading">
        <div>
          <h2 class="text-h6">{{ existing ? `Edit ${form.name}` : 'New stack' }}</h2>
          <p class="text-body-2 text-medium-emphasis mb-0">Preview the saved configuration before confirming changes.</p>
        </div>
        <v-chip v-if="isDirty" size="small" color="warning" variant="tonal">Unsaved changes</v-chip>
      </div>
      <v-card-text>
        <v-text-field v-model="form.name" label="Stack name" :disabled="existing || isLoading || isSubmitting"
          :rules="[value => !!value || 'Enter a stack name']"
          hint="Letters, numbers, underscores and hyphens. Start with a letter or number." persistent-hint class="mb-4" />
        <v-alert type="info" variant="tonal" class="mb-4">
          Saving adds explicit security defaults to each service. The preview shows those changes.
          Services needing the image's original behavior require an explicit
          <code>x-yachtplus-security: image-default</code> setting.
          Running containers change only when recreated.
        </v-alert>
        <div class="compose-editor-label mb-2" id="compose-source-label">Compose YAML</div>
        <v-ace-editor v-model:value="form.content" lang="yaml" :theme="editorTheming()"
          :readonly="isLoading || isSubmitting" :options="{ useWorker: false, tabSize: 2, showPrintMargin: false }"
          style="height: 420px; width: 100%" class="compose-source-editor" aria-labelledby="compose-source-label" />
      </v-card-text>
      <v-card-actions class="compose-editor-actions">
        <v-btn variant="text" :disabled="isSubmitting" @click="$router.push({ name: 'View Projects' })">Cancel</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-file-compare" :loading="isPreviewing"
          :disabled="!canPreview || isPreviewing || isSubmitting" @click="previewChanges">Preview changes</v-btn>
        <v-btn color="primary" variant="flat" :loading="isSubmitting" :disabled="!canSave" @click="submitCompose">Save stack</v-btn>
      </v-card-actions>
    </v-card>
    <v-alert v-if="previewError" type="error" variant="tonal" class="mt-4" role="alert">{{ previewError }}</v-alert>
    <v-card v-if="preview" class="mt-4" aria-label="Compose change preview">
      <v-card-title>Review changes</v-card-title>
      <v-card-text>
        <p class="text-body-2 mb-3">This preview does not change files or restart services. The full configuration below is what will be saved.</p>
        <v-alert v-for="warning in preview.warnings" :key="warning" type="warning" variant="tonal" class="mb-3">{{ warning }}</v-alert>
        <h3 class="text-subtitle-1 mb-2">Affected services</h3>
        <div v-if="preview.affected_services.length" class="d-flex flex-wrap ga-2 mb-4">
          <v-chip v-for="service in preview.affected_services" :key="service.name" size="small" :color="service.change === 'removed' ? 'error' : 'info'">
            {{ service.name }} · {{ service.change }}
          </v-chip>
        </div>
        <p v-else class="text-body-2 mb-4">No service configuration changes.</p>
        <h3 class="text-subtitle-1 mb-2">Security defaults applied</h3>
        <ul v-if="preview.security_changes.length" class="compose-security-list mb-4">
          <li v-for="change in preview.security_changes" :key="change.service"><strong>{{ change.service }}</strong>: {{ change.fields.join(', ') }}</li>
        </ul>
        <p v-else class="text-body-2 mb-4">The entered configuration already contains the required security settings.</p>
        <h3 class="text-subtitle-1 mb-2">Changes from the saved file</h3>
        <pre v-if="preview.diff" class="compose-diff" aria-label="Changes from saved configuration"><code><span v-for="(line, index) in diffLines" :key="index" :class="diffClass(line)">{{ line }}</span></code></pre>
        <p v-else class="text-body-2">The saved YAML is unchanged.</p>
        <v-alert v-if="diffTruncated" type="info" variant="tonal" class="mt-3">
          Showing the first 2,000 diff lines. Download the full diff and review the complete configuration below.
          <v-btn variant="text" @click="downloadDiff">Download full diff</v-btn>
        </v-alert>
        <v-expansion-panels class="mt-4" variant="accordion">
          <v-expansion-panel title="Full configuration after saving">
            <v-expansion-panel-text><pre class="compose-normalized">{{ preview.normalized_content }}</pre></v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
        <v-checkbox v-model="previewConfirmed" label="I reviewed the changes and want to save this configuration."
          :disabled="isSubmitting" hide-details class="mt-3" />
      </v-card-text>
    </v-card>
    <v-dialog v-model="leaveDialog" max-width="440" persistent>
      <v-card>
        <v-card-title>Discard unsaved changes?</v-card-title>
        <v-card-text>Your changes have not been saved. Stay to continue editing or leave to discard them.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="resolveLeave(false)">Keep editing</v-btn>
          <v-btn color="warning" variant="flat" @click="resolveLeave(true)">Discard and leave</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { mapActions, mapMutations } from "vuex";
import axios from "axios";
import { VAceEditor } from "vue3-ace-editor";
import "ace-builds/src-noconflict/mode-yaml";
import "ace-builds/src-noconflict/theme-twilight";
import "ace-builds/src-noconflict/theme-textmate";

const sameForm = (first, second) => first?.name === second?.name && first?.content === second?.content;

export default {
  components: { VAceEditor },
  data() {
    return {
      existing: false, form: { name: "", content: "" }, savedForm: { name: "", content: "" },
      isLoading: false, loadError: false, loadSequence: 0, isSubmitting: false,
      savedNavigation: false,
      isPreviewing: false, preview: null, previewForm: null, previewConfirmed: false,
      previewError: "", previewSequence: 0, leaveDialog: false, pendingLeave: null,
    };
  },
  computed: {
    isDirty() { return !sameForm(this.form, this.savedForm); },
    canPreview() { return !this.isLoading && !this.loadError && !!this.form.name && !!this.form.content; },
    canSave() {
      return !!this.preview && this.previewConfirmed && sameForm(this.form, this.previewForm)
        && !this.isSubmitting && !this.isLoading && !this.isPreviewing;
    },
    diffLines() { return (this.preview?.diff || "").split("\n").slice(0, 2000); },
    diffTruncated() { return (this.preview?.diff || "").split("\n").length > 2000; },
  },
  watch: {
    "form.name"() { this.invalidatePreview(); },
    "form.content"() { this.invalidatePreview(); },
    "$route.params.projectName": { immediate: true, handler() { this.populateForm(); } },
  },
  mounted() { window.addEventListener("beforeunload", this.beforeUnload); },
  beforeUnmount() {
    window.removeEventListener("beforeunload", this.beforeUnload);
    this.loadSequence++;
    this.previewSequence++;
    if (this.pendingLeave) this.resolveLeave(false);
  },
  beforeRouteLeave(to, from, next) { this.requestLeave(next); },
  beforeRouteUpdate(to, from, next) { this.requestLeave(next); },
  methods: {
    ...mapMutations({ setErr: "snackbar/setErr" }),
    ...mapActions({ readProject: "projects/readProject" }),
    editorTheming() { return this.$vuetify.theme.global.current.dark ? "twilight" : "textmate"; },
    invalidatePreview() {
      this.previewSequence++;
      this.preview = null;
      this.previewForm = null;
      this.previewConfirmed = false;
      this.isPreviewing = false;
      this.previewError = "";
    },
    async previewChanges() {
      if (!this.canPreview || this.isPreviewing || this.isSubmitting) return;
      const form = { ...this.form };
      const sequence = ++this.previewSequence;
      this.preview = null;
      this.previewForm = null;
      this.previewConfirmed = false;
      this.previewError = "";
      this.isPreviewing = true;
      try {
        const response = await axios.post("/compose/preview", form);
        if (sequence !== this.previewSequence || !sameForm(form, this.form)) return;
        const preview = response.data;
        if (!preview || preview.name !== form.name || typeof preview.normalized_content !== "string" || typeof preview.diff !== "string"
          || typeof preview.preview_token !== "string" || !/^[a-f0-9]{64}$/.test(preview.preview_token)
          || !Array.isArray(preview.affected_services) || !preview.affected_services.every(service => service && typeof service.name === "string" && ["added", "changed", "removed"].includes(service.change))
          || !Array.isArray(preview.security_changes) || !preview.security_changes.every(change => change && typeof change.service === "string" && Array.isArray(change.fields) && change.fields.every(field => typeof field === "string"))
          || !Array.isArray(preview.warnings) || !preview.warnings.every(warning => typeof warning === "string")) {
          throw new Error("The server returned an invalid Compose preview. Retry the preview.");
        }
        this.preview = preview;
        this.previewForm = form;
      } catch (error) {
        if (sequence !== this.previewSequence) return;
        const detail = error.response?.data?.detail;
        this.previewError = typeof detail === "string" ? detail : error.message || "Compose preview failed. Retry the preview.";
      } finally {
        if (sequence === this.previewSequence) this.isPreviewing = false;
      }
    },
    async submitCompose() {
      if (!this.canSave) return;
      this.isSubmitting = true;
      this.savedNavigation = false;
      const sequence = this.loadSequence;
      const form = { ...this.form, preview_token: this.preview.preview_token };
      try {
        const response = await axios.post(`/compose/${encodeURIComponent(form.name)}/edit`, form);
        if (sequence !== this.loadSequence) return;
        this.form = { name: response.data.name, content: response.data.content ?? this.preview.normalized_content };
        this.savedForm = { ...this.form };
        this.savedNavigation = true;
        await this.$router.push({ path: `/projects/${encodeURIComponent(response.data.name)}` });
      } catch (error) {
        if (sequence !== this.loadSequence) return;
        if (error.response?.status === 409) {
          this.invalidatePreview();
          this.previewError = "The saved file or configuration changed. Generate and review a new preview.";
        }
        this.setErr(error);
      } finally {
        this.isSubmitting = false;
        this.savedNavigation = false;
      }
    },
    async populateForm() {
      const sequence = ++this.loadSequence;
      this.invalidatePreview();
      this.loadError = false;
      const projectName = this.$route.params.projectName;
      this.existing = projectName != null && projectName !== "_";
      if (!this.existing) {
        this.form = { name: "", content: "" };
        this.savedForm = { ...this.form };
        this.isLoading = false;
        return;
      }
      this.isLoading = true;
      try {
        const project = await this.readProject(projectName);
        if (sequence !== this.loadSequence) return;
        this.form = { name: project.name || "", content: project.content || "" };
        this.savedForm = { ...this.form };
      } catch (error) {
        if (sequence === this.loadSequence) this.loadError = true;
      } finally {
        if (sequence === this.loadSequence) this.isLoading = false;
      }
    },
    beforeUnload(event) {
      if (!this.isDirty && !this.isSubmitting) return;
      event.preventDefault();
      event.returnValue = "";
    },
    requestLeave(next) {
      if (this.isSubmitting && !this.savedNavigation) { next(false); return; }
      if (!this.isDirty) { next(); return; }
      if (this.pendingLeave) this.pendingLeave(false);
      this.pendingLeave = next;
      this.leaveDialog = true;
    },
    resolveLeave(discard) {
      const next = this.pendingLeave;
      this.pendingLeave = null;
      this.leaveDialog = false;
      if (next) next(discard);
    },
    diffClass(line) {
      if (line.startsWith("+++") || line.startsWith("---")) return "compose-diff-heading";
      if (line.startsWith("+")) return "compose-diff-added";
      if (line.startsWith("-")) return "compose-diff-removed";
      return "";
    },
    downloadDiff() {
      if (!this.preview) return;
      let url;
      let link;
      try {
        url = URL.createObjectURL(new Blob([this.preview.diff], { type: "text/plain;charset=utf-8" }));
        link = document.createElement("a");
        link.href = url;
        link.download = `${this.form.name}-compose.diff`;
        document.body.appendChild(link);
        link.click();
      } catch (error) {
        this.setErr(error);
      } finally {
        link?.remove();
        if (url) URL.revokeObjectURL(url);
      }
    },
  },
};
</script>

<style scoped>
.compose-editor { min-width: 0; }
.compose-editor-heading { gap: 16px; flex-wrap: wrap; }
.compose-editor-actions { flex-wrap: wrap; gap: 8px; padding: 12px 16px; }
.compose-source-editor { border: 1px solid var(--yp-border); border-radius: var(--yp-radius-sm); }
.compose-editor-label { font-weight: 600; }
.compose-security-list { padding-left: 22px; overflow-wrap: anywhere; }
.compose-diff, .compose-normalized {
  background: var(--yp-bg-2); color: var(--yp-text); border: 1px solid var(--yp-border-soft);
  border-radius: var(--yp-radius-sm); padding: 14px; overflow: auto; max-height: 420px;
  font-family: var(--yp-font-mono); font-size: 12px; line-height: 1.6; tab-size: 2;
}
.compose-diff span { display: block; min-height: 1.6em; width: max-content; min-width: 100%; }
.compose-diff-added { color: rgb(var(--v-theme-success)); background: var(--yp-ok-soft); }
.compose-diff-removed { color: rgb(var(--v-theme-error)); background: var(--yp-err-soft); }
.compose-diff-heading { font-weight: 700; }
@media (max-width: 600px) {
  .compose-editor-actions .v-btn { flex: 1 1 auto; }
}
</style>

<template>
  <v-card class="mb-6">
    <v-toolbar color="primary" flat>
      <v-toolbar-title>Network Access &amp; Protection</v-toolbar-title>
    </v-toolbar>
    <v-card-text>
      <p class="mb-3">Only administrators connected from a local network can change network access.</p>
      <v-progress-linear v-if="loading" indeterminate aria-label="Loading security settings" class="mb-3" />
      <v-alert v-if="loadError" type="error" role="alert" class="mb-3">{{ loadError }}</v-alert>
      <p v-if="!policy" data-testid="policy-unknown">Network access and protection status are unavailable until settings load.</p>
      <template v-else>
        <v-alert :type="policy.allow_public ? 'warning' : 'info'" data-testid="active-policy" class="mb-3">
          Last confirmed policy: {{ policy.allow_public ? 'Public access enabled — all IP addresses allowed.' : 'Local networks only — public access blocked.' }}
        </v-alert>
        <p class="mb-3">Local networks: {{ policy.local_networks.join(', ') }}</p>
        <v-alert :type="policy.fail2ban.active ? 'success' : 'error'" role="status" data-testid="fail2ban-status" class="mb-3">
          <strong>{{ policy.fail2ban.active ? 'Fail2ban protection is active.' : 'Fail2ban protection is not ready.' }}</strong>
          <span v-if="!policy.fail2ban.active"> Public access cannot be enabled. Check the server protection configuration.</span>
          <span v-if="policy.fail2ban.required"> Protection is required and cannot be disabled here.</span>
          <span v-else> This deployment does not require protection at startup. Protection settings cannot be changed here.</span>
        </v-alert>
        <v-alert v-if="!policy.can_modify" type="warning" class="mb-3">
          Connect from a local network to change this setting.
        </v-alert>
        <v-checkbox
          :model-value="draftAllowPublic"
          :disabled="!canEdit || (!policy.allow_public && !policy.fail2ban.active)"
          label="Allow public access from all IP addresses"
          data-testid="public-access"
          @update:model-value="changeDraft"
        />
        <p class="mb-3">Public access keeps authentication, two-factor authentication and fail2ban protection in place. Configure external reverse proxies as trusted proxies on the server so client IP addresses are checked correctly.</p>
        <p v-if="hasChanges" data-testid="unsaved-policy" class="mb-3">Unsaved change. The last confirmed policy remains in effect until Save succeeds.</p>
      </template>
      <v-alert v-if="saveError" type="error" role="alert" class="mt-3">{{ saveError }}</v-alert>
    </v-card-text>
    <v-card-actions>
      <v-btn :disabled="loading || saving" @click="fetchSettings">{{ loadError ? 'Retry' : 'Refresh Status' }}</v-btn>
      <v-spacer />
      <v-btn color="primary" :loading="saving" :disabled="!canSave" data-testid="save-security" @click="requestSave">Save</v-btn>
    </v-card-actions>
    <v-dialog v-model="confirmDialog" max-width="560px" persistent>
      <v-card>
        <v-card-title>Enable Public Access</v-card-title>
        <v-card-text>
          <p>This allows connections from every IP address. Authentication, two-factor authentication and fail2ban protection remain in place. Configure any external reverse proxy as trusted before exposing YachtPlus.</p>
          <v-checkbox v-model="publicConfirmed" :disabled="saving" label="I understand and want to allow public access" data-testid="confirm-public" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="saving" @click="cancelConfirmation">Cancel</v-btn>
          <v-btn color="warning" :loading="saving" :disabled="saving || !publicConfirmed || !canSave" data-testid="enable-public" @click="saveSettings(true)">Enable Public Access</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import axios from "axios";

export default {
  emits: ["notify"],
  data() {
    return {
      policy: null,
      draftAllowPublic: null,
      loading: false,
      saving: false,
      loadError: "",
      saveError: "",
      confirmDialog: false,
      publicConfirmed: false
    };
  },
  computed: {
    canEdit() {
      return !!this.policy?.can_modify && !this.loading && !this.saving;
    },
    hasChanges() {
      return !!this.policy && this.draftAllowPublic !== this.policy.allow_public;
    },
    canSave() {
      return this.canEdit && this.hasChanges && (!this.draftAllowPublic || this.policy.fail2ban.active);
    }
  },
  created() {
    this.fetchSettings();
  },
  methods: {
    readPolicy(data) {
      if (typeof data?.allow_public !== "boolean" || typeof data.can_modify !== "boolean" ||
          !Array.isArray(data.local_networks) || !data.local_networks.every(network => typeof network === "string") ||
          typeof data.fail2ban?.required !== "boolean" || typeof data.fail2ban.active !== "boolean") {
        throw new Error("Invalid security settings response");
      }
      return data;
    },
    errorMessage(error, fallback) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail.every(item => typeof item?.msg === "string")) {
        return detail.map(item => item.msg).join("; ");
      }
      return fallback;
    },
    async fetchSettings() {
      if (this.loading || this.saving) return;
      this.loading = true;
      this.policy = null;
      this.draftAllowPublic = null;
      this.loadError = "";
      this.saveError = "";
      this.cancelConfirmation();
      try {
        const response = await axios.get("/settings/security");
        this.policy = this.readPolicy(response.data);
        this.draftAllowPublic = this.policy.allow_public;
      } catch (error) {
        this.loadError = this.errorMessage(error, "Could not load security settings. Retry to verify network access and protection.");
      } finally {
        this.loading = false;
      }
    },
    changeDraft(value) {
      if (!this.canEdit || typeof value !== "boolean") return;
      if (value && !this.policy.fail2ban.active) return;
      this.draftAllowPublic = value;
      this.publicConfirmed = false;
      this.saveError = "";
    },
    requestSave() {
      if (!this.canSave) return;
      if (this.draftAllowPublic) {
        if (!this.confirmDialog) this.publicConfirmed = false;
        this.confirmDialog = true;
      } else {
        return this.saveSettings(false);
      }
    },
    cancelConfirmation() {
      if (this.saving) return;
      this.confirmDialog = false;
      this.publicConfirmed = false;
    },
    async saveSettings(confirmed) {
      if (!this.canSave || (this.draftAllowPublic && (!confirmed || !this.publicConfirmed || !this.confirmDialog))) return;
      this.saving = true;
      this.saveError = "";
      try {
        const response = await axios.put("/settings/security", {
          allow_public: this.draftAllowPublic,
          confirm_public_access: this.draftAllowPublic && confirmed
        });
        this.policy = this.readPolicy(response.data);
        this.draftAllowPublic = this.policy.allow_public;
        this.$emit("notify", { message: "Network Access Settings Saved", color: "success" });
      } catch (error) {
        this.draftAllowPublic = this.policy.allow_public;
        this.saveError = this.errorMessage(error, "Could not save security settings.") + " Refresh Status to verify whether the change was applied.";
      } finally {
        this.saving = false;
        this.cancelConfirmation();
      }
    }
  }
};
</script>

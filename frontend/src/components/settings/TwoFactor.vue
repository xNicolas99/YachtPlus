<template>
  <v-card class="elevation-12">
    <v-toolbar color="primary" dark flat>
      <v-toolbar-title>Two-Factor Authentication</v-toolbar-title>
    </v-toolbar>
    <v-card-text>
      <div v-if="!isEnabled">
        <p>2FA is currently disabled.</p>
        <v-btn color="primary" :loading="busy" :disabled="busy" @click="setup2FA">Setup 2FA</v-btn>
      </div>
      <div v-else>
        <p>2FA is enabled.</p>
        <v-btn color="error" :loading="busy" :disabled="busy" @click="openDisableDialog">Disable 2FA</v-btn>
      </div>

      <!-- Enable / Setup dialog -->
      <v-dialog v-model="setupDialog" max-width="500px" persistent>
        <v-card>
          <v-card-title>Scan QR Code</v-card-title>
          <v-card-text class="text-center">
            <img
              :src="qrCode"
              alt="QR Code"
              v-if="qrCode"
              style="max-width: 100%;"
            />
            <v-text-field
              v-model="token"
              label="Verification Code"
              outlined
              class="mt-4"
              maxlength="6"
              autocomplete="one-time-code"
              @keyup.enter="verifyAndEnable"
            ></v-text-field>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn text @click="setupDialog = false" :disabled="busy">Cancel</v-btn>
            <v-btn color="primary" :loading="busy" :disabled="busy || !token" @click="verifyAndEnable"
              >Verify &amp; Enable</v-btn
            >
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Disable dialog: backend requires password reconfirmation plus
           a fresh TOTP code (security fix against silent 2FA drop via a
           captured cookie). Browser `confirm()` couldn't carry those, so
           "Disable" used to send a body-less request and the backend
           rejected it with 422 — no feedback path existed and the click
           looked like a no-op. -->
      <v-dialog v-model="disableDialog" max-width="500px" persistent>
        <v-card>
          <v-card-title>Disable Two-Factor Authentication</v-card-title>
          <v-card-text>
            <p class="mb-3">
              To disable 2FA we need your current password and a fresh
              code from your authenticator app. This prevents someone
              with a stolen session cookie from turning 2FA off.
            </p>
            <v-text-field
              v-model="disablePassword"
              label="Password"
              type="password"
              outlined
              autocomplete="current-password"
            ></v-text-field>
            <v-text-field
              v-model="disableCode"
              label="2FA Code"
              outlined
              maxlength="6"
              autocomplete="one-time-code"
              @keyup.enter="confirmDisable"
            ></v-text-field>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn text @click="closeDisableDialog" :disabled="busy">Cancel</v-btn>
            <v-btn
              color="error"
              :loading="busy"
              :disabled="busy || !disablePassword || !disableCode"
              @click="confirmDisable"
            >
              Disable
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </v-card-text>
  </v-card>
</template>

<script>
import axios from "axios";

export default {
  data() {
    return {
      isEnabled: false,
      busy: false,
      // Enable flow
      setupDialog: false,
      qrCode: null,
      token: "",
      // Disable flow
      disableDialog: false,
      disablePassword: "",
      disableCode: ""
    };
  },
  created() {
    this.checkStatus();
  },
  methods: {
    notify(message, color = "success") {
      this.$emit("notify", { message, color });
    },
    extractError(err, fallback) {
      // Surface FastAPI's `detail` field; Pydantic 422 returns a list.
      const data = err?.response?.data;
      if (!data) return fallback;
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) {
        return data.detail.map(d => d.msg).join("; ");
      }
      return fallback;
    },
    async checkStatus() {
      try {
        const response = await axios.get("/auth/me");
        this.isEnabled = !!response.data.is_2fa_enabled;
      } catch (err) {
        // Not blocking — if /auth/me fails the user is logged out anyway.
        console.warn("Could not load 2FA status", err);
      }
    },
    async setup2FA() {
      this.busy = true;
      try {
        const response = await axios.post("/auth/2fa/generate");
        this.qrCode = response.data.qr_code;
        this.token = "";
        this.setupDialog = true;
      } catch (err) {
        this.notify(
          "Error generating 2FA: " + this.extractError(err, "Unknown error"),
          "error"
        );
      } finally {
        this.busy = false;
      }
    },
    async verifyAndEnable() {
      if (!this.token) return;
      this.busy = true;
      try {
        // Backend's TwoFactorRequest schema uses `code`, not `token`. The
        // old payload `{ token }` got silently ignored by Pydantic, the
        // server then read `code=undefined`, and verification failed
        // every time. Send the correct field name.
        await axios.post("/auth/2fa/enable", { code: this.token });
        this.isEnabled = true;
        this.setupDialog = false;
        this.token = "";
        this.notify("2FA Enabled", "success");
      } catch (err) {
        this.notify(
          "Verification failed: " + this.extractError(err, "Invalid code"),
          "error"
        );
      } finally {
        this.busy = false;
      }
    },
    openDisableDialog() {
      this.disablePassword = "";
      this.disableCode = "";
      this.disableDialog = true;
    },
    closeDisableDialog() {
      this.disableDialog = false;
      this.disablePassword = "";
      this.disableCode = "";
    },
    async confirmDisable() {
      if (!this.disablePassword || !this.disableCode) return;
      this.busy = true;
      try {
        await axios.post("/auth/2fa/disable", {
          password: this.disablePassword,
          code: this.disableCode
        });
        this.isEnabled = false;
        this.closeDisableDialog();
        this.notify("2FA disabled", "success");
      } catch (err) {
        // Most common: 400 "Password incorrect" or "Invalid 2FA code".
        this.notify(
          "Disable failed: " + this.extractError(err, "Could not disable 2FA"),
          "error"
        );
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

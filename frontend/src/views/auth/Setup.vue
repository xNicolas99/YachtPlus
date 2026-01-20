<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Setup Yacht - Step {{ step }} of 2</v-toolbar-title>
          </v-toolbar>

          <!-- Step 1: Registration -->
          <div v-if="step === 1">
            <v-card-text>
              <p>Please create an administrator account.</p>
              <v-form @submit.prevent="register">
                <v-text-field
                  label="Email"
                  name="email"
                  prepend-icon="mdi-email"
                  type="email"
                  v-model="email"
                  required
                ></v-text-field>

                <v-text-field
                  label="Password"
                  name="password"
                  prepend-icon="mdi-lock"
                  type="password"
                  v-model="password"
                  required
                ></v-text-field>

                <v-text-field
                  label="Confirm Password"
                  name="confirm_password"
                  prepend-icon="mdi-lock-check"
                  type="password"
                  v-model="confirm_password"
                  required
                ></v-text-field>
              </v-form>
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="primary" @click="register" :loading="loading">Create Admin</v-btn>
            </v-card-actions>
          </div>

          <!-- Step 2: 2FA Setup -->
          <div v-if="step === 2">
            <v-card-text class="text-center">
              <p>Scan the QR Code with your Authenticator App.</p>

              <div v-if="qrCode" class="d-flex justify-center mb-4">
                <img :src="qrCode" alt="QR Code" style="max-width: 200px;" />
              </div>
              <v-skeleton-loader v-else type="image" class="mx-auto" width="200" height="200"></v-skeleton-loader>

              <v-text-field
                v-model="token"
                label="Verification Code"
                outlined
                class="mt-4"
                prepend-icon="mdi-two-factor-authentication"
                @keyup.enter="verifyAndFinalize"
              ></v-text-field>
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="primary" @click="verifyAndFinalize" :loading="loading">
                Verify & Finish
              </v-btn>
            </v-card-actions>
          </div>

          <!-- Global Error Alert -->
          <v-card-text v-if="error">
            <v-alert type="error" dense dismissible @input="error = null">
              {{ error }}
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      step: 1,
      email: "",
      password: "",
      confirm_password: "",
      token: "",
      qrCode: null,
      error: null,
      loading: false
    };
  },
  methods: {
    async register() {
      if (this.password !== this.confirm_password) {
        this.error = "Passwords do not match";
        return;
      }
      this.error = null;
      this.loading = true;

      try {
        await axios.post('/setup/register', {
          username: this.email,
          password: this.password
        });

        // Registration successful, move to 2FA step
        this.loading = false;
        this.step = 2;

        // Generate QR Code immediately
        this.generate2FA();

      } catch (err) {
        this.loading = false;
        if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
        } else {
            this.error = "Registration failed.";
        }
      }
    },

    async generate2FA() {
      this.loading = true;
      try {
        const response = await axios.post("/auth/2fa/generate");
        this.qrCode = response.data.qr_code;
      } catch (err) {
        this.error = "Error generating 2FA: " + (err.response?.data?.detail || err.message);
      } finally {
        this.loading = false;
      }
    },

    async verifyAndFinalize() {
      if (!this.token) {
        this.error = "Please enter the verification code.";
        return;
      }
      this.error = null;
      this.loading = true;

      try {
        // 1. Enable 2FA
        await axios.post("/auth/2fa/enable", { token: this.token });

        // 2. Finalize Setup
        await axios.post("/setup/finalize");

        // 3. Update Store and Redirect
        await this.$store.dispatch("auth/CHECK_SETUP");

        // Ensure the user is logged in correctly in the store state
        // The cookie is already there, CHECK_SETUP checks status,
        // AUTH_CHECK verifies the user session.
        await this.$store.dispatch("auth/AUTH_CHECK");

        this.$router.push("/");

      } catch (err) {
        this.loading = false;
        if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
        } else {
            this.error = "Verification or Finalization failed.";
        }
      }
    }
  }
};
</script>

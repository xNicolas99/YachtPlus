<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Setup YachtPlus - Step {{ currentStep }} of 3</v-toolbar-title>
          </v-toolbar>

          <v-window v-model="currentStep">
            <!-- Step 1: Registration -->
            <v-window-item :value="1">
              <v-card-text>
                <p>Please create an administrator account.</p>
                <v-form @submit.prevent="register">
                  <v-text-field
                    label="Username"
                    name="username"
                    prepend-icon="mdi-account"
                    v-model="username"
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
                <v-btn color="primary" @click="register" :loading="loading">Next</v-btn>
              </v-card-actions>
            </v-window-item>

            <!-- Step 2: 2FA Setup -->
            <v-window-item :value="2">
              <v-card-text class="text-center">
                <h3>Enable Two-Factor Authentication</h3>
                <p class="mb-4">Scan the QR Code with your Authenticator App.</p>

                <div v-if="setupQrCode" class="d-flex justify-center mb-4">
                  <img :src="setupQrCode" alt="QR Code" style="max-width: 200px;" />
                </div>
                <v-skeleton-loader v-else type="image" class="mx-auto" width="200" height="200"></v-skeleton-loader>

                <v-text-field
                  v-model="token"
                  label="Verification Code"
                  outlined
                  class="mt-4"
                  prepend-icon="mdi-two-factor-authentication"
                  maxlength="6"
                  @keyup.enter="verify"
                ></v-text-field>
              </v-card-text>
              <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn color="primary" @click="verify" :loading="loading">Verify & Next</v-btn>
              </v-card-actions>
            </v-window-item>

            <!-- Step 3: Completion -->
            <v-window-item :value="3">
              <v-card-text class="text-center">
                <v-icon color="success" size="64" class="mb-4">mdi-check-circle</v-icon>
                <h2>Setup Complete!</h2>
                <p>YachtPlus has been successfully configured.</p>
                <p class="caption">Redirecting to login...</p>
              </v-card-text>
            </v-window-item>
          </v-window>

          <!-- Global Error Alert -->
          <v-card-text v-if="error">
            <v-alert type="error" dense dismissible @click:close="error = null">
              {{ error }}
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { mapState, mapActions } from 'vuex';

export default {
  data() {
    return {
      username: "",
      password: "",
      confirm_password: "",
      token: "",
      error: null,
      loading: false
    };
  },
  computed: {
    ...mapState('auth', ['setupStep', 'setupQrCode']),
    currentStep: {
        get() {
            return this.setupStep;
        },
        set(val) {
            // We control step via store, but v-window needs a setter
        }
    }
  },
  watch: {
    setupStep(val) {
        if (val === 2 && !this.setupQrCode) {
            this.generateQr();
        }
        if (val === 3) {
            this.finalize();
        }
    }
  },
  methods: {
    ...mapActions('auth', ['SETUP_REGISTER', 'SETUP_2FA_GENERATE', 'SETUP_2FA_ENABLE', 'SETUP_FINALIZE']),

    async register() {
      if (this.password !== this.confirm_password) {
        this.error = "Passwords do not match";
        return;
      }
      if (!this.username) {
          this.error = "Username is required";
          return;
      }
      this.error = null;
      this.loading = true;

      try {
        await this.SETUP_REGISTER({
          username: this.username,
          password: this.password
        });

        // Success: Store updates setupStep to 2, watcher triggers generateQr
      } catch (err) {
        if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
        } else {
            this.error = "Registration failed.";
        }
      } finally {
          this.loading = false;
      }
    },

    async generateQr() {
      this.loading = true;
      try {
        await this.SETUP_2FA_GENERATE();
      } catch (err) {
        this.error = "Failed to generate QR Code.";
      } finally {
        this.loading = false;
      }
    },

    async verify() {
      if (!this.token) {
        this.error = "Please enter the verification code.";
        return;
      }
      this.error = null;
      this.loading = true;

      try {
        await this.SETUP_2FA_ENABLE(this.token);
        // Success: Store updates setupStep to 3, watcher triggers finalize
      } catch (err) {
        if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
        } else {
            this.error = "Verification failed.";
        }
      } finally {
        this.loading = false;
      }
    },

    async finalize() {
        this.loading = true;
        try {
            await this.SETUP_FINALIZE();
            setTimeout(() => {
                this.$router.push('/login');
            }, 2000);
        } catch (err) {
            this.error = "Finalization failed.";
            this.loading = false;
        }
    }
  }
};
</script>

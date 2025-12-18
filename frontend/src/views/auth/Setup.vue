<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card color="foreground" class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Setup Yacht</v-toolbar-title>
          </v-toolbar>
          <v-card-text>
            <v-stepper v-model="step">
              <v-stepper-header>
                <v-stepper-step :complete="step > 1" step="1">Create Admin</v-stepper-step>
                <v-divider></v-divider>
                <v-stepper-step :complete="step > 2" step="2">2FA Setup</v-stepper-step>
              </v-stepper-header>

              <v-stepper-items>
                <!-- Step 1: Create Admin -->
                <v-stepper-content step="1">
                  <ValidationObserver ref="obs1" v-slot="{ invalid, validated }">
                    <v-form @submit.prevent="createAdmin">
                      <ValidationProvider name="Email" rules="required|email" v-slot="{ errors, valid }">
                        <v-text-field
                          label="Email"
                          v-model="email"
                          :error-messages="errors"
                          :success="valid"
                          required
                          outlined
                        />
                      </ValidationProvider>

                      <ValidationProvider name="Password" rules="required|min:8" v-slot="{ errors, valid }">
                        <v-text-field
                          label="Password"
                          v-model="password"
                          :error-messages="errors"
                          :success="valid"
                          :type="showPass ? 'text' : 'password'"
                          :append-icon="showPass ? 'mdi-eye' : 'mdi-eye-off'"
                          @click:append="showPass = !showPass"
                          required
                          outlined
                        />
                      </ValidationProvider>

                      <ValidationProvider name="Confirm Password" rules="required|confirmed:Password" v-slot="{ errors, valid }">
                        <v-text-field
                          label="Confirm Password"
                          v-model="confirmPassword"
                          :error-messages="errors"
                          :success="valid"
                          type="password"
                          required
                          outlined
                        />
                      </ValidationProvider>

                      <v-btn color="primary" @click="createAdmin" :disabled="invalid || !validated">
                        Create Account
                      </v-btn>
                    </v-form>
                  </ValidationObserver>
                </v-stepper-content>

                <!-- Step 2: 2FA Setup -->
                <v-stepper-content step="2">
                  <div class="text-center mb-4">
                    <p>Scan the QR code below with your authenticator app.</p>
                    <img v-if="qrCodeUrl" :src="qrCodeUrl" alt="2FA QR Code" style="max-width: 200px;" />
                  </div>

                  <ValidationObserver ref="obs2" v-slot="{ invalid, validated }">
                    <v-form @submit.prevent="verify2FA">
                      <ValidationProvider name="2FA Code" rules="required|digits:6" v-slot="{ errors, valid }">
                        <v-text-field
                          label="Verification Code"
                          v-model="otpToken"
                          :error-messages="errors"
                          :success="valid"
                          required
                          outlined
                          autofocus
                        />
                      </ValidationProvider>
                      <v-btn color="primary" @click="verify2FA" :disabled="invalid || !validated">
                        Verify & Enable
                      </v-btn>
                      <v-btn text @click="skip2FA">Skip</v-btn>
                    </v-form>
                  </ValidationObserver>
                </v-stepper-content>
              </v-stepper-items>
            </v-stepper>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
    <v-snackbar v-model="snackbar" :color="snackbarColor">
      {{ snackbarMessage }}
    </v-snackbar>
  </v-container>
</template>

<script>
import { ValidationObserver, ValidationProvider } from "vee-validate";
import axios from 'axios';
import { mapActions } from 'vuex';

export default {
  components: {
    ValidationProvider,
    ValidationObserver
  },
  data() {
    return {
      step: 1,
      email: '',
      password: '',
      confirmPassword: '',
      showPass: false,
      qrCodeUrl: '',
      otpToken: '',
      snackbar: false,
      snackbarColor: '',
      snackbarMessage: ''
    };
  },
  methods: {
    ...mapActions('auth', ['CHECK_SETUP']),

    async createAdmin() {
      try {
        const response = await axios.post('/api/setup/register', {
          username: this.email,
          password: this.password
        });

        // Assuming success means we are logged in
        this.$store.commit("auth/AUTH_SUCCESS", response);

        // Trigger 2FA Generation
        await this.generate2FA();
        this.step = 2;

      } catch (err) {
        this.showError(err.response ? err.response.data.detail : "Setup failed");
      }
    },

    async generate2FA() {
      try {
        const response = await axios.post('/api/auth/2fa/generate');
        this.qrCodeUrl = response.data.qr_code;
      } catch (err) {
        this.showError("Failed to generate 2FA");
      }
    },

    async verify2FA() {
      try {
        await axios.post('/api/auth/2fa/enable', {
            token: this.otpToken
        });
        this.finishSetup();
      } catch (err) {
        this.showError("Invalid Code");
      }
    },

    async skip2FA() {
      // Just finish setup without enabling 2FA
      this.finishSetup();
    },

    async finishSetup() {
       await this.CHECK_SETUP(); // Update store state
       this.$router.push('/');
    },

    showError(msg) {
      this.snackbarMessage = msg;
      this.snackbarColor = 'error';
      this.snackbar = true;
    }
  }
};
</script>

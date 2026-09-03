<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Login</v-toolbar-title>
          </v-toolbar>
          <v-card-text>
            <div v-if="!requires2FA">
              <v-form @submit.prevent="login">
                <v-text-field
                  label="Login"
                  name="login"
                  prepend-icon="mdi-account"
                  type="text"
                  v-model="email"
                  autocomplete="username"
                  required
                />
                <v-text-field
                  id="password"
                  label="Password"
                  name="password"
                  prepend-icon="mdi-lock"
                  type="password"
                  v-model="password"
                  autocomplete="current-password"
                  required
                />
                <v-alert v-if="error" type="error" dense class="mt-2">
                  {{ error }}
                </v-alert>
              </v-form>
            </div>
            <div v-else>
              <p>Please enter your 2FA code.</p>
              <v-form @submit.prevent="verify2FA">
                <v-text-field
                  label="2FA Code"
                  v-model="otpToken"
                  prepend-icon="mdi-shield-key"
                  required
                  outlined
                  autofocus
                  autocomplete="one-time-code"
                />
                <v-alert v-if="error" type="error" dense class="mt-2">
                  {{ error }}
                </v-alert>
              </v-form>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn
              v-if="!requires2FA"
              color="primary"
              @click="login"
              :loading="loading"
              :disabled="loading"
              >Login</v-btn
            >
            <v-btn
              v-else
              color="primary"
              @click="verify2FA"
              :loading="loading"
              :disabled="loading"
              >Verify</v-btn
            >
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import axios from "axios";

export default {
  data() {
    return {
      email: "",
      password: "",
      otpToken: "",
      requires2FA: false,
      error: null,
      loading: false
    };
  },
  methods: {
    async login() {
      this.error = null;
      this.loading = true;
      try {
        const response = await axios.post(
          "/auth/login_cookie",
          { username: this.email, password: this.password },
          { withCredentials: true }
        );
        if (response.data.login === "2fa_required") {
          this.requires2FA = true;
        } else if (response.data.login === "successful") {
          await this.$store.dispatch("auth/AUTH_REQUEST", {
            username: this.email,
            password: this.password
          });
          this.$router.push("/");
        }
      } catch (err) {
        this.error =
          (err.response && err.response.data && err.response.data.detail) ||
          "Login failed. Please check your credentials.";
      } finally {
        this.loading = false;
      }
    },
    async verify2FA() {
      this.error = null;
      this.loading = true;
      try {
        const response = await axios.post(
          "/auth/login_cookie",
          {
            username: this.email,
            password: this.password,
            otp_token: this.otpToken
          },
          { withCredentials: true }
        );
        if (response.data.login === "successful") {
          await this.$store.dispatch("auth/AUTH_REQUEST", {
            username: this.email,
            password: this.password
          });
          this.$router.push("/");
        }
      } catch (err) {
        this.error =
          (err.response && err.response.data && err.response.data.detail) ||
          "Verification failed.";
      } finally {
        this.loading = false;
      }
    }
  }
};
</script>

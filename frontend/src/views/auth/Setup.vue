<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Setup Yacht</v-toolbar-title>
          </v-toolbar>
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

              <v-alert v-if="error" type="error" dense class="mt-2">
                {{ error }}
              </v-alert>
            </v-form>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="primary" @click="register" :loading="loading">Create Admin</v-btn>
          </v-card-actions>
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
      email: "",
      password: "",
      confirm_password: "",
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
        await axios.post('/auth/register', {
          email: this.email,
          password: this.password
        });
        // After registration, login
        await this.$store.dispatch("auth/AUTH_REQUEST", {
           email: this.email,
           password: this.password
        });
        this.$router.push("/");
      } catch (err) {
        this.loading = false;
        if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
        } else {
            this.error = "Setup failed.";
        }
      }
    }
  }
};
</script>

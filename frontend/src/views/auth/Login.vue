<template>
  <v-container fluid class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card class="elevation-12">
          <v-toolbar color="primary" dark flat>
            <v-toolbar-title>Login</v-toolbar-title>
          </v-toolbar>
          <v-card-text>
            <v-form @submit.prevent="login">
              <v-text-field
                label="Login"
                name="login"
                prepend-icon="mdi-account"
                type="text"
                v-model="email"
                required
              ></v-text-field>

              <v-text-field
                id="password"
                label="Password"
                name="password"
                prepend-icon="mdi-lock"
                type="password"
                v-model="password"
                required
              ></v-text-field>

              <v-alert v-if="error" type="error" dense class="mt-2">
                {{ error }}
              </v-alert>
            </v-form>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="primary" @click="login" :loading="loading">Login</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { useAuthStore } from '@/stores/authStore'

export default {
  data() {
    return {
      email: "",
      password: "",
      error: null,
      loading: false
    };
  },
  methods: {
    login() {
      this.error = null;
      this.loading = true;
      const { email, password } = this;
      const authStore = useAuthStore();

      // Note: the login credentials expect 'username' so we map 'email' to 'username'
      authStore.login({ username: email, password })
        .then(() => {
          this.$router.push("/");
        })
        .catch(err => {
          this.loading = false;
          if (err.response && err.response.data && err.response.data.detail) {
            this.error = err.response.data.detail;
          } else {
             this.error = "Login failed. Please check your credentials.";
          }
        });
    }
  }
};
</script>

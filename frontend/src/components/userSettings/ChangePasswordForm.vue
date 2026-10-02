<template>
  <Form as="div" v-slot="{ meta }">
    <v-card color="foreground" class="elevation-12 pb-8">
      <v-toolbar color="primary" dark flat>
        <v-toolbar-title>Change Password</v-toolbar-title>
      </v-toolbar>
      <v-card-text>
        Change your username, password, or both. Leave the password blank to
        keep your current password.
        <v-form @submit.prevent="onSubmit">
          <v-text-field v-model="currentPassword" label="Current password" type="password" autocomplete="current-password" required />
          <Field
            name="username"
            rules="required"
            v-model="username"
            v-slot="{ componentField, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="componentField"
              label="Username"
              :error-messages="errors"
              :success="fieldMeta.valid"
              required
            />
          </Field>

          <Field
            name="password"
            v-model="password"
            v-slot="{ componentField, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="componentField"
              label="Password"
              :error-messages="errors"
              :success="fieldMeta.valid"
              :type="show1 ? 'text' : 'password'"
              :append-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'"
              @click:append="show1 = !show1"
            />
          </Field>
          <Field
            name="confirm"
            rules="confirmed:@password"
            v-model="confirm"
            v-slot="{ componentField, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="componentField"
              label="Confirm Password"
              :error-messages="errors"
              :success="fieldMeta.valid"
              :type="show2 ? 'text' : 'password'"
              :append-icon="show2 ? 'mdi-eye' : 'mdi-eye-off'"
              @click:append="show2 = !show2"
            />
          </Field>
          <v-alert v-if="error" type="error" class="mb-3">{{ error }}</v-alert>
          <v-btn
            class="float-right"
            @click="onSubmit()"
            color="primary"
            :loading="loading"
            :disabled="!meta.valid || loading"
            >Change User Info</v-btn
          >
        </v-form>
      </v-card-text>
    </v-card>
  </Form>
</template>

<script>
import { Form, Field } from "vee-validate";
import { mapActions } from "vuex";
export default {
  components: {
    Field,
    Form
  },
  props: ["currentUsername"],
  data() {
    return {
      username: this.currentUsername || "",
      password: "",
      currentPassword: "",
      confirm: "",
      show1: false,
      show2: false,
      loading: false,
      error: null
    };
  },
  methods: {
    ...mapActions({
      login: "auth/AUTH_CHANGE_PASS"
    }),
    async onSubmit() {
      if (this.password !== this.confirm) {
        this.error = "Passwords do not match.";
        return;
      }
      this.error = null;
      this.loading = true;
      try {
        await this.login({
          username: this.username.trim(),
          current_password: this.currentPassword,
          password: this.password || null
        });
      } catch (err) {
        this.error = err.response?.data?.detail || "Could not update your account.";
      } finally {
        this.loading = false;
      }
    }
  }
};
</script>

<style lang="css" scope></style>

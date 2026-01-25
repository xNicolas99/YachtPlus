<template>
  <Form as="div" v-slot="{ meta }">
    <v-card color="foreground" class="elevation-12 pb-8">
      <v-toolbar color="primary" dark flat>
        <v-toolbar-title>Change Password</v-toolbar-title>
      </v-toolbar>
      <v-card-text>
        You can also change just your email here (or both your email and
        password).
        <v-form @submit.prevent="onSubmit">
          <Field
            name="username"
            rules="required|email"
            v-model="username"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="field"
              label="Email"
              :error-messages="errors"
              :success="fieldMeta.valid"
              required
            />
          </Field>

          <Field
            name="password"
            rules="required"
            v-model="password"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="field"
              label="Password"
              :error-messages="errors"
              :success="fieldMeta.valid"
              :type="show1 ? 'text' : 'password'"
              :append-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'"
              required
              @click:append="show1 = !show1"
            />
          </Field>
          <Field
            name="confirm"
            rules="confirmed:@password"
            v-model="confirm"
            v-slot="{ field, errors, meta: fieldMeta }"
          >
            <v-text-field
              v-bind="field"
              label="Confirm Password"
              :error-messages="errors"
              :success="fieldMeta.valid"
              :type="show2 ? 'text' : 'password'"
              :append-icon="show2 ? 'mdi-eye' : 'mdi-eye-off'"
              @click:append="show2 = !show2"
            />
          </Field>
          <v-btn
            class="float-right"
            @click="onSubmit()"
            color="primary"
            :disabled="!meta.valid"
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
      confirm: "",
      show1: false,
      show2: false
    };
  },
  methods: {
    ...mapActions({
      login: "auth/AUTH_CHANGE_PASS"
    }),
    onSubmit() {
      this.login({
        username: this.username,
        password: this.password
      });
    }
  }
};
</script>

<style lang="css" scope></style>

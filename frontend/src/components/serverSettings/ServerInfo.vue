<template>
  <v-card color="foreground" class="elevation-12">
    <v-toolbar color="primary" dark flat>
      <v-toolbar-title>Server Settings</v-toolbar-title>
      <v-spacer></v-spacer>
    </v-toolbar>
    <v-card-text>
      This is where you can change settings related to your server.
    </v-card-text>
    <h2 class="font-weight-bold ml-5">Import</h2>
    <Form ref="obs1" v-slot="{ meta, isSubmitting }" @submit="import_settings(importFile)">
      <Field
        name="importFile"
        v-model="importFile"
        rules="required"
        v-slot="{ componentField, errors }"
      >
        <v-file-input
          v-bind="componentField"
          ref="importFile"
          label="Import export.json"
          :error-messages="errors"
          required
          show-size
          accept=".json"
          class="mx-5"
        />
      </Field>
      <v-btn
        class="mx-5"
        color="primary"
        type="submit"
        :disabled="!meta.valid || isSubmitting"
        :loading="isSubmitting"
        >Import
      </v-btn>
    </Form>
    <h2 class="font-weight-bold mt-5 ml-5">Export</h2>
    <v-btn class="mx-5 mb-5" color="primary" @click="export_settings()"
      >Export
    </v-btn>
  </v-card>
</template>

<script>
import { Form, Field } from "vee-validate";
import axios from "axios";
import { mapMutations } from "vuex";
export default {
  components: {
    Form,
    Field
  },
  data() {
    return {
      importFile: null
    };
  },
  methods: {
    ...mapMutations({
      setSuccess: "snackbar/setSuccess",
      setErr: "snackbar/setErr"
    }),
    async export_settings() {
      let fileURL;
      let fileLink;
      try {
        const response = await axios({
          url: "/settings/export",
          method: "GET",
          responseType: "blob"
        });
        fileURL = window.URL.createObjectURL(new Blob([response.data]));
        fileLink = document.createElement("a");
        fileLink.href = fileURL;
        fileLink.setAttribute("download", "export.json");
        document.body.appendChild(fileLink);
        fileLink.click();
      } catch (err) {
        this.setErr(err);
      } finally {
        if (fileLink) fileLink.remove();
        if (fileURL) window.URL.revokeObjectURL(fileURL);
      }
    },
    async import_settings(importFile) {
      const file = Array.isArray(importFile) ? importFile[0] : importFile;
      if (!file) return;
      const formData = new FormData();
      formData.append("upload", file);
      try {
        const response = await axios.post("/settings/export", formData);
        this.setSuccess(response);
      } catch (err) {
        this.setErr(err);
      }
    }
  }
};
</script>

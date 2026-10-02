<template>
  <v-card color="foreground" class="elevation-12 pb-8">
    <v-toolbar color="primary" dark flat>
      <v-toolbar-title>Server Template Variables</v-toolbar-title>
    </v-toolbar>
    <v-card-text>
      <Form v-slot="{ meta }" @submit="submitFormData">
          <transition-group
            name="slide"
            enter-active-class="animated fadeInLeft fast-anim"
            leave-active-class="animated fadeOutLeft fast-anim"
          >
            <v-row v-for="(item, index) in form.templateVariables" :key="index">
              <v-col>
                <Field
                  :name="`templateVariables[${index}].variable`"
                  v-model="item.variable"
                  rules="required"
                  v-slot="{ componentField, errors }"
                >
                  <v-text-field
                    label="Variable"
                    v-bind="componentField"
                    :error-messages="errors"
                    required
                  ></v-text-field>
                </Field>
              </v-col>
              <v-col>
                <Field
                  :name="`templateVariables[${index}].replacement`"
                  v-model="item.replacement"
                  rules="required"
                  v-slot="{ componentField, errors }"
                >
                  <v-text-field
                    label="Replacement"
                    v-bind="componentField"
                    :error-messages="errors"
                    required
                  ></v-text-field>
                </Field>
              </v-col>
              <v-col class="d-flex justify-end" cols="1">
                <v-btn
                  icon
                  :disabled="isSaving"
                  class="align-self-center"
                  @click="removeTemplateVariables(index)"
                >
                  <v-icon>mdi-minus</v-icon>
                </v-btn>
              </v-col>
            </v-row>
          </transition-group>
          <v-row>
            <v-col cols="12" class="d-flex justify-end">
              <v-btn
                icon
                :disabled="isSaving"
                class="align-self-center"
                @click="addTemplateVariables"
              >
                <v-icon>mdi-plus</v-icon>
              </v-btn>
            </v-col>
          </v-row>
          <v-btn
            class="float-right"
            type="submit"
            color="primary"
            :loading="isSaving"
            :disabled="!meta.valid || isSaving"
            >Save</v-btn
          >
      </Form>
    </v-card-text>
    <v-snackbar v-model="saved" location="bottom" color="secondary">
      Saved
      <template v-slot:actions="{ props }">
        <v-btn color="primary" variant="text" v-bind="props" @click="saved = false">
          Close
        </v-btn>
      </template>
    </v-snackbar>
  </v-card>
</template>

<script>
import { Form, Field } from "vee-validate";
import { mapActions } from "vuex";
export default {
  components: {
    Field,
    Form
  },
  data() {
    return {
      form: {
        templateVariables: []
      },
      saved: false,
      isSaving: false
    };
  },
  methods: {
    ...mapActions({
      writeTemplateVariables: "templates/writeTemplateVariables",
      readTemplateVariables: "templates/readTemplateVariables"
    }),
    addTemplateVariables() {
      this.form.templateVariables.push({ variable: "", replacement: "" });
    },
    removeTemplateVariables(index) {
      this.form.templateVariables.splice(index, 1);
    },
    async submitFormData() {
      if (this.isSaving) return;
      const payload = this.form.templateVariables.map(item => ({ ...item }));
      this.saved = false;
      this.isSaving = true;
      try {
        await this.writeTemplateVariables(payload);
        this.saved = true;
      } catch {
        // The store action reports the error through the global snackbar.
      } finally {
        this.isSaving = false;
      }
    },
    async populateForm() {
      try {
        const t_vars = await this.readTemplateVariables();
        this.form = {
          templateVariables: (t_vars || []).map(item => ({ ...item }))
        };
      } catch (error) {
        console.error(error, error.response);
      }
    }
  },

  async created() {
    await this.populateForm();
    this.saved = false;
  }
};
</script>

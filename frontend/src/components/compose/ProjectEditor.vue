<template lang="html">
  <div class="template-form component">
    <v-card>
      <!-- <v-fade-transition>
        <v-progress-linear
          indeterminate
          v-if="isLoading"
          color="primary"
          bottom
        />
      </v-fade-transition> -->
      <v-form>
        <div class="d-flex">
          <v-row>
            <v-col class="flex-grow-1 flex-shrink-0">
              <v-card-title v-if="!this.existing" class="mt-1">
                New Compose Template
              </v-card-title>
              <v-card-title v-if="this.existing" class="mt-1">
                Edit {{ this.form.name }} Project
              </v-card-title>
            </v-col>
            <v-col class="flex-grow-1 flex-shrink-0">
              <v-text-field
                v-if="!this.existing"
                class="mr-3"
                v-model="form.name"
                label="Template Name"
                required
              >
              </v-text-field>
            </v-col>
            <v-col class="flex-grow-0 flex-shrink-1">
              <v-btn @click="submitCompose()" color="primary" class="mr-2 mt-3"
                >submit</v-btn
              >
            </v-col>
          </v-row>
        </div>
        <v-ace-editor
          v-model:value="form.content"
          @init="editorInit"
          lang="yaml"
          :theme="editorTheming()"
          :style="{ height: windowHeight + 'px', width: windowWidth + 'px' }"
          class="editor"
        ></v-ace-editor>
      </v-form>
    </v-card>
  </div>
</template>

<script>
import { mapActions, mapMutations } from "vuex";
import axios from "axios";
import { VAceEditor } from "vue3-ace-editor";
import "ace-builds/src-noconflict/mode-yaml";
import "ace-builds/src-noconflict/theme-twilight";
import "ace-builds/src-noconflict/theme-textmate";

export default {
  data() {
    return {
      existing: false,
      form: {
        name: "",
        content: null
      },
      windowHeight: window.innerHeight - 205,
      windowWidth: window.innerWidth - 80
    };
  },
  components: {
    VAceEditor
  },
  methods: {
    ...mapMutations({
      setErr: "snackbar/setErr"
    }),
    ...mapActions({
      readProject: "projects/readProject"
    }),
    editorInit() {
      // Ace modes/themes are imported at the top
    },
    editorTheming() {
      if (this.$vuetify.theme.dark == false) {
        return "textmate";
      } else {
        return "twilight";
      }
    },
    submitCompose() {
      let url = `/compose/${this.form.name}/edit`;
      axios
        .post(url, this.form, {})
        .then(response => {
          this.$router.push({ path: `/projects/${response.data.name}` });
        })
        .catch(err => {
          this.setErr(err);
        });
    },
    async populateForm() {
      const projectName = this.$route.params.projectName;
      if (projectName != "_" && projectName != null) {
        const project = await this.readProject(projectName);
        this.form = {
          name: project.name || "",
          content: project.content || ""
        };
        this.existing = true;
      }
    }
  },
  async created() {
    await this.populateForm();
  }
};
</script>

<style lang="css">
.ace_gutter {
  z-index: 1;
}
.ace_gutter-active-line {
  z-index: 1;
}
.ace_editor {
  z-index: 1;
}
</style>

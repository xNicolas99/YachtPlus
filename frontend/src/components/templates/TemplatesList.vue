<template lang="html">
  <div class="templates-list component">
    <v-card color="foreground">
      <v-tabs v-model="activeTab" background-color="primary" dark>
        <v-tab>User Templates</v-tab>
        <!-- Renamed from "Docker Hub Popular" — the tab now covers
             DockerHub + GHCR + LinuxServer (via RegistryBrowser). -->
        <v-tab>Docker Online</v-tab>
      </v-tabs>

      <v-tabs-items v-model="activeTab">
        <v-tab-item>
          <v-card flat color="foreground">
            <v-fade-transition>
              <v-progress-linear
                indeterminate
                v-if="isLoading"
                color="primary"
                bottom
              />
            </v-fade-transition>
            <v-card-title class="primary font-weight-bold">
              Templates
              <!-- Three input methods for adding a catalog:
                     mdi-plus      → Add via URL (existing /templates/new form)
                     mdi-upload    → Upload a JSON file from disk
                     mdi-pencil-plus → Paste / type JSON content into a textarea
                   All three end up in the same `templates` table; upload
                   and create produce `local://<uuid>.json` synthetic URLs. -->
              <v-btn class="ml-2" color="secondary" to="/templates/new" aria-label="Add template via URL" title="Add via URL">
                <v-icon>mdi-plus</v-icon>
              </v-btn>
              <v-btn
                class="ml-2"
                color="secondary"
                @click="uploadDialog = true"
                aria-label="Upload template JSON"
                title="Upload JSON"
              >
                <v-icon>mdi-upload</v-icon>
              </v-btn>
              <v-btn
                class="ml-2"
                color="secondary"
                @click="openCreateDialog"
                aria-label="Create template manually"
                title="Create manually"
              >
                <v-icon>mdi-pencil-plus</v-icon>
              </v-btn>
              <v-spacer></v-spacer>
              <v-text-field
                v-model="search"
                append-icon="mdi-magnify"
                label="Search"
                single-line
                hide-details
              ></v-text-field>
            </v-card-title>
            <v-data-table
              class="foreground"
              :headers="headers"
              :items="templates"
              :items-per-page="25"
              :footer-props="{
                'items-per-page-options': [15, 25, 50, -1]
              }"
              :search="search"
              @click:row="handleRowClick"
            >
              <template slot="no-data">
                <div>
                  No templates available. <a href="/#/templates/new">Add</a> one
                  to view information and launch apps from here.
                </div>
              </template>
              <template v-slot:item.title="{ item }">
                <div class="namecell">
                  <span class="nametext">{{ item.title }}</span>
                  <v-menu close-on-click close-on-content-click offset-y>
                    <template v-slot:activator="{ on, attrs }">
                      <v-btn icon size="small" v-bind="attrs" v-on="on" aria-label="Template Actions" title="Template Actions">
                        <v-icon>mdi-dots-horizontal</v-icon>
                      </v-btn>
                    </template>
                    <v-list color="foreground" dense>
                      <v-list-item @click="templateDetails(item.id)">
                        <v-list-item-icon>
                          <v-icon>mdi-eye</v-icon>
                        </v-list-item-icon>
                        <v-list-item-title>View</v-list-item-title>
                      </v-list-item>
                      <v-list-item @click="updateTemplate(item.id)">
                        <v-list-item-icon>
                          <v-icon>mdi-update</v-icon>
                        </v-list-item-icon>
                        <v-list-item-title>Update</v-list-item-title>
                      </v-list-item>
                      <v-divider />
                      <v-list-item
                        @click="
                          selectedTemplate = item;
                          deleteDialog = true;
                        "
                      >
                        <v-list-item-icon>
                          <v-icon>mdi-delete</v-icon>
                        </v-list-item-icon>
                        <v-list-item-title>Delete</v-list-item-title>
                      </v-list-item>
                    </v-list>
                  </v-menu>
                </div>
              </template>
              <template v-slot:item.created_at="{ item }">
                <span>{{ $formatDate(item.created_at) }}</span>
              </template>
              <template v-slot:item.updated_at="{ item }">
                <span>{{ $formatDate(item.updated_at) }}</span>
              </template>
            </v-data-table>
          </v-card>
        </v-tab-item>

        <v-tab-item>
          <v-card flat color="foreground" class="pa-4">
            <RegistryBrowser />
          </v-card>
        </v-tab-item>
      </v-tabs-items>
    </v-card>

    <!-- Upload JSON dialog -->
    <v-dialog v-model="uploadDialog" max-width="520">
      <v-card color="foreground">
        <v-card-title>Upload template JSON</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="uploadForm.title"
            label="Catalog title"
            placeholder="My selfhosted apps"
            :rules="[v => !!v || 'Required']"
            required
          />
          <v-file-input
            v-model="uploadForm.file"
            label="JSON file"
            accept="application/json,.json"
            show-size
            :rules="[v => !!v || 'Required']"
          />
          <p v-if="uploadError" class="text-error">{{ uploadError }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="uploadDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="uploading"
            :disabled="uploading || !uploadForm.title || !uploadForm.file"
            @click="submitUpload"
          >
            Upload
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create / Edit manual JSON dialog. Same dialog used for both
         flows; manualForm.editingId == null => create, else update. -->
    <v-dialog v-model="manualDialog" max-width="780">
      <v-card color="foreground">
        <v-card-title>
          {{ manualForm.editingId == null ? 'Create catalog' : 'Edit catalog' }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="manualForm.title"
            label="Catalog title"
            :rules="[v => !!v || 'Required']"
            required
          />
          <v-textarea
            v-model="manualForm.content"
            label="Catalog JSON (array of template entries)"
            rows="14"
            auto-grow
            spellcheck="false"
            placeholder='[
  {
    "type": 1,
    "title": "Nginx",
    "image": "nginx:latest",
    "ports": ["80:80/tcp"]
  }
]'
            class="yp-mono"
          />
          <p v-if="manualError" class="text-error">{{ manualError }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="manualDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="manualSaving"
            :disabled="manualSaving || !manualForm.title || !manualForm.content"
            @click="submitManual"
          >
            {{ manualForm.editingId == null ? 'Create' : 'Save' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-if="selectedTemplate" v-model="deleteDialog" max-width="290">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Delete the template?
        </v-card-title>
        <v-card-text>
          Are you sure you want to permanently delete the template?<br />
          This action cannot be revoked.
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="deleteDialog = false">
            Cancel
          </v-btn>
          <v-btn
            text
            color="error"
            @click="
              deleteTemplate(selectedTemplate.id);
              deleteDialog = false;
            "
          >
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from "axios";
import { mapActions, mapState } from "vuex";
import RegistryBrowser from "./RegistryBrowser.vue";

export default {
  components: {
    RegistryBrowser
  },
  data() {
    return {
      activeTab: 0,
      selectedTemplate: null,
      deleteDialog: false,
      // Upload + manual-create dialogs share simple form state. The
      // manual dialog also doubles as the editor for an existing local
      // catalog (manualForm.editingId is set).
      uploadDialog: false,
      uploading: false,
      uploadError: null,
      uploadForm: { title: "", file: null },
      manualDialog: false,
      manualSaving: false,
      manualError: null,
      manualForm: { title: "", content: "", editingId: null },
      search: "",
      headers: [
        {
          text: "Title",
          value: "title",
          sortable: true,
          align: "start"
        },
        {
          text: "Created At",
          value: "created_at",
          sortable: true,
          width: "20%"
        },
        {
          text: "Updated At",
          value: "updated_at",
          sortable: true,
          width: "20%"
        }
      ]
    };
  },
  methods: {
    ...mapActions({
      deleteTemplate: "templates/deleteTemplate",
      readTemplates: "templates/readTemplates",
      updateTemplate: "templates/updateTemplate"
    }),
    handleRowClick(value) {
      this.$router.push({ path: `/templates/${value.id}` });
    },
    templateDetails(templateId) {
      this.$router.push({ path: `/templates/${templateId}` });
    },
    openCreateDialog() {
      this.manualForm = { title: "", content: "", editingId: null };
      this.manualError = null;
      this.manualDialog = true;
    },
    async submitUpload() {
      this.uploadError = null;
      this.uploading = true;
      try {
        const fd = new FormData();
        // Vuetify 3 v-file-input emits either a File or a File[]; accept
        // both so the form behaves predictably across versions.
        const file = Array.isArray(this.uploadForm.file)
          ? this.uploadForm.file[0]
          : this.uploadForm.file;
        if (!file) throw new Error("Pick a file first.");
        fd.append("upload", file, file.name);
        await axios.post(
          `/templates/upload?title=${encodeURIComponent(this.uploadForm.title)}`,
          fd,
          { headers: { "Content-Type": "multipart/form-data" } }
        );
        this.uploadDialog = false;
        this.uploadForm = { title: "", file: null };
        await this.readTemplates();
      } catch (err) {
        this.uploadError = err?.response?.data?.detail || err.message || "Upload failed";
      } finally {
        this.uploading = false;
      }
    },
    async submitManual() {
      this.manualError = null;
      this.manualSaving = true;
      try {
        let parsed;
        try {
          parsed = JSON.parse(this.manualForm.content);
        } catch (e) {
          throw new Error("Content is not valid JSON: " + e.message);
        }
        if (this.manualForm.editingId == null) {
          await axios.post("/templates/manual", {
            title: this.manualForm.title,
            content: parsed,
          });
        } else {
          await axios.put(`/templates/${this.manualForm.editingId}/content`, {
            title: this.manualForm.title,
            content: parsed,
          });
        }
        this.manualDialog = false;
        await this.readTemplates();
      } catch (err) {
        this.manualError = err?.response?.data?.detail || err.message || "Save failed";
      } finally {
        this.manualSaving = false;
      }
    }
  },
  computed: {
    ...mapState("templates", ["templates", "isLoading"])
  },
  mounted() {
    this.readTemplates();
  }
};
</script>

<style lang="css" scoped>
.namecell {
  display: flex;
  min-width: 72px;
  align-items: center;
}
.nametext {
  padding: 0px;
  padding-right: 20px;
  flex-grow: 1;
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}
</style>

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
                      <!-- Update = re-fetch from the remote URL. Only
                           makes sense for URL-sourced catalogs; local
                           catalogs have no remote to fetch from. -->
                      <v-list-item
                        v-if="!isLocalTemplate(item)"
                        @click="updateTemplate(item.id)"
                      >
                        <v-list-item-icon>
                          <v-icon>mdi-update</v-icon>
                        </v-list-item-icon>
                        <v-list-item-title>Refresh from URL</v-list-item-title>
                      </v-list-item>
                      <!-- Edit = open the manual JSON editor with the
                           current items pre-loaded. Available for any
                           catalog; PUT /templates/{id}/content replaces
                           the items list (URL templates effectively
                           snapshot themselves until next Refresh). -->
                      <v-list-item @click="openEditDialog(item)">
                        <v-list-item-icon>
                          <v-icon>mdi-pencil</v-icon>
                        </v-list-item-icon>
                        <v-list-item-title>Edit JSON</v-list-item-title>
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
              <!-- Source chip + URL preview. Lets the user tell a
                   GitHub-fetched catalog from a JSON upload from a
                   hand-written one at a glance — previously they all
                   looked identical in the list. -->
              <template v-slot:item.source="{ item }">
                <v-chip
                  :color="sourceFor(item).color"
                  :prepend-icon="sourceFor(item).icon"
                  size="small"
                  variant="tonal"
                >
                  {{ sourceFor(item).label }}
                </v-chip>
              </template>
              <template v-slot:item.url_preview="{ item }">
                <span
                  class="yp-mono text-medium-emphasis"
                  style="font-size:0.85em"
                  :title="item.url"
                >
                  {{ urlPreviewFor(item) }}
                </span>
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
          text: "Source",
          value: "source",
          sortable: false,
          width: "120px"
        },
        {
          text: "Origin",
          value: "url_preview",
          sortable: false,
          width: "30%"
        },
        {
          text: "Created At",
          value: "created_at",
          sortable: true,
          width: "18%"
        },
        {
          text: "Updated At",
          value: "updated_at",
          sortable: true,
          width: "18%"
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
    isLocalTemplate(item) {
      // Backend stores uploaded/manual catalogs under a synthetic
      // `local://<uuid>.json` URL. Use that as the "local" signal
      // here — URL-fetched catalogs always have http(s) URLs.
      return typeof item?.url === "string" && item.url.startsWith("local://");
    },
    sourceFor(item) {
      if (this.isLocalTemplate(item)) {
        return { label: "Uploaded", color: "primary", icon: "mdi-upload" };
      }
      return { label: "URL", color: "secondary", icon: "mdi-cloud-download" };
    },
    urlPreviewFor(item) {
      if (this.isLocalTemplate(item)) return "(local catalog)";
      if (!item?.url) return "";
      // Show host + last path component so the user can still tell
      // catalogs apart without dumping the whole 100-char URL into a
      // narrow table cell.
      try {
        const u = new URL(item.url);
        const parts = u.pathname.split("/").filter(Boolean);
        const tail = parts.slice(-2).join("/") || u.hostname;
        return `${u.host}/${tail}`;
      } catch (_) {
        return item.url;
      }
    },
    openEditDialog(item) {
      this.manualForm = {
        title: item.title || "",
        // Load the FULL JSON for editing. For local templates this is
        // the canonical source. For URL templates we still let the
        // user edit (becomes a snapshot — refresh will overwrite).
        content: "",
        editingId: item.id,
      };
      this.manualError = null;
      this.manualDialog = true;
      // Async fetch of the items so the user can edit content
      axios
        .get(`/templates/${item.id}`)
        .then(resp => {
          const items = resp?.data?.items || [];
          this.manualForm.content = JSON.stringify(items, null, 2);
        })
        .catch(err => {
          this.manualError = this.extractError(err, "Failed to load template content");
        });
    },
    openCreateDialog() {
      this.manualForm = { title: "", content: "", editingId: null };
      this.manualError = null;
      this.manualDialog = true;
    },
    extractError(err, fallback) {
      // FastAPI 422 returns `detail` as an array of {loc, msg, type};
      // the previous string-only handler rendered "[object Object]" and
      // looked exactly like a silent failure. Flatten + pretty-print
      // so the user can tell upload-blocked-on-validation from
      // backend-route-not-found.
      const data = err?.response?.data;
      if (!data) {
        if (err?.response?.status === 404) {
          return "Endpoint not found — backend image may be outdated; run `docker compose pull`.";
        }
        return err?.message || fallback;
      }
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail
          .map(d => {
            const loc = Array.isArray(d.loc) ? d.loc.slice(-1)[0] : "field";
            return `${loc}: ${d.msg}`;
          })
          .join("; ");
      }
      return fallback;
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
        this.uploadError = this.extractError(err, "Upload failed");
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
        this.manualError = this.extractError(err, "Save failed");
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

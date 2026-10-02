<template lang="html">
  <div class="projects-list component" style="max-width: 90%">
    <v-card color="foreground">
      <v-fade-transition>
        <v-progress-linear
          indeterminate
          v-if="isLoading"
          color="primary"
          bottom
        />
      </v-fade-transition>
      <v-card-title class="primary font-weight-bold">
        Compose Stacks
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn
              class="ml-2"
              color="secondary"
              to="/projects/_/edit"
              v-bind="props"
            >
              <v-icon>mdi-plus</v-icon>
            </v-btn>
          </template>
          <span>Add Compose Stack</span>
        </v-tooltip>
        <v-spacer />
        <v-text-field
          v-model="search"
          append-icon="mdi-magnify"
          label="Search"
          single-line
          hide-details
        ></v-text-field>
      </v-card-title>
      <v-card-subtitle v-if="action"
        >Running docker-compose {{ action }} ...</v-card-subtitle
      >

      <v-data-table
        style="max-width: 99%;"
        class="mx-auto project-datatable foreground"
        :headers="headers"
        :items="projects"
        :items-per-page="25"
        :items-per-page-options="[15, 25, 50, -1]"
        :search="search"
        @click:row="handleRowClick"
      >
        <template #no-data>
          <div>
            No Compose available.
          </div>
        </template>
        <template v-slot:item.name="{ item }">
          <div class="d-flex">
            <v-menu
              :close-on-click="true"
              :close-on-content-click="false"
             
            >
              <template v-slot:activator="{ props }">
                <v-btn icon size="small" v-bind="props" class="" aria-label="Project Actions" title="Project Actions">
                  <v-icon>mdi-chevron-down</v-icon>
                </v-btn>
              </template>
              <v-list color="foreground" density="compact">
                <v-list-group prepend-icon="mdi-gamepad">
                  <template #activator="{ props }">
                    <v-list-item v-bind="props" title="Controls" /></template
                  >
                  <v-list color="background" density="compact">
                    <v-list-item
                      @click="ProjectAction({ Name: item.name, Action: 'up' })"
                    >
                      <span>
                        <v-icon>mdi-arrow-up-bold</v-icon>
                      </span>
                      <v-list-item-title>Up</v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'down' })
                      "
                    >
                      <span>
                        <v-icon>mdi-arrow-down-bold</v-icon>
                      </span>
                      <v-list-item-title>Down</v-list-item-title>
                    </v-list-item>
                    <v-divider />
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'start' })
                      "
                    >
                      <span>
                        <v-icon>mdi-play</v-icon>
                      </span>
                      <v-list-item-title>Start</v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'stop' })
                      "
                    >
                      <span>
                        <v-icon>mdi-stop</v-icon>
                      </span>
                      <v-list-item-title>Stop</v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'restart' })
                      "
                    >
                      <span>
                        <v-icon>mdi-refresh</v-icon>
                      </span>
                      <v-list-item-title>Restart</v-list-item-title>
                    </v-list-item>
                    <v-divider />
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'pull' })
                      "
                    >
                      <span>
                        <v-icon>mdi-update</v-icon>
                      </span>
                      <v-list-item-title>Pull</v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'create' })
                      "
                    >
                      <span>
                        <v-icon>mdi-plus-box-multiple</v-icon>
                      </span>
                      <v-list-item-title>Create</v-list-item-title>
                    </v-list-item>
                    <v-divider />
                    <v-list-item
                      @click="
                        ProjectAction({ Name: item.name, Action: 'kill' })
                      "
                    >
                      <span>
                        <v-icon>mdi-fire</v-icon>
                      </span>
                      <v-list-item-title>Kill</v-list-item-title>
                    </v-list-item>

                    <v-list-item
                      @click="ProjectAction({ Name: item.name, Action: 'rm' })"
                    >
                      <span>
                        <v-icon>mdi-delete</v-icon>
                      </span>
                      <v-list-item-title>Remove</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-list-group>
                <v-list-item @click="projectDetails(item.name)">
                  <span>
                    <v-icon>mdi-eye</v-icon>
                  </span>
                  <v-list-item-title>View</v-list-item-title>
                </v-list-item>
                <v-list-item @click="editProject(item.name)">
                  <span>
                    <v-icon>mdi-file-document-edit-outline</v-icon>
                  </span>
                  <v-list-item-title>Edit</v-list-item-title>
                </v-list-item>
                <v-divider />
                <v-list-item
                  @click="
                    selectedProject = item;
                    deleteDialog = true;
                  "
                >
                  <span>
                    <v-icon>mdi-delete</v-icon>
                  </span>
                  <v-list-item-title>Delete</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <span class="align-streatch text-truncate nametext mt-2">{{
              item.name
            }}</span>
            <v-spacer />

            <v-chip
              variant="outlined"
              small
              color="orange lighten-1"
              class="align-center mt-1"
              label
              v-if="item.inUse == false"
              >Unused</v-chip
            >
          </div>
        </template>
        <template v-slot:item.version="{ item }">
          <div class="projectcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.version }}
            </span>
          </div>
        </template>
        <template v-slot:item.path="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ item.path }}
            </span>
          </div>
        </template>
        <template v-slot:item.services="{ item }" class="idcell">
          <div class="idcell">
            <span class="d-inline-block text-truncate idtext">
              {{ Object.keys(item.services).length }}
            </span>
          </div>
        </template>
      </v-data-table>
    </v-card>
    <v-dialog v-if="selectedProject" v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Delete {{ selectedProject["name"] }} stack?
        </v-card-title>
        <v-card-text>
          The stack directory and all files within it will be permanently
          deleted. This action cannot be revoked.
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false">
            Cancel
          </v-btn>
          <v-btn
            variant="text"
            color="error"
            @click="
              ProjectAction({ Name: selectedProject.name, Action: 'delete' });
              deleteDialog = false;
            "
          >
            Delete Stack
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { mapActions, mapState } from "vuex";
export default {
  data() {
    return {
      selectedProject: null,
      deleteDialog: false,
      form: {
        name: ""
      },
      createDialog: false,
      search: "",
      headers: [
        {
          title: "Name",
          key: "name",
          sortable: true
        },
        {
          title: "Version",
          key: "version",
          sortable: true
        },
        {
          title: "Services",
          key: "services",
          sortable: false
        },
        {
          title: "Path",
          key: "path",
          sortable: true
        }
      ]
    };
  },
  methods: {
    ...mapActions({
      readProjects: "projects/readProjects",
      ProjectAction: "projects/ProjectAction"
    }),
    handleRowClick(event, { item }) {
      this.$router.push({ path: `/projects/${item.name}` });
    },
    editProject(projectname) {
      this.$router.push({ path: `/projects/${projectname}/edit` });
    },
    projectDetails(projectname) {
      this.$router.push({ path: `/projects/${projectname}` });
    }
  },
  computed: {
    ...mapState("projects", ["projects", "isLoading", "action"])
  },
  mounted() {
    this.readProjects();
  }
};
</script>

<style lang="css" scoped></style>

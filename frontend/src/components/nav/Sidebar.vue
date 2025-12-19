<template>
  <v-navigation-drawer
    app
    clipped
    permanent
    mini-variant
    expand-on-hover
    color="secondary"
    style="transform: translateX(0) !important;"
  >
    <!-- -->

    <v-list nav dense>
      <div v-for="(link, i) in links" :key="i">
        <!-- Render divider if present in link object, but only if it's explicitly set to true -->
        <v-divider v-if="link.divider" class="my-2" />

        <v-list-item v-if="!link.subLinks" :to="link.to" exact class="mt-1">
          <v-list-item-icon>
            <v-icon>{{ link.icon }}</v-icon>
          </v-list-item-icon>

          <v-list-item-title v-text="link.text" />
        </v-list-item>

        <v-list-group
          v-else
          :key="link.text"
          :prepend-icon="link.icon"
          :value="false"
        >
          <template v-slot:activator>
            <v-list-item-title>{{ link.text }}</v-list-item-title>
          </template>

          <v-list-item
            v-for="sublink in link.subLinks"
            :to="sublink.to"
            :key="sublink.text"
            exact
            class="mb-1"
          >
            <v-list-item-icon>
              <v-icon>{{ sublink.icon }}</v-icon>
            </v-list-item-icon>
            <v-list-item-title>{{ sublink.text }}</v-list-item-title>
          </v-list-item>
        </v-list-group>
      </div>
    </v-list>
    <template v-slot:append>
      <a :href="'https://' + 'yacht.sh'">
        <v-icon size="200%" class="pa-2">mdi-file-document</v-icon>
      </a>
      <br />
      <a :href="'https://' + 'github.com/SelfhostedPro/Yacht'">
        <v-icon size="200%" class="pa-2">mdi-github</v-icon>
      </a>
    </template>
  </v-navigation-drawer>
</template>

<script>
export default {
  data: () => ({
    links: [
      {
        to: "/",
        icon: "mdi-view-dashboard",
        text: "Dashboard"
      },
      {
        text: "Applications",
        to: "/apps",
        icon: "mdi-application"
      },
      {
        text: "Templates",
        to: "/templates",
        icon: "mdi-folder"
      },
      {
        text: "Projects",
        to: "/projects",
        icon: "mdi-book-open"
      },
      {
        icon: "mdi-cube-outline",
        text: "Resources",
        subLinks: [
          {
            text: "Images",
            to: "/resources/images",
            icon: "mdi-disc"
          },
          {
            text: "Volumes",
            to: "/resources/volumes",
            icon: "mdi-database"
          },
          {
            text: "Networks",
            to: "/resources/networks",
            icon: "mdi-network"
          }
        ]
      },
      {
        to: "/users",
        icon: "mdi-account-group",
        text: "Users"
      },
      {
        to: "/settings/info",
        icon: "mdi-cog",
        text: "Settings",
        divider: true // Visual separator before Settings
      }
    ]
  })
};
</script>

<style scoped>
.v-application--is-ltr
  .v-list--dense.v-list--nav
  .v-list-group--no-action
  > .v-list-group__items
  > .v-list-item {
  padding: 0 8px;
}

/* Active state styling */
.v-list-item--active {
  background-color: rgba(255, 255, 255, 0.1) !important;
  border-left: 4px solid var(--v-primary-base) !important;
}

/* Ensure the border doesn't mess up padding */
.v-list-item {
  border-left: 4px solid transparent;
}
</style>

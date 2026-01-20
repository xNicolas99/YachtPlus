<template>
  <v-navigation-drawer
    app
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    :permanent="$vuetify.display.mdAndUp"
    :temporary="$vuetify.display.smAndDown"
    :rail="$vuetify.display.mdAndUp"
    expand-on-hover
    color="surface"
    class="sidebar-nav"
  >
    <v-list nav density="compact">
      <template v-for="(link, i) in links">
        <v-divider :key="`divider-${i}`" v-if="link.divider" class="my-4" />

        <!-- Single Link -->
        <v-list-item
          :key="`item-${i}`"
          v-if="!link.subLinks"
          :to="link.to"
          exact
          class="nav-item mb-1"
          active-class="nav-item-active"
          rounded="lg"
        >
          <template v-slot:prepend>
            <v-icon :icon="link.icon"></v-icon>
          </template>
          <v-list-item-title class="text-body-2 font-weight-medium">{{ link.text }}</v-list-item-title>
        </v-list-item>

        <!-- Group Link -->
        <v-list-group
          v-else
          :key="`group-${i}`"
          :value="link.text"
        >
          <template v-slot:activator="{ props }">
            <v-list-item v-bind="props" class="nav-item mb-1" rounded="lg">
              <template v-slot:prepend>
                 <v-icon :icon="link.icon"></v-icon>
              </template>
              <v-list-item-title class="text-body-2 font-weight-medium">{{ link.text }}</v-list-item-title>
            </v-list-item>
          </template>

          <v-list-item
            v-for="sublink in link.subLinks"
            :to="sublink.to"
            :key="sublink.text"
            exact
            class="nav-item mb-1 pl-6"
            active-class="nav-item-active"
            rounded="lg"
          >
            <template v-slot:prepend>
              <v-icon :icon="sublink.icon" size="small"></v-icon>
            </template>
            <v-list-item-title class="text-body-2">{{ sublink.text }}</v-list-item-title>
          </v-list-item>
        </v-list-group>
      </template>
    </v-list>
  </v-navigation-drawer>
</template>

<script>
export default {
  props: {
    modelValue: {
      type: Boolean,
      default: true
    }
  },
  emits: ['update:modelValue'],
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
        text: "Docker-Compose",
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
        divider: true
      }
    ]
  })
};
</script>

<style scoped>
.sidebar-nav {
  border-right: 1px solid rgba(255, 255, 255, 0.05);
}

.nav-item {
  transition: all 0.2s ease-in-out;
}

.nav-item:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.nav-item-active {
  background: rgba(var(--v-theme-primary), 0.15) !important;
  color: rgb(var(--v-theme-primary)) !important;
  border-left: 4px solid rgb(var(--v-theme-primary)) !important;
  border-top-left-radius: 0 !important;
  border-bottom-left-radius: 0 !important;
}

:deep(.v-list-item__prepend) {
  width: 24px;
}
</style>

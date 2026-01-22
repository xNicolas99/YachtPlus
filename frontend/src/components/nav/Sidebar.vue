<template>
  <v-navigation-drawer
    app
    :model-value="drawerOpen"
    @update:model-value="handleDrawerUpdate"
    :rail="isRail && !isMobile"
    :permanent="!isMobile"
    :temporary="isMobile"
    color="surface"
    class="sidebar-nav"
    :width="250"
  >
    <!-- Header with Toggle -->
    <div class="sidebar-header d-flex align-center px-4 py-3" :class="{ 'justify-center': isRail && !isMobile }">
      <img
        v-if="!isRail || isMobile"
        src="@/assets/logo.png"
        alt="Logo"
        height="32"
        class="mr-2 fade-transition"
      />

      <v-spacer v-if="!isRail && !isMobile"></v-spacer>

      <!-- Desktop Toggle Button -->
      <v-btn
        v-if="!isMobile"
        icon
        variant="text"
        size="small"
        @click="toggleRail"
        color="medium-emphasis"
      >
        <v-icon>{{ isRail ? 'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
      </v-btn>
    </div>

    <v-divider class="mb-2"></v-divider>

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
          :prepend-icon="link.icon"
          :title="isRail ? '' : link.text"
        >
        </v-list-item>

        <!-- Group Link -->
        <v-list-group
          v-else
          :key="`group-${i}`"
          :value="link.text"
        >
          <template v-slot:activator="{ props }">
            <v-list-item
              v-bind="props"
              class="nav-item mb-1"
              rounded="lg"
              :prepend-icon="link.icon"
              :title="isRail ? '' : link.text"
            >
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
            :prepend-icon="sublink.icon"
            :title="isRail ? '' : sublink.text"
          >
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
      default: true // Controls visibility on mobile (drawer open/close)
    }
  },
  emits: ['update:modelValue'],
  data: () => ({
    isRail: false, // Controls collapsed/expanded state on desktop
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
  }),
  computed: {
    isMobile() {
        return this.$vuetify.display.smAndDown;
    },
    drawerOpen() {
        return this.modelValue;
    }
  },
  methods: {
      handleDrawerUpdate(val) {
          this.$emit('update:modelValue', val);
      },
      toggleRail() {
          this.isRail = !this.isRail;
          localStorage.setItem('sidebar_collapsed', this.isRail);
      }
  },
  created() {
      // Restore expanded/collapsed state from local storage on desktop
      const collapsed = localStorage.getItem('sidebar_collapsed');
      if (collapsed !== null) {
          this.isRail = collapsed === 'true';
      }
  }
};
</script>

<style scoped>
.sidebar-nav {
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  transition: width 0.3s ease, transform 0.3s ease;
}

.sidebar-header {
  height: 64px; /* Match standard app bar height */
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

/* Fix icon size in collapsed mode */
:deep(.v-list-item__prepend) {
  width: 24px;
}

.fade-transition {
    animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
</style>

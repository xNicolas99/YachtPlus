<template>
  <v-navigation-drawer
    v-model="drawer"
    :rail="rail"
    permanent
    class="bg-surface"
  >
    <v-list>
      <v-list-item
        prepend-avatar="@/assets/logo.png"
        title="YachtPlus"
        nav
      >
        <template v-slot:append>
          <v-btn
            icon="mdi-chevron-left"
            variant="text"
            @click.stop="rail = !rail"
          ></v-btn>
        </template>
      </v-list-item>
    </v-list>

    <v-divider></v-divider>

    <v-list density="compact" nav>
      <v-list-item
        v-for="item in items"
        :key="item.title"
        :to="item.path"
        :prepend-icon="item.icon"
        :title="item.title"
        exact
      ></v-list-item>
    </v-list>

    <template v-slot:append>
        <v-list density="compact" nav>
            <v-list-item
                prepend-icon="mdi-cog"
                title="Settings"
                to="/settings"
            ></v-list-item>
             <v-list-item
                prepend-icon="mdi-logout"
                title="Logout"
                @click="logout"
            ></v-list-item>
        </v-list>
    </template>
  </v-navigation-drawer>
</template>

<script>
import { mapActions } from 'vuex';

export default {
  data() {
    return {
      drawer: true,
      rail: false,
      items: [
        { title: 'Dashboard', icon: 'mdi-view-dashboard', path: '/' },
        { title: 'Applications', icon: 'mdi-apps', path: '/apps' },
        { title: 'Templates', icon: 'mdi-file-document-box', path: '/templates' },
        { title: 'Resources', icon: 'mdi-folder', path: '/resources' },
        { title: 'Projects', icon: 'mdi-docker', path: '/projects' },
      ],
    };
  },
  methods: {
    ...mapActions('auth', { logout: 'AUTH_LOGOUT' }),
  }
};
</script>

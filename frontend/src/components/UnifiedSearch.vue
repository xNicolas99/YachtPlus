<template>
  <v-autocomplete
    v-model="model"
    :items="items"
    :loading="isLoading"
    :search-input.sync="search"
    hide-no-data
    hide-selected
    item-text="title"
    item-value="id"
    label="Search (Apps, Templates, DockerHub)"
    placeholder="Start typing to Search"
    prepend-icon="mdi-magnify"
    return-object
    dense
    hide-details
    solo-inverted
    flat
    @change="handleSelect"
  >
    <template v-slot:item="{ item }">
      <v-list-item-avatar>
        <img v-if="item.logo" :src="item.logo" />
        <v-icon v-else>{{ item.icon }}</v-icon>
      </v-list-item-avatar>
      <v-list-item-content>
        <v-list-item-title v-text="item.title"></v-list-item-title>
        <v-list-item-subtitle v-text="item.description"></v-list-item-subtitle>
      </v-list-item-content>
      <v-list-item-action>
        <v-chip x-small :color="item.color">{{ item.source }}</v-chip>
      </v-list-item-action>
    </template>
  </v-autocomplete>
</template>

<script>
import axios from "axios";
import { mapState } from "vuex";

export default {
  data: () => ({
    isLoading: false,
    items: [],
    model: null,
    search: null,
    debounce: null
  }),
  computed: {
    ...mapState("apps", ["apps"])
  },
  watch: {
    search(val) {
      if (!val) {
        this.items = [];
        return;
      }
      if (this.debounce) clearTimeout(this.debounce);
      this.debounce = setTimeout(() => {
        this.doSearch(val);
      }, 500);
    }
  },
  methods: {
    async doSearch(query) {
      if (!query || query.length < 2) return;
      this.isLoading = true;
      this.items = [];

      // 1. Search Local Apps
      const localMatches = this.apps
        .filter(app => app.name.toLowerCase().includes(query.toLowerCase()))
        .map(app => ({
          title: app.name,
          description: app.Config.Image,
          id: app.name,
          source: "Local",
          type: "app",
          icon: "mdi-cube-outline",
          color: "primary"
        }));
      this.items = [...localMatches];

      try {
        // Use Unified Search Endpoint
        // Returns { dockerhub: [...], templates: [...] }
        const response = await axios.get(`/search/?q=${query}`);
        const data = response.data;

        // Templates
        const tmplMatches = (data.templates || []).map(t => ({
          title: t.title || t.name,
          description: t.description,
          id: t.id,
          source: "Template",
          type: "template",
          logo: t.logo,
          icon: "mdi-application",
          color: "info"
        }));
        this.items = [...this.items, ...tmplMatches];

        // DockerHub
        const regMatches = (data.dockerhub || []).map(r => ({
           title: r.name,
           description: r.description,
           id: r.name,
           source: "DockerHub",
           type: "image",
           icon: "mdi-docker",
           color: "grey darken-1",
           logo: r.logo
        }));
        this.items = [...this.items, ...regMatches];

      } catch (e) {
        console.error("Search failed", e);
      } finally {
        this.isLoading = false;
      }
    },
    handleSelect(item) {
      if (!item) return;

      if (item.type === "app") {
        // Go to app details
        this.$router.push({ path: `/apps/${item.title}/info` });
      } else if (item.type === "template") {
        this.$router.push({ name: "Deploy", params: { appId: item.id } });
      } else if (item.type === "image") {
        this.$router.push({ path: "/apps/deploy", query: { image: item.id } });
      }

      // Clear selection after action
      this.$nextTick(() => {
        this.model = null;
        this.search = null;
      });
    }
  }
};
</script>

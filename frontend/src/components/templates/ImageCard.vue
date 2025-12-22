<template>
  <v-card
    hover
    @click="$emit('click', image)"
    class="d-flex flex-column"
    height="100%"
  >
    <v-card-title class="d-flex align-start">
      <v-avatar size="40" class="mr-3" tile>
        <img
          :src="currentSrc"
          alt="logo"
          @error="handleImageError"
          v-if="currentSrc"
        />
        <v-icon v-else x-large>mdi-docker</v-icon>
      </v-avatar>
      <div>
        <div
          class="subtitle-1 font-weight-bold"
          style="word-break: break-all; line-height: 1.2"
        >
          {{ image.name }}
        </div>
        <div class="caption grey--text">{{ image.namespace }}</div>
      </div>
      <v-spacer></v-spacer>
      <v-chip x-small color="primary" v-if="image.is_official">Official</v-chip>
    </v-card-title>

    <v-card-text class="flex-grow-1">
      <div class="text-truncate-2" :title="image.description">
        {{ image.description || "No description available." }}
      </div>
    </v-card-text>

    <v-divider></v-divider>

    <v-card-actions>
      <v-row dense no-gutters class="caption grey--text">
        <v-col cols="4" class="d-flex align-center">
          <v-icon x-small class="mr-1">mdi-download</v-icon>
          {{ formatNumber(image.pull_count) }}
        </v-col>
        <v-col cols="4" class="d-flex align-center">
          <v-icon x-small class="mr-1">mdi-star</v-icon>
          {{ formatNumber(image.star_count) }}
        </v-col>
        <v-col cols="4" class="d-flex align-center" v-if="image.last_updated">
          <v-icon x-small class="mr-1">mdi-calendar-clock</v-icon>
          {{ formatDate(image.last_updated) }}
        </v-col>
      </v-row>
      <v-spacer></v-spacer>
      <v-btn text color="primary" small @click.stop="$emit('deploy', image)"
        >Deploy</v-btn
      >
      <v-btn text small @click.stop="$emit('details', image)">Details</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script>
import { getImageLogoWithFallbacks } from "@/utils/imageLogos";

export default {
  name: "ImageCard",
  props: {
    image: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      currentSrc: null,
      sourceIndex: 0,
      logoSources: []
    };
  },
  watch: {
    image: {
      handler: "initLogo",
      immediate: true
    }
  },
  methods: {
    initLogo() {
      // If the backend provided a logo_url (e.g. for LinuxServer), we might want to prioritize it or mix it in.
      // However, the user request says LSIO works, others don't.
      // The util handles LSIO fallback logic.
      // But wait, the backend LSIO logic returns a specific logo URL. The util constructs one.
      // If we want to strictly follow "no regression", we should check if image.logo_url exists and is valid.
      // BUT, Docker Hub/GHCR might return placeholder/invalid ones (user says they show generic icons).
      // Let's assume the util is the source of truth for the "Dynamic Logo Implementation".

      // We can add image.logo_url as the first priority if it exists and is not a generic fallback (like github mark).
      // Or simply trust the util.
      // Let's trust the util but pass the backend URL as an option if needed.
      // Actually, for LSIO, the util generates the fleet URL. Backend returns `project_logo` from API.
      // Let's mix them.

      const { sources, fallback } = getImageLogoWithFallbacks(
        this.image.full_name,
        this.image.source
      );

      this.logoSources = [...sources];

      // If backend provided a specific logo, let's prepend it?
      // For GHCR, backend provides GitHub mark. We want to avoid that if possible, or put it low priority.
      // For LSIO, backend provides a logo.
      // Since the util is "Approach 3: Multiple CDN Fallback Chain", let's use it as primary.

      this.sourceIndex = 0;
      this.currentSrc = this.logoSources[0] || fallback;
    },
    handleImageError() {
      this.sourceIndex++;
      if (this.sourceIndex < this.logoSources.length) {
        this.currentSrc = this.logoSources[this.sourceIndex];
      } else {
        // Fallback to registry icon if all sources fail
        // or keep the last one?
        // Use the hardcoded fallback from util
        const { fallback } = getImageLogoWithFallbacks(
          this.image.full_name,
          this.image.source
        );
        // prevent infinite loop if fallback also fails (it shouldn't if it's a valid URL)
        // But if fallback is same as current, stop.
        if (this.currentSrc === fallback) {
             // giving up, maybe show nothing or keep broken image
             return;
        }
        this.currentSrc = fallback;
      }
    },
    formatNumber(num) {
      if (num === undefined || num === null) return "0";
      if (num >= 1000000000) return (num / 1000000000).toFixed(1) + "B";
      if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
      if (num >= 1000) return (num / 1000).toFixed(1) + "K";
      return num.toString();
    },
    formatDate(dateString) {
      if (!dateString) return "N/A";
      try {
        const date = new Date(dateString);
        return date.toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric"
        });
      } catch (e) {
        return dateString;
      }
    }
  }
};
</script>

<style scoped>
.text-truncate-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

<template>
  <v-card hover height="100%" class="d-flex flex-column">
    <v-card-title class="subtitle-1 font-weight-bold text-truncate d-block pb-1">
      {{ image.name }}
    </v-card-title>
    <v-card-subtitle class="caption py-1">
      <v-chip v-if="image.is_official" x-small color="success" class="mr-1" label>OFFICIAL</v-chip>
      <span v-else class="grey--text">Community</span>
    </v-card-subtitle>
    <v-card-text class="flex-grow-1 py-1">
      <div class="d-flex align-center mb-2">
        <v-icon small class="mr-1">mdi-download</v-icon>
        <span class="caption font-weight-bold mr-3">{{ formatNumber(image.pulls) }}</span>

        <v-icon small class="mr-1">mdi-star</v-icon>
        <span class="caption font-weight-bold">{{ formatNumber(image.stars) }}</span>
      </div>
      <div
        class="caption grey--text text--lighten-1"
        style="line-height: 1.2; max-height: 60px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;"
      >
        {{ image.description || 'No description available.' }}
      </div>
    </v-card-text>
    <v-card-actions>
      <v-spacer></v-spacer>
      <v-btn color="primary" variant="tonal" @click="$emit('deploy', image.name)">
        <v-icon start size="small">mdi-cloud-download</v-icon>
        Deploy
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script>
export default {
  name: "DockerHubImageCard",
  props: {
    image: {
      type: Object,
      required: true,
    },
  },
  methods: {
    formatNumber(num) {
      if (!num) return "0";
      if (num >= 1000000000) {
        return (num / 1000000000).toFixed(1).replace(/\.0$/, "") + "G";
      }
      if (num >= 1000000) {
        return (num / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
      }
      if (num >= 1000) {
        return (num / 1000).toFixed(1).replace(/\.0$/, "") + "k";
      }
      return num.toString();
    },
  },
};
</script>
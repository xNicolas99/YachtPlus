<template>
  <v-card class="elevation-2" :to="to" hover>
    <v-card-text>
      <div class="d-flex justify-space-between align-center">
        <div>
          <v-icon size="40" :color="color">{{ icon }}</v-icon>
        </div>
        <div class="text-right">
          <div class="text-h4 font-weight-bold">{{ count }}</div>
          <div class="text-subtitle-1 grey--text">{{ title }}</div>
        </div>
      </div>
      <v-divider class="my-3"></v-divider>
      <div class="d-flex flex-wrap justify-space-between">
        <div
          v-for="(item, index) in items"
          :key="index"
          class="caption font-weight-medium mr-2"
        >
          <v-icon x-small :color="item.color">{{
            item.icon || "mdi-circle"
          }}</v-icon>
          {{ item.label }}: {{ item.count }}
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  name: "StatsCard",
  props: {
    title: String,
    count: Number,
    icon: String,
    color: {
      type: String,
      default: "primary"
    },
    to: String,
    items: {
      type: Array,
      default: () => []
    }
  }
};
</script>

<style scoped>
.v-card {
  transition: transform 0.2s, box-shadow 0.2s;
}
.v-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}
</style>

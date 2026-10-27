<template lang="html">
  <div class="templates page">
    <PageHeader title="Templates" subtitle="Deploy containers from your catalogs or browse container registries.">
      <template v-if="$route.name !== 'View Templates'" #actions>
        <v-btn :to="{ name: 'View Templates' }" variant="text" prepend-icon="mdi-arrow-left">All templates</v-btn>
      </template>
    </PageHeader>
    <transition
      name="slide"
      enter-active-class="animated slideInRight delay"
      leave-active-class="animated slideOutLeft"
    >
      <router-view></router-view>
    </transition>
  </div>
</template>

<script>
import PageHeader from "@/components/PageHeader.vue";
export default { components: { PageHeader } };
</script>

<style lang="css" scoped></style>

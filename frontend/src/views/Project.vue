<template lang="html">
  <div class="compose page">
    <PageHeader title="Stacks" subtitle="Manage multi-container applications with Docker Compose.">
      <template v-if="$route.name !== 'View Projects'" #actions>
        <v-btn :to="{ name: 'View Projects' }" variant="text" prepend-icon="mdi-arrow-left">All stacks</v-btn>
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

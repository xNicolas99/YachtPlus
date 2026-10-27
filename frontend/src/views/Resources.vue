<template lang="html">
  <div class="resources page">
    <PageHeader title="Resources" subtitle="Manage images, networks, and persistent volumes.">
      <template #actions>
        <nav class="d-flex flex-wrap ga-1" aria-label="Resource types">
          <v-btn :to="{ name: 'Images' }" variant="text" size="small" :active="$route.path.startsWith('/resources/images')">Images</v-btn>
          <v-btn :to="{ name: 'Networks' }" variant="text" size="small" :active="$route.path.startsWith('/resources/networks')">Networks</v-btn>
          <v-btn :to="{ name: 'Volumes' }" variant="text" size="small" :active="$route.path.startsWith('/resources/volumes')">Volumes</v-btn>
        </nav>
      </template>
    </PageHeader>
    <router-view v-slot="{ Component }">
      <transition
        name="slide"
        enter-active-class="animated slideInRight delay"
        leave-active-class="animated slideOutLeft"
      >
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<script>
import PageHeader from "@/components/PageHeader.vue";
export default { components: { PageHeader } };
</script>

<style lang="css"></style>

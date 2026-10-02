<template lang="html">
  <div class="images page">
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
export default {};
</script>

<style lang="css"></style>

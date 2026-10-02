<template>
  <v-card color="foreground" class="mx-4 mt-2" raised>
    <v-card-title class="primary font-weight-bold"> Logs</v-card-title>
    <v-virtual-scroll
      ref="logcontainer"
      :bench="20"
      :items="logs"
      height="600"
      item-height="20"
      class="keep-whitespace"
      id="logcontainer"
    >
      <template v-slot="{ item }">
        <p id="logtext">
          {{ item }}
        </p>
      </template>
    </v-virtual-scroll>
  </v-card>
</template>

<script>
export default {
  props: ["app", "logs"],
  watch: {
    logs: {
      handler() {
        this.$nextTick(() => {
          if (this.$refs.logcontainer && this.$refs.logcontainer.$el) {
            const container = this.$refs.logcontainer.$el;
            container.scrollTop = container.scrollHeight;
          }
        });
      },
      deep: true
    }
  }
};
</script>

<style>
#logtext {
  font: 1rem Inconsolata, monospace;
}
#logcontainer {
  background-color: var(--v-background-base) !important;
}
.keep-whitespace {
  white-space: pre;
}
</style>

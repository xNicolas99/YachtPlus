<template>
  <div>
    <v-card color="foreground">
      <v-card-title class="primary font-weight-bold">
        Theme Settings
      </v-card-title>
      <v-card-text>
        <h2 class="mt-2">Presets:</h2>
        <v-select
          v-model="selectedPreset"
          :items="presetOptions"
          label="Select a Preset"
          outlined
          dense
          @change="applyPreset"
        ></v-select>

        <h2 class="mt-2">Customize Colors:</h2>
        <v-row class="mt-2">
          <v-col cols="12" sm="6">
            <h3 class="mb-2">Primary Color</h3>
            <v-color-picker
              v-model="primaryColor"
              hide-canvas
              hide-inputs
              show-swatches
              swatches-max-height="100"
              class="mx-auto"
            ></v-color-picker>
          </v-col>
          <v-col cols="12" sm="6">
            <h3 class="mb-2">Secondary Color</h3>
            <v-color-picker
              v-model="secondaryColor"
              hide-canvas
              hide-inputs
              show-swatches
              swatches-max-height="100"
              class="mx-auto"
            ></v-color-picker>
          </v-col>
        </v-row>
        <br />
        <h2 class="mt-2">Logo:</h2>
        <v-switch
          @change="setDarkmode"
          v-model="$vuetify.theme.dark"
          :label="`Dark Theme: ${$vuetify.theme.dark.toString()}`"
        />
      </v-card-text>
      <v-btn class="ml-2 mb-2" @click="setTheme" color="primary">set</v-btn>
      <v-btn class="ml-2 mb-2" @click="resetTheme" color="secondary"
        >reset</v-btn
      >
    </v-card>
  </div>
</template>

<script>
export default {
  data() {
    return {
      color_toggle: null, // Kept for compatibility per request
      selectedPreset: null,
      primaryColor: null,
      secondaryColor: null,
      presets: {
        Ocean: {
          primary: "#0EA5E9",
          secondary: "#1E293B"
        },
        Forest: {
          primary: "#2E7D32",
          secondary: "#E8F5E9"
        },
        Sunset: {
          primary: "#F4511E",
          secondary: "#FCE4EC"
        }
      }
    };
  },
  mounted() {
    const currentTheme = this.$vuetify.theme.global.current;
    this.primaryColor = currentTheme.colors.primary;
    this.secondaryColor = currentTheme.colors.secondary;
  },
  computed: {
    presetOptions() {
      return Object.keys(this.presets);
    }
  },
  methods: {
    applyPreset() {
      if (this.selectedPreset && this.presets[this.selectedPreset]) {
        const preset = this.presets[this.selectedPreset];
        this.primaryColor = preset.primary;
        this.secondaryColor = preset.secondary;
      }
    },
    setTheme() {
      // Save to localStorage
      localStorage.setItem("theme_primary", this.primaryColor);
      localStorage.setItem("theme_secondary", this.secondaryColor);
      localStorage.setItem("dark_theme", this.$vuetify.theme.global.name.value === "dark");

      // Update Runtime
      const themes = ['light', 'dark'];
      themes.forEach(t => {
        if (this.$vuetify.theme.themes[t]) {
           this.$vuetify.theme.themes[t].colors.primary = this.primaryColor;
           this.$vuetify.theme.themes[t].colors.secondary = this.secondaryColor;
        }
      });

      // Also update current theme directly to see instant effect
      this.$vuetify.theme.global.current.colors.primary = this.primaryColor;
      this.$vuetify.theme.global.current.colors.secondary = this.secondaryColor;
    },
    setDarkmode() {
      // Vuetify 3 toggle
      localStorage.setItem("dark_theme", this.$vuetify.theme.global.name.value === "dark");
    },
    resetTheme() {
      localStorage.removeItem("theme_primary");
      localStorage.removeItem("theme_secondary");
      localStorage.removeItem("dark_theme");
      window.location.reload();
    }
  }
};
</script>

<style></style>

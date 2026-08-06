<template>
  <div>
    <v-card>
      <v-card-title class="font-weight-bold">
        Theme Settings
      </v-card-title>
      <v-card-text>
        <h2 class="mt-2">Presets:</h2>
        <v-select
          v-model="selectedPreset"
          :items="presetOptions"
          label="Select a Preset"
          variant="outlined"
          density="compact"
          @update:modelValue="applyPreset"
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
        <h2 class="mt-2">Dark Mode:</h2>
        <v-switch
          @update:modelValue="setDarkmode"
          v-model="isDark"
          :label="`Dark Theme: ${isDark.toString()}`"
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
  computed: {
    presetOptions() {
      return Object.keys(this.presets);
    },
    // Vuetify 3 exposes the current theme name as a ref. Bind the switch
    // to a computed that reads/writes it cleanly (replaces the broken
    // `$vuetify.theme.dark` Vuetify-2 API).
    isDark: {
      get() {
        return this.$vuetify.theme.global.name.value === "dark";
      },
      set(val) {
        this.$vuetify.theme.global.name.value = val ? "dark" : "light";
      }
    }
  },
  mounted() {
    const currentTheme = this.$vuetify.theme.global.current;
    this.primaryColor = currentTheme.colors.primary;
    this.secondaryColor = currentTheme.colors.secondary;
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
      localStorage.setItem("dark_theme", this.isDark);

      // Update Runtime — Vuetify 3 theme colors are refs.
      const themes = ['light', 'dark'];
      themes.forEach(t => {
        if (this.$vuetify.theme.themes.value[t]) {
          this.$vuetify.theme.themes.value[t].colors.primary = this.primaryColor;
          this.$vuetify.theme.themes.value[t].colors.secondary = this.secondaryColor;
        }
      });

      // Also update current theme directly to see instant effect
      this.$vuetify.theme.global.current.colors.primary = this.primaryColor;
      this.$vuetify.theme.global.current.colors.secondary = this.secondaryColor;
    },
    setDarkmode() {
      // Vuetify 3 toggle — persist the resolved theme name.
      localStorage.setItem("dark_theme", this.isDark);
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

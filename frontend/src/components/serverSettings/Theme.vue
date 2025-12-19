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

        <h2 class="mt-2">Colors:</h2>
        <br />
        <v-btn-toggle v-model="color_toggle">
          <v-btn
            :color="$vuetify.theme.themes[theme].primary"
            class="secondary--text"
            >Primary</v-btn
          >
          <v-btn
            :color="$vuetify.theme.themes[theme].secondary"
            class="primary--text"
            >Secondary</v-btn
          >
          <v-btn
            :color="$vuetify.theme.themes[theme].background"
            class="primary--text"
            >Background</v-btn
          >
          <v-btn
            :color="$vuetify.theme.themes[theme].foreground"
            class="primary--text"
            >Foreground</v-btn
          >
          <v-btn
            :color="$vuetify.theme.themes[theme].tabs"
            class="primary--text"
            >Tabs</v-btn
          >
        </v-btn-toggle>
        <v-color-picker
          v-if="color_toggle !== undefined"
          v-model="picker"
          show-swatches
          swatches-max-height="200"
          class="mt-2 ml-2"
          mode="hexa"
          :value="picker"
        />
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
      color_toggle: null,
      selectedPreset: null,
      presets: {
        Ocean: {
          dark: {
            primary: "#00E5FF", // Cyan A400
            secondary: "#1E293B", // Slate 800
            background: "#0F172A", // Slate 900
            foreground: "#1E293B",
            tabs: "#1E293B",
            accent: "#10B981",
            error: "#EF4444",
            info: "#3B82F6",
            success: "#10B981",
            warning: "#F59E0B"
          },
          light: {
            primary: "#0EA5E9",
            secondary: "#F1F5F9",
            background: "#FFFFFF",
            foreground: "#FFFFFF",
            tabs: "#FFFFFF"
          }
        },
        Forest: {
          dark: {
            primary: "#66BB6A", // Green 400
            secondary: "#2E4C2E", // Dark Green
            background: "#1B2E1B", // Deep Green
            foreground: "#2E4C2E",
            tabs: "#2E4C2E",
            accent: "#10B981",
            error: "#EF4444",
            info: "#3B82F6",
            success: "#10B981",
            warning: "#F59E0B"
          },
          light: {
            primary: "#2E7D32",
            secondary: "#E8F5E9",
            background: "#FFFFFF",
            foreground: "#FFFFFF",
            tabs: "#FFFFFF"
          }
        },
        Sunset: {
          dark: {
            primary: "#FF7043", // Deep Orange 400
            secondary: "#4A274A", // Dark Purple
            background: "#2D1B2E", // Deep Purple/Brown
            foreground: "#4A274A",
            tabs: "#4A274A",
            accent: "#10B981",
            error: "#EF4444",
            info: "#3B82F6",
            success: "#10B981",
            warning: "#F59E0B"
          },
          light: {
            primary: "#F4511E",
            secondary: "#FCE4EC",
            background: "#FFFFFF",
            foreground: "#FFFFFF",
            tabs: "#FFFFFF"
          }
        }
      }
    };
  },
  computed: {
    presetOptions() {
      return Object.keys(this.presets);
    },
    theme() {
      return this.$vuetify.theme.dark ? "dark" : "light";
    },
    picker: {
      get() {
        if (this.color_toggle == 0) {
          return this.$vuetify.theme.themes[this.theme].primary;
        } else if (this.color_toggle == 1) {
          return this.$vuetify.theme.themes[this.theme].secondary;
        } else if (this.color_toggle == 2) {
          return this.$vuetify.theme.themes[this.theme].background;
        } else if (this.color_toggle == 3) {
          return this.$vuetify.theme.themes[this.theme].foreground;
        } else if (this.color_toggle == 4) {
          return this.$vuetify.theme.themes[this.theme].tabs;
        } else return null;
      },
      set(v) {
        if (this.color_toggle == 0) {
          this.$vuetify.theme.themes[this.theme].primary = v;
        } else if (this.color_toggle == 1) {
          this.$vuetify.theme.themes[this.theme].secondary = v;
        } else if (this.color_toggle == 2) {
          this.$vuetify.theme.themes[this.theme].background = v;
        } else if (this.color_toggle == 3) {
          this.$vuetify.theme.themes[this.theme].foreground = v;
        } else if (this.color_toggle == 4) {
          this.$vuetify.theme.themes[this.theme].tabs = v;
        } else return null;
      }
    },
    setColor() {
      this.$vuetify.theme.themes[this.theme][this.picker] == this.color;
      return this.color;
    }
  },
  methods: {
    applyPreset() {
      if (this.selectedPreset && this.presets[this.selectedPreset]) {
        const preset = this.presets[this.selectedPreset];

        // Update both dark and light themes for consistency
        Object.keys(preset.dark).forEach(key => {
          this.$vuetify.theme.themes.dark[key] = preset.dark[key];
        });
        Object.keys(preset.light).forEach(key => {
          this.$vuetify.theme.themes.light[key] = preset.light[key];
        });

        // Immediately save to persistence
        this.setTheme();
      }
    },
    setTheme() {
      localStorage.setItem("dark_theme", this.$vuetify.theme.dark.toString());
      localStorage.setItem("theme", JSON.stringify(this.$vuetify.theme.themes));
    },
    setDarkmode() {
      localStorage.setItem("dark_theme", this.$vuetify.theme.dark.toString());
    },
    resetTheme() {
      localStorage.removeItem("theme");
      localStorage.removeItem("dark_theme");
      window.location.reload();
    }
  }
};
</script>

<style></style>

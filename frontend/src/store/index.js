import { createStore } from "vuex";
import auth from "./modules/auth";
import templates from "./modules/templates.js";
import apps from "./modules/apps.js";
import snackbar from "./modules/snackbar.js";
import images from "./modules/images.js";
import volumes from "./modules/volumes.js";
import networks from "./modules/networks.js";
import projects from "./modules/projects.js";

export default createStore({
  state: {
    // templates: [],
    // itemCount: 10
  },
  mutations: {
    clearUserData(state) {
      for (const name of ["apps", "projects", "templates", "images", "volumes", "networks", "snackbar"]) {
        const module = state[name];
        for (const key of Object.keys(module)) {
          if (Array.isArray(module[key])) module[key] = [];
          else if (key.startsWith("isLoading")) module[key] = key === "isLoading" ? false : null;
          else if (typeof module[key] === "string") module[key] = "";
          else if (typeof module[key] === "boolean") module[key] = false;
          else if (module[key] && typeof module[key] === "object") module[key] = {};
        }
      }
    },
    // setTemplates(state, templates) {
    //   state.templates = templates;
    // }
  },
  actions: {
    // readTemplates({ commit }) {
    //   const url = "/templates/";
    //   axios
    //     .get(url)
    //     .then(response => {
    //       let templates = response.data.data;
    //       commit("setTemplates", templates);
    //     });
    // }
  },
  getters: {
    // getTemplates(state) {
    //   return state.templates;
    // }
  },
  modules: {
    templates,
    apps,
    images,
    volumes,
    networks,
    projects,
    auth,
    snackbar
  }
});

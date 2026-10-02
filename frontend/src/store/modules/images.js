import axios from "axios";
import router from "@/router/index";
import { readResourcePages } from "@/utils/resourcePages";

const state = {
  images: [],
  isLoading: false
};

const mutations = {
  setImages(state, images) {
    state.images = images;
  },
  setImage(state, image) {
    const idx = state.images.findIndex(x => x.Id === image.Id);
    if (idx < 0) {
      state.images.push(image);
    } else {
      state.images.splice(idx, 1, image);
    }
  },
  addImage(state, image) {
    state.images.push(image);
  },
  removeImage(state, image) {
    const idx = state.images.findIndex(x => x.Id === image.Id);
    if (idx < 0) {
      return;
    }
    state.images.splice(idx, 1);
  },
  setLoading(state, loading) {
    state.isLoading = loading;
  }
};

const actions = {
  async readImages({ commit }) {
    commit("setLoading", true);
    try {
      const items = await readResourcePages("/resources/images/");
      commit("setImages", items);
      return items;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  readImage({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/images/${id}`;
    return axios
      .get(url)
      .then(response => {
        const image = response.data;
        commit("setImage", image);
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
      })
      .finally(() => {
        commit("setLoading", false);
      });
  },
  async writeImage({ commit, dispatch }, payload) {
    commit("setLoading", true);
    try {
      await axios.post("/resources/images/", payload);
      await dispatch("readImages");
      await router.push({ name: "Images" });
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  updateImage({ commit, dispatch }, id) {
    commit("setLoading", true);
    const url = `/resources/images/${id}/pull`;
    return axios
      .post(url)
      .then(response => {
        const image = response.data;
        commit("setImage", image);
        return dispatch("readImages");
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
      })
      .finally(() => {
        commit("setLoading", false);
      });
  },
  deleteImage({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/images/${id}`;
    return axios
      .delete(url)
      .then(response => {
        const image = response.data;
        commit("removeImage", image);
        return true;
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
        return false;
      })
      .finally(() => {
        commit("setLoading", false);
      });
  }
};

const getters = {
  getImageById(state) {
    return Id => {
      return state.images.find(x => x.Id == Id);
    };
  }
};

export default {
  namespaced: true,
  state,
  mutations,
  getters,
  actions
};

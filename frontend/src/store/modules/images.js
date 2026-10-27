import axios from "axios";
import { runTrackedOperation } from "@/utils/operations";
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
      await runTrackedOperation(axios, { kind: "image.pull", resource: payload.image });
      await dispatch("readImages");
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  async updateImage({ commit, dispatch }, id) {
    commit("setLoading", true);
    try {
      await runTrackedOperation(axios, { kind: "image.pull", resource: id, action: "update" });
      await dispatch("readImages");
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally { commit("setLoading", false); }
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

import axios from "axios";
import router from "@/router/index";
import { readResourcePages } from "@/utils/resourcePages";

const state = {
  volumes: [],
  isLoading: false
};

const mutations = {
  setVolumes(state, volumes) {
    state.volumes = volumes;
  },
  setVolume(state, volume) {
    const idx = state.volumes.findIndex(x => x.Name === volume.Name);
    if (idx < 0) {
      state.volumes.push(volume);
    } else {
      state.volumes.splice(idx, 1, volume);
    }
  },
  addVolume(state, volume) {
    state.volumes.push(volume);
  },
  removeVolume(state, volume) {
    const idx = state.volumes.findIndex(x => x.Name === volume.Name);
    if (idx < 0) {
      return;
    }
    state.volumes.splice(idx, 1);
  },
  setLoading(state, loading) {
    state.isLoading = loading;
  }
};

const actions = {
  async _readVolumes({ commit }) {
    commit("setLoading", true);
    try {
      const items = await readResourcePages("/resources/volumes/");
      commit("setVolumes", items);
      return items;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      throw error;
    } finally {
      commit("setLoading", false);
    }
  },
  async readVolumes({ commit }) {
    commit("setLoading", true);
    try {
      const items = await readResourcePages("/resources/volumes/");
      commit("setVolumes", items);
      return items;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  readVolume({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/volumes/${id}`;
    return axios
      .get(url)
      .then(response => {
        const volume = response.data;
        commit("setVolume", volume);
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
      })
      .finally(() => {
        commit("setLoading", false);
      });
  },
  async writeVolume({ commit, dispatch }, payload) {
    commit("setLoading", true);
    try {
      await axios.post("/resources/volumes/", payload);
      await dispatch("readVolumes");
      await router.push({ name: "Volumes" });
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  deleteVolume({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/volumes/${id}`;
    return axios
      .delete(url)
      .then(response => {
        const volume = response.data;
        commit("removeVolume", volume);
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
  getVolumeByName(state) {
    return Name => {
      return state.volumes.find(x => x.Name == Name);
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

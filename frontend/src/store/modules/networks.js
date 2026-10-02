import axios from "axios";
import router from "@/router/index";
import { readResourcePages } from "@/utils/resourcePages";

const state = {
  networks: [],
  isLoading: false
};

const mutations = {
  setNetworks(state, networks) {
    state.networks = networks;
  },
  setNetwork(state, network) {
    const idx = state.networks.findIndex(x => x.Id === network.Id);
    if (idx < 0) {
      state.networks.push(network);
    } else {
      state.networks.splice(idx, 1, network);
    }
  },
  addNetwork(state, network) {
    state.networks.push(network);
  },
  removeNetwork(state, network) {
    const idx = state.networks.findIndex(x => x.Id === network.Id);
    if (idx < 0) {
      return;
    }
    state.networks.splice(idx, 1);
  },
  setLoading(state, loading) {
    state.isLoading = loading;
  }
};

const actions = {
  async _readNetworks({ commit }) {
    commit("setLoading", true);
    try {
      const items = await readResourcePages("/resources/networks/");
      commit("setNetworks", items);
      return items;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      throw error;
    } finally {
      commit("setLoading", false);
    }
  },
  async readNetworks({ commit }) {
    commit("setLoading", true);
    try {
      const items = await readResourcePages("/resources/networks/");
      commit("setNetworks", items);
      return items;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  readNetwork({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/networks/${id}`;
    return axios
      .get(url)
      .then(response => {
        const network = response.data;
        commit("setNetwork", network);
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
      })
      .finally(() => {
        commit("setLoading", false);
      });
  },
  async writeNetwork({ commit, dispatch }, payload) {
    commit("setLoading", true);
    try {
      await axios.post("/resources/networks/", payload);
      await dispatch("readNetworks");
      await router.push({ name: "Networks" });
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
    }
  },
  deleteNetwork({ commit }, id) {
    commit("setLoading", true);
    const url = `/resources/networks/${id}`;
    return axios
      .delete(url)
      .then(response => {
        const network = response.data;
        commit("removeNetwork", network);
        return true;
      })
      .catch(err => {
        commit("snackbar/setErr", err, { root: true });
        return false;
      })
      .finally(() => { commit("setLoading", false); });
  }
};

const getters = {
  getNetworkById(state) {
    return Id => {
      return state.networks.find(x => x.Id == Id);
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

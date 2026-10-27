import axios from "axios";
import { runTrackedOperation } from "@/utils/operations";

const state = {
  apps: [],
  updatable: [],
  logs: [],
  processes: [],
  isLoading: false,
  isLoadingValue: null,
  action: ""
};

const mutations = {
  setApps(state, apps) {
    state.apps = apps;
  },
  setApp(state, app) {
    const name = app.name || app.Name?.replace(/^\//, "");
    const idx = state.apps.findIndex(x => (app.Id && x.Id === app.Id) ||
      (name && (x.name || x.Name?.replace(/^\//, "")) === name));
    if (idx < 0) {
      state.apps.push(app);
    } else {
      state.apps.splice(idx, 1, app);
    }
  },
  setAppProcesses(state, processes) {
    state.processes = processes;
  },
  setAppLogs(state, logs) {
    state.logs = logs;
  },
  setLoading(state, loading) {
    state.isLoading = loading;
  },
  setLoadingItems(state) {
    state.isLoadingValue = 0;
  },
  setLoadingItemCompleted(state, total) {
    let quotent = 1 / total;
    let increment = quotent * 100;
    state.isLoadingValue += increment;
  },
  setLoadingComplete(state) {
    state.isLoadingValue = null;
  },
  setAction(state, action) {
    state.action = action;
  },
  setUpdatable(state, updatable) {
    state.updatable = updatable;
  },
  setUpdated(state, updated) {
    const index = state.updatable.indexOf(updated);
    // F26: guard against index -1 (would remove the last element).
    if (index !== -1) state.updatable.splice(index, 1);
  }
};

const actions = {
  async readApps({ commit }) {
    await commit("setLoading", true);
    await commit("setAction", "Getting Apps ...");
    const url = "/apps/";
    return axios
      .get(url)
      .then(response => {
        var apps = response.data;
        commit("setApps", apps);
        return true;
      })
      .catch(err => {
        console.error(
          "Failed to load apps: " +
            (err.response?.data?.detail || err.message)
        );
        commit("snackbar/setErr", err, { root: true });
        return false;
      })
      .finally(() => {
        commit("setLoading", false);
        commit("setAction", "");
      });
  },
  async checkAppUpdate({ commit }, apps) {
    commit("setLoading", true);
    commit("setLoadingItems");
    commit("setAction", "Checking for updates...");
    try {
      await Promise.all(
        apps.map(async _app => {
          let url = `/apps/${_app.name}/updates`;
          try {
            const response = await axios.get(url);
            let app = response.data;
            commit("setLoadingItemCompleted", apps.length);
            commit("setApp", app);
          } catch (err) {
            console.error("Failed to check updates for " + _app.name);
            commit("snackbar/setErr", err, { root: true });
          }
        })
      );
      console.log("Update check completed");
    } finally {
      commit("setLoading", false);
      commit("setAction", "");
    }
  },
  readApp({ commit }, Name) {
    const url = `/apps/${Name}`;
    commit("setLoading", true);
    return new Promise((resolve, reject) => {
      axios
        .get(url)
        .then(response => {
          const app = response.data;
          commit("setApp", app);
          resolve(app);
        })
        .catch(err => {
          console.error("Failed to read app " + Name);
          commit("snackbar/setErr", err, { root: true });
          reject(err);
        })
        .finally(() => {
          commit("setLoading", false);
        });
    });
  },
  async readAppProcesses({ commit }, Name) {
    const url = `/apps/${Name}/processes`;
    try {
      let response = await axios.get(url);
      if (response) {
        const processes = response.data;
        commit("setAppProcesses", processes);
      }
    } catch (err) {
      console.error("Failed to read processes for " + Name);
    }
  },
  async readAppLogs({ commit }, Name) {
    let url = `/apps/${Name}/logs`;
    axios
      .get(url)
      .then(response => {
        let logs = [];
        let _log = response.data.logs;
        let split_log = _log.split("\n");
        split_log.forEach(element => {
          logs.push(element);
        });
        commit("setAppLogs", logs);
        console.log("Logs downloaded for " + Name);
      })
      .catch(err => {
        console.error("Failed to download logs for " + Name);
        commit("snackbar/setErr", err, { root: true });
      });
  },
  async AppUpdate({ commit, dispatch }, Name) {
    commit("setLoading", true);
    commit("setAction", `Updating ${Name}…`);
    try {
      await runTrackedOperation(axios, { kind: "container.action", resource: Name, action: "update" }, {
        onUpdate: task => commit("setAction", task.phase),
      });
      await dispatch("readApps");
      commit("setUpdated", Name);
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
      commit("setAction", "");
    }
  },
  async AppAction({ commit, dispatch }, { Name, Action }) {
    commit("setLoading", true);
    commit("setAction", `${Action} ${Name}…`);
    try {
      await runTrackedOperation(axios, { kind: "container.action", resource: Name, action: Action }, {
        onUpdate: task => commit("setAction", task.phase),
      });
      await dispatch("readApps");
      if (Action === "update") commit("setUpdated", Name);
      return true;
    } catch (error) {
      commit("snackbar/setErr", error, { root: true });
      return false;
    } finally {
      commit("setLoading", false);
      commit("setAction", "");
    }
  }
};

const getters = {
  getAppByName(state) {
    return Name => {
      Name = "/" + Name;
      return state.apps.find(x => x.Name == Name);
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

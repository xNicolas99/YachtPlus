import { afterEach, describe, expect, it, vi } from "vitest";
import * as Vue from "vue";
import { createStore } from "vuex";
import ProjectDetails from "./ProjectDetails.vue";
import detailsSource from "./ProjectDetails.vue?raw";
import ProjectList from "./ProjectList.vue";
import listSource from "./ProjectList.vue?raw";

const apps = [];
function remove(node) {
  const index = node.parent?.children.indexOf(node);
  if (index >= 0) node.parent.children.splice(index, 1);
  node.parent = null;
}
const renderer = Vue.createRenderer({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: "text", text }),
  createComment: text => ({ type: "comment", text }),
  setText: (node, text) => { node.text = text; },
  setElementText: (node, text) => { node.text = text; node.children = []; },
  patchProp: (node, key, previous, value) => { node.props[key] = value; },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1],
  insert(node, parent, anchor) {
    if (node.parent) remove(node);
    node.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node);
  },
  remove
});

function mount({ list = false, projects = [], loading = false, action = vi.fn().mockResolvedValue(true) } = {}) {
  const read = vi.fn().mockResolvedValue();
  const readApps = vi.fn().mockResolvedValue();
  const store = createStore({ modules: {
    projects: {
      namespaced: true,
      state: () => ({ projects, isLoading: loading, action: "" }),
      getters: { getProjectByName: state => name => state.projects.find(project => project.name === name) },
      actions: { readProject: read, readProjects: read, ProjectAction: action, ProjectAppAction: vi.fn() }
    },
    apps: { namespaced: true, state: () => ({ apps: [] }), actions: { readApps } },
    snackbar: { namespaced: true, mutations: { setErr: vi.fn() } }
  } });
  const source = list ? listSource : detailsSource;
  const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
  const app = renderer.createApp({ ...(list ? ProjectList : ProjectDetails), render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const name of [
    "VCard", "VCardTitle", "VCardSubtitle", "VCardText", "VCardActions", "VSpacer",
    "VRow", "VCol", "VBtn", "VMenu", "VIcon", "VList", "VListItem", "VListItemTitle",
    "VFadeTransition", "VProgressLinear", "VAlert", "VDivider", "VTable", "VDataTable",
    "VExpansionPanels", "VExpansionPanel", "VExpansionPanelTitle", "VExpansionPanelText", "VItemGroup",
    "VTooltip", "VTextField", "VListGroup", "VChip"
  ]) {
    app.component(name, { setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.()) });
  }
  app.component("VDialog", {
    props: ["modelValue"],
    setup: (props, { attrs, slots }) => () => Vue.h("VDialog", { ...attrs, modelValue: props.modelValue }, props.modelValue ? slots.default?.() : [])
  });
  app.use(store);
  const router = { push: vi.fn().mockResolvedValue() };
  const route = Vue.reactive({ params: { projectName: "demo" } });
  app.config.globalProperties.$route = route;
  app.config.globalProperties.$router = router;
  const root = { children: [] };
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [
    ...(node.type === type ? [node] : []),
    ...(node.children || []).flatMap(child => nodes(type, child))
  ];
  const text = (node = root) => [node.text || "", ...(node.children || []).map(text)].join(" ");
  return { vm, store, read, readApps, action, router, route, nodes, text };
}

afterEach(() => apps.splice(0).forEach(app => app.unmount()));

describe("Compose project details", () => {
  it("renders a direct visit while the project loads, then shows the response", async () => {
    const mounted = mount({ loading: true });
    expect(mounted.nodes("VProgressLinear")).toHaveLength(1);
    expect(mounted.nodes("VCard")).toHaveLength(0);
    expect(mounted.read).toHaveBeenCalledWith(expect.anything(), "demo");
    mounted.store.state.projects.projects = [{ name: "demo", services: {} }];
    mounted.store.state.projects.isLoading = false;
    await Vue.nextTick();
    expect(mounted.text()).toContain("Stack details");
    expect(mounted.nodes("VAlert")).toHaveLength(0);
  });

  it("shows unavailable data safely after a failed request", async () => {
    const mounted = mount({ loading: true });
    mounted.store.state.projects.isLoading = false;
    await Vue.nextTick();
    expect(mounted.text()).toContain("Stack details are unavailable");
    expect(mounted.nodes("VCard")).toHaveLength(0);
  });

  it("loads the selected project when route parameters change", async () => {
    const mounted = mount();
    mounted.route.params.projectName = "other";
    await Vue.nextTick();
    expect(mounted.read).toHaveBeenLastCalledWith(expect.anything(), "other");
  });

  it("renders Compose mapping forms, long volume/port syntax and full environment values", () => {
    const mounted = mount({ projects: [{
      name: "demo", networks: ["private"], volumes: ["data"], services: {
        web: {
          image: "example/web", depends_on: { db: { condition: "service_healthy" } },
          networks: { private: null, frontend: { aliases: ["web"] } },
          ports: [{ target: 80, published: "8080", protocol: "tcp" }],
          volumes: [{ type: "volume", source: "data", target: "/app/data" }, "/cache"],
          environment: ["QUERY=one=two", "FROM_HOST"],
          labels: { "com.example.enabled": true, "com.example.count": 0 }
        }
      }
    }] });
    expect(mounted.text()).toContain("db");
    expect(mounted.text()).toContain("8080:80/tcp");
    expect(mounted.text()).toContain("/app/data");
    expect(mounted.text()).toContain("/cache");
    expect(mounted.text()).toContain("one=two");
    expect(mounted.text()).toContain("FROM_HOST");
    expect(mounted.text()).toContain("com.example.enabled");
    expect(mounted.text()).toContain("true");
    expect(mounted.text()).toContain("com.example.count");
  });

  it("renders list-form labels and mapping-form environment values", () => {
    const mounted = mount({ projects: [{ name: "demo", services: {
      web: { labels: ["query=one=two", "flag"], environment: { EMPTY: "", COUNT: 0 }, depends_on: ["db"], networks: ["private"] }
    } }] });
    expect(mounted.text()).toContain("one=two");
    expect(mounted.text()).toContain("flag");
    expect(mounted.text()).toContain("EMPTY");
    expect(mounted.text()).toContain("COUNT");
    expect(mounted.text()).toContain("db");
    expect(mounted.text()).toContain("private");
    expect(mounted.text()).not.toContain("0, private");
    expect(mounted.text().match(/private/g)).toHaveLength(1);
  });
});

describe.each([false, true])("Compose deletion (list=%s)", list => {
  it.each([false, true])("waits for the result, prevents duplicate deletion and closes only on success (%s)", async success => {
    let resolve;
    const action = vi.fn().mockReturnValue(new Promise(done => { resolve = done; }));
    const mounted = mount({ list, action, projects: [{ name: "demo", services: {} }] });
    mounted.vm.selectedProject = { name: "demo" };
    mounted.vm.deleteDialog = true;
    const pending = mounted.vm.confirmDelete();
    await Vue.nextTick();
    expect(mounted.nodes("VDialog")[0].props.persistent).toBe(true);
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(true);
    await mounted.vm.confirmDelete();
    expect(action).toHaveBeenCalledOnce();
    expect(mounted.vm.deleteDialog).toBe(true);
    resolve(success);
    await pending;
    expect(mounted.vm.deleteDialog).toBe(!success);
    expect(mounted.vm.deleting).toBe(false);
    if (success && !list) expect(mounted.router.push).toHaveBeenCalledWith({ name: "View Projects" });
    else expect(mounted.router.push).not.toHaveBeenCalled();
  });

  it("retains confirmation and reports unexpected rejection", async () => {
    const error = new Error("request failed");
    const mounted = mount({ list, action: vi.fn().mockRejectedValue(error) });
    const commit = vi.spyOn(mounted.store, "commit");
    mounted.vm.selectedProject = { name: "demo" };
    mounted.vm.deleteDialog = true;
    await mounted.vm.confirmDelete();
    expect(commit).toHaveBeenCalledWith("snackbar/setErr", error);
    expect(mounted.vm.deleteDialog).toBe(true);
    expect(mounted.vm.deleting).toBe(false);
  });
});

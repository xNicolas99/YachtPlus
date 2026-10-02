import { afterEach, describe, expect, it, vi } from "vitest";
import * as Vue from "vue";
import { createStore } from "vuex";
import ImageDetails from "./images/ImageDetails.vue";
import imageSource from "./images/ImageDetails.vue?raw";
import NetworkDetails from "./networks/NetworkDetails.vue";
import networkSource from "./networks/NetworkDetails.vue?raw";
import VolumeDetails from "./volumes/VolumeDetails.vue";
import volumeSource from "./volumes/VolumeDetails.vue?raw";

const resources = [
  { kind: "image", module: "images", component: ImageDetails, source: imageSource,
    getter: "getImageById", read: "readImage", remove: "deleteImage", route: "Images",
    params: { imageid: "sha256:123" }, identity: "sha256:123", data: { Id: "sha256:123" } },
  { kind: "network", module: "networks", component: NetworkDetails, source: networkSource,
    getter: "getNetworkById", read: "readNetwork", remove: "deleteNetwork", route: "Networks",
    params: { networkid: "network-id" }, identity: "network-id", data: { Id: "network-id", Name: "private" } },
  { kind: "volume", module: "volumes", component: VolumeDetails, source: volumeSource,
    getter: "getVolumeByName", read: "readVolume", remove: "deleteVolume", route: "Volumes",
    params: { volumeName: "data" }, identity: "data", data: { Name: "data" } }
];

// Render real templates against a reactive Vuex store, with presentation-only
// Vuetify stubs. Host nodes expose events without requiring a DOM dependency.
const apps = [];
function removeNode(node) {
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
    if (node.parent) removeNode(node);
    node.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, node);
  },
  remove: removeNode
});

function mountDetails(spec, options = {}) {
  const resource = Object.prototype.hasOwnProperty.call(options, "resource") ? options.resource : spec.data;
  const { loading = false, remove = vi.fn().mockResolvedValue(true) } = options;
  const root = { children: [] };
  const read = vi.fn().mockResolvedValue();
  const store = createStore({ modules: { [spec.module]: {
    namespaced: true,
    state: () => ({ resource, isLoading: loading }),
    getters: { [spec.getter]: state => () => state.resource },
    actions: { [spec.read]: read, [spec.remove]: remove }
  } } });
  const render = Vue.compile(spec.source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
  const app = renderer.createApp({ ...spec.component, render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const name of [
    "VCard", "VCardTitle", "VCardSubtitle", "VCardText", "VCardActions", "VSpacer",
    "VBtn", "VMenu", "VIcon", "VList", "VListItem", "VListItemTitle", "VChip",
    "VFadeTransition", "VProgressLinear", "VTable", "VDataTable", "VAlert"
  ]) {
    app.component(name, {
      inheritAttrs: false,
      setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.())
    });
  }
  app.component("VDialog", {
    props: ["modelValue"],
    setup: (props, { attrs, slots }) => () => Vue.h("VDialog", { ...attrs, modelValue: props.modelValue }, props.modelValue ? slots.default?.() : [])
  });
  const router = { push: vi.fn().mockResolvedValue() };
  app.use(store);
  app.config.globalProperties.$route = { params: spec.params };
  app.config.globalProperties.$router = router;
  app.config.globalProperties.$formatDate = value => value || "";
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [
    ...(node.type === type ? [node] : []),
    ...(node.children || []).flatMap(child => nodes(type, child))
  ];
  const text = (node = root) => [node.text || "", ...(node.children || []).map(text)].join(" ");
  return { vm, nodes, text, read, remove, router, store };
}

afterEach(() => apps.splice(0).forEach(app => app.unmount()));

describe.each(resources)("$kind details", spec => {
  it("renders a direct visit before inspect data arrives and renders the loaded data", async () => {
    const mounted = mountDetails(spec, { resource: undefined, loading: true });
    expect(mounted.nodes("VProgressLinear")).toHaveLength(1);
    expect(mounted.read).toHaveBeenCalledWith(expect.anything(), spec.identity);
    expect(mounted.nodes("VDialog")).toHaveLength(0);
    mounted.store.state[spec.module].resource = spec.data;
    mounted.store.state[spec.module].isLoading = false;
    await Vue.nextTick();
    expect(mounted.nodes("VCard").length).toBeGreaterThan(0);
    expect(mounted.nodes("VAlert")).toHaveLength(0);
  });

  it("shows an unavailable state if inspect fails without enabling destructive actions", async () => {
    const mounted = mountDetails(spec, { resource: null, loading: true });
    mounted.store.state[spec.module].isLoading = false;
    await Vue.nextTick();
    expect(mounted.nodes("VAlert")).toHaveLength(1);
    expect(mounted.text()).toContain("details are unavailable");
    expect(mounted.nodes("VListItem")).toHaveLength(0);
  });

  it.each([false, true])("requires confirmation and returns to the list only on success (%s)", async success => {
    const mounted = mountDetails(spec, { remove: vi.fn().mockResolvedValue(success) });
    expect(mounted.vm.deleteDialog).toBe(false);
    mounted.nodes("VListItem")[0].props.onClick();
    await Vue.nextTick();
    expect(mounted.remove).not.toHaveBeenCalled();
    expect(mounted.nodes("VDialog")[0].props.modelValue).toBe(true);
    const buttons = mounted.nodes("VBtn");
    await buttons.at(-1).props.onClick();
    await Vue.nextTick();
    expect(mounted.remove).toHaveBeenCalledWith(expect.anything(), spec.identity);
    expect(mounted.vm.deleteDialog).toBe(!success);
    expect(mounted.vm.deleting).toBe(false);
    if (success) expect(mounted.router.push).toHaveBeenCalledWith({ name: spec.route });
    else expect(mounted.router.push).not.toHaveBeenCalled();
  });

  it("supports cancelling deletion without making a request", async () => {
    const mounted = mountDetails(spec);
    mounted.nodes("VListItem")[0].props.onClick();
    await Vue.nextTick();
    mounted.nodes("VBtn").at(-2).props.onClick();
    await Vue.nextTick();
    expect(mounted.vm.deleteDialog).toBe(false);
    expect(mounted.remove).not.toHaveBeenCalled();
  });

  it("keeps confirmation open while deletion is pending and prevents duplicate requests", async () => {
    let resolveRequest;
    const request = new Promise(resolve => { resolveRequest = resolve; });
    const mounted = mountDetails(spec, { remove: vi.fn().mockReturnValue(request) });
    mounted.vm.deleteDialog = true;
    const pending = mounted.vm.confirmDelete();
    await Vue.nextTick();
    expect(mounted.nodes("VDialog")[0].props.persistent).toBe(true);
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(true);
    await mounted.vm.confirmDelete();
    expect(mounted.remove).toHaveBeenCalledOnce();
    expect(mounted.vm.deleteDialog).toBe(true);
    expect(mounted.router.push).not.toHaveBeenCalled();
    resolveRequest(false);
    await pending;
    expect(mounted.vm.deleteDialog).toBe(true);
    expect(mounted.vm.deleting).toBe(false);
  });

  it("keeps the dialog open and reports an unexpected deletion rejection", async () => {
    const error = new Error("request rejected");
    const mounted = mountDetails(spec, { remove: vi.fn().mockRejectedValue(error) });
    const commit = vi.spyOn(mounted.store, "commit").mockImplementation(() => {});
    mounted.vm.deleteDialog = true;
    await mounted.vm.confirmDelete();
    expect(commit).toHaveBeenCalledWith("snackbar/setErr", error);
    expect(mounted.vm.deleteDialog).toBe(true);
    expect(mounted.vm.deleting).toBe(false);
    expect(mounted.router.push).not.toHaveBeenCalled();
  });

  it("still navigates after a successful delete removes the resource from the store", async () => {
    const remove = vi.fn(async ({ state }) => { state.resource = undefined; return true; });
    const mounted = mountDetails(spec, { remove });
    mounted.vm.deleteDialog = true;
    await mounted.vm.confirmDelete();
    await Vue.nextTick();
    expect(mounted.router.push).toHaveBeenCalledWith({ name: spec.route });
    expect(mounted.vm.deleteDialog).toBe(false);
  });
});

describe("Docker inspect data compatibility", () => {
  it("renders modern image Config and tolerates null tags, digests and missing virtual size", () => {
    const mounted = mountDetails(resources[0], { resource: {
      Id: "sha256:123", RepoTags: null, RepoDigests: null, Size: 2048,
      Config: {
        Cmd: ["serve", "--port", "80"], Entrypoint: ["/entrypoint", "--quiet"],
        ExposedPorts: { "80/tcp": {} }, Labels: { owner: "team" }, Env: ["MODE=production"]
      }
    } });
    expect(mounted.text()).toContain("serve --port 80");
    expect(mounted.text()).toContain("/entrypoint --quiet");
    expect(mounted.text()).toContain("80/tcp");
    expect(mounted.text()).toContain("owner");
    expect(mounted.text()).toContain("MODE=production");
    expect(mounted.text()).toContain("2 KB");
    expect(mounted.text()).not.toContain("NaN");
  });

  it("supports legacy image ContainerConfig when Config is absent", () => {
    const mounted = mountDetails(resources[0], { resource: {
      Id: "sha256:123", ContainerConfig: { Cmd: ["legacy", "run"] }
    } });
    expect(mounted.text()).toContain("legacy run");
  });

  it.each([undefined, null, {}, { Config: null }, { Config: [] }, { Config: [null] }])("renders empty network IPAM without crashing (%j)", IPAM => {
    const mounted = mountDetails(resources[1], { resource: {
      Id: "network-id", Name: "host", IPAM, Labels: null, Options: null, Containers: null
    } });
    expect(mounted.text()).toContain("IPV4 Subnet");
    expect(mounted.nodes("VDataTable")[0].props.items).toEqual([]);
  });

  it("renders network address data and a single label", () => {
    const mounted = mountDetails(resources[1], { resource: {
      Id: "network-id", Name: "private", IPAM: { Config: [{ Subnet: "10.1.0.0/24", Gateway: "10.1.0.1" }] },
      Labels: { owner: "team" }, Containers: { containerID: { Name: "web" } }
    } });
    expect(mounted.text()).toContain("10.1.0.0/24");
    expect(mounted.text()).toContain("10.1.0.1");
    expect(mounted.text()).toContain("owner");
    expect(mounted.nodes("VDataTable")[0].props.items).toEqual([{ Name: "web" }]);
  });
});

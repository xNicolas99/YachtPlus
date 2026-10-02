import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as Vue from "vue";
import axios from "axios";
import NetworkAccessSecurity from "./NetworkAccessSecurity.vue";
import source from "./NetworkAccessSecurity.vue?raw";

vi.mock("axios", () => ({ default: { get: vi.fn(), put: vi.fn() } }));

// Exercise the compiled template and real Vue reactivity with presentation
// stubs, matching the repo's renderer-based component tests.
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
const state = (overrides = {}) => ({
  allow_public: false,
  local_networks: ["127.0.0.0/8", "192.168.0.0/16"],
  fail2ban: { required: true, active: true },
  can_modify: true,
  ...overrides
});
function mount() {
  const root = { children: [] };
  const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
  const app = renderer.createApp({ ...NetworkAccessSecurity, render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const name of ["VCard", "VToolbar", "VToolbarTitle", "VCardText", "VProgressLinear", "VAlert", "VCheckbox", "VCardActions", "VBtn", "VSpacer", "VDialog", "VCardTitle"]) {
    app.component(name, {
      inheritAttrs: false,
      setup: (_, { attrs, slots }) => () => Vue.h(name, attrs,
        name === "VDialog" && !attrs.modelValue ? [] : slots.default?.())
    });
  }
  const vm = app.mount(root);
  apps.push(app);
  const all = (node = root) => [node, ...(node.children || []).flatMap(all)];
  const find = id => all().find(node => node.props?.["data-testid"] === id);
  const text = () => all().filter(node => node.type !== "comment").map(node => node.text || "").join(" ");
  return { vm, find, text, all };
}
async function settle() {
  await Promise.resolve();
  await Vue.nextTick();
  await Promise.resolve();
  await Vue.nextTick();
}
async function change(mounted, id, value) {
  mounted.find(id).props["onUpdate:modelValue"](value);
  await settle();
}
async function click(mounted, id) {
  mounted.find(id).props.onClick();
  await settle();
}
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => vi.resetAllMocks());
afterEach(() => apps.splice(0).forEach(app => app.unmount()));

describe("network access security", () => {
  it("keeps unknown policy disabled while loading, then displays backend state", async () => {
    const request = deferred();
    axios.get.mockReturnValueOnce(request.promise);
    const mounted = mount();
    expect(axios.get).toHaveBeenCalledWith("/settings/security");
    expect(mounted.find("policy-unknown")).toBeDefined();
    expect(mounted.find("public-access")).toBeUndefined();
    expect(mounted.find("save-security").props.disabled).toBe(true);
    await mounted.vm.requestSave();
    expect(axios.put).not.toHaveBeenCalled();
    request.resolve({ data: state({ allow_public: true }) });
    await settle();
    expect(mounted.text()).toContain("Public access enabled");
    expect(mounted.find("public-access").props["model-value"]).toBe(true);
  });

  it.each(["offline", "permission", "invalid"])("shows unavailable policy after %s fetch failure and supports Retry", async failure => {
    if (failure === "invalid") axios.get.mockResolvedValueOnce({ data: {} });
    else axios.get.mockRejectedValueOnce(failure === "permission" ? { response: { status: 403, data: { detail: "Superuser access required" } } } : new Error("offline"));
    const mounted = mount();
    await settle();
    expect(mounted.find("policy-unknown")).toBeDefined();
    expect(mounted.find("public-access")).toBeUndefined();
    expect(mounted.find("save-security").props.disabled).toBe(true);
    if (failure === "permission") expect(mounted.text()).toContain("Superuser access required");
    axios.get.mockResolvedValueOnce({ data: state() });
    mounted.all().find(node => node.type === "VBtn" && node.props.onClick === mounted.vm.fetchSettings).props.onClick();
    await settle();
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(mounted.find("policy-unknown")).toBeUndefined();
    expect(mounted.text()).toContain("Local networks only");
  });

  it("requires dialog acknowledgement, keeps unsaved policy distinct and blocks duplicate submits", async () => {
    axios.get.mockResolvedValueOnce({ data: state() });
    const mounted = mount();
    await settle();
    await change(mounted, "public-access", true);
    expect(mounted.text()).toContain("Local networks only");
    expect(mounted.find("unsaved-policy")).toBeDefined();
    await click(mounted, "save-security");
    expect(axios.put).not.toHaveBeenCalled();
    expect(mounted.find("enable-public").props.disabled).toBe(true);
    await mounted.vm.saveSettings(true);
    expect(axios.put).not.toHaveBeenCalled();
    await change(mounted, "confirm-public", true);
    const request = deferred();
    axios.put.mockReturnValueOnce(request.promise);
    await click(mounted, "enable-public");
    expect(mounted.find("public-access").props.disabled).toBe(true);
    expect(mounted.find("enable-public").props.disabled).toBe(true);
    await mounted.vm.saveSettings(true);
    await mounted.vm.requestSave();
    await mounted.vm.fetchSettings();
    expect(axios.put).toHaveBeenCalledOnce();
    expect(axios.get).toHaveBeenCalledOnce();
    expect(axios.put).toHaveBeenCalledWith("/settings/security", { allow_public: true, confirm_public_access: true });
    request.resolve({ data: state({ allow_public: true }) });
    await settle();
    expect(mounted.text()).toContain("Public access enabled");
    expect(mounted.find("unsaved-policy")).toBeUndefined();
    expect(mounted.vm.confirmDialog).toBe(false);
  });

  it("retains backend policy and displays the reason when saving public access fails", async () => {
    axios.get.mockResolvedValueOnce({ data: state() });
    const mounted = mount();
    await settle();
    await change(mounted, "public-access", true);
    await click(mounted, "save-security");
    await change(mounted, "confirm-public", true);
    axios.put.mockRejectedValueOnce({ response: { data: { detail: "Local network connection required" } } });
    await click(mounted, "enable-public");
    expect(mounted.text()).toContain("Local networks only");
    expect(mounted.text()).toContain("Local network connection required");
    expect(mounted.text()).toContain("Refresh Status to verify whether the change was applied");
    expect(mounted.find("public-access").props["model-value"]).toBe(false);
    expect(mounted.find("save-security").props.disabled).toBe(true);
    expect(mounted.vm.publicConfirmed).toBe(false);
  });

  it("saves local-only access without a public confirmation", async () => {
    axios.get.mockResolvedValueOnce({ data: state({ allow_public: true }) });
    axios.put.mockResolvedValueOnce({ data: state() });
    const mounted = mount();
    await settle();
    await change(mounted, "public-access", false);
    await click(mounted, "save-security");
    expect(axios.put).toHaveBeenCalledWith("/settings/security", { allow_public: false, confirm_public_access: false });
    expect(mounted.text()).toContain("Local networks only");
  });

  it("keeps access read-only for an administrator outside the local networks", async () => {
    axios.get.mockResolvedValueOnce({ data: state({ allow_public: true, can_modify: false }) });
    const mounted = mount();
    await settle();
    expect(mounted.find("public-access").props.disabled).toBe(true);
    expect(mounted.text()).toContain("Connect from a local network");
    await change(mounted, "public-access", false);
    await mounted.vm.requestSave();
    expect(mounted.vm.draftAllowPublic).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("shows unavailable protection conspicuously and prevents enabling public access", async () => {
    axios.get.mockResolvedValueOnce({ data: state({ fail2ban: { required: true, active: false } }) });
    const mounted = mount();
    await settle();
    expect(mounted.find("fail2ban-status").props.type).toBe("error");
    expect(mounted.text()).toContain("Fail2ban protection is not ready");
    expect(mounted.find("public-access").props.disabled).toBe(true);
    await change(mounted, "public-access", true);
    await mounted.vm.requestSave();
    expect(mounted.find("save-security").props.disabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("cancels confirmation without saving and requires fresh acknowledgement on reopen", async () => {
    axios.get.mockResolvedValueOnce({ data: state() });
    const mounted = mount();
    await settle();
    await change(mounted, "public-access", true);
    await click(mounted, "save-security");
    await change(mounted, "confirm-public", true);
    mounted.vm.cancelConfirmation();
    await settle();
    await click(mounted, "save-security");
    expect(mounted.find("enable-public").props.disabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("displays optional startup protection accurately and refreshes an ambiguous failed save", async () => {
    axios.get.mockResolvedValueOnce({ data: state({ fail2ban: { required: false, active: true } }) });
    const mounted = mount();
    await settle();
    expect(mounted.text()).toContain("does not require protection at startup");
    expect(mounted.text()).not.toContain("Protection is required");
    await change(mounted, "public-access", true);
    await click(mounted, "save-security");
    await change(mounted, "confirm-public", true);
    axios.put.mockRejectedValueOnce(new Error("Connection lost after server applied change"));
    await click(mounted, "enable-public");
    expect(mounted.text()).toContain("Refresh Status to verify whether the change was applied");
    expect(mounted.text()).toContain("Local networks only");
    axios.get.mockResolvedValueOnce({ data: state({ allow_public: true }) });
    await mounted.vm.fetchSettings();
    await settle();
    expect(mounted.text()).toContain("Public access enabled");
    expect(mounted.vm.saveError).toBe("");
  });
});

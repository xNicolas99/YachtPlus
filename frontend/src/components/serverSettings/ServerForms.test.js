import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as Vue from "vue";
import { defineRule } from "vee-validate";
import { required } from "@vee-validate/rules";
import axios from "axios";
import NetworkForm from "../resources/networks/NetworkForm.vue";
import networkSource from "../resources/networks/NetworkForm.vue?raw";
import ServerInfo from "./ServerInfo.vue";
import infoSource from "./ServerInfo.vue?raw";
import ServerVariables from "./ServerVariables.vue";
import variablesSource from "./ServerVariables.vue?raw";

vi.mock("axios", () => ({ default: Object.assign(vi.fn(), { post: vi.fn() }) }));
defineRule("required", required);

// Keep the real Form/Field validation and compiled template. Only presentation
// components use host nodes, allowing their modelValue events to be exercised
// without adding a DOM or test utility dependency.
const mountedApps = [];
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

function mountForm(component, source, { variables = [], dispatch } = {}) {
  const root = { children: [] };
  const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1], {
    isCustomElement: tag => tag === "transition-group"
  });
  const app = renderer.createApp({ ...component, render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const name of [
    "VCard", "VToolbar", "VToolbarTitle", "VSpacer", "VCardTitle", "VCardText",
    "VCardActions", "VRow", "VCol", "VTextField", "VFileInput", "VSelect",
    "VCheckbox", "VBtn", "VIcon", "VSnackbar", "VFadeTransition",
    "VProgressLinear"
  ]) {
    app.component(name, {
      inheritAttrs: false,
      setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.())
    });
  }
  const router = { push: vi.fn().mockResolvedValue() };
  const commit = vi.fn();
  app.config.globalProperties.$router = router;
  app.config.globalProperties.$store = {
    commit,
    dispatch: dispatch || vi.fn().mockResolvedValue(variables)
  };
  const vm = app.mount(root);
  mountedApps.push(app);
  const nodes = (type, node = root) => [
    ...(node.type === type ? [node] : []),
    ...(node.children || []).flatMap(child => nodes(type, child))
  ];
  return { vm, nodes, router, commit };
}

async function settle() {
  await Vue.nextTick();
  await new Promise(resolve => setTimeout(resolve, 15));
  await Vue.nextTick();
}

async function change(node, value) {
  node.props["onUpdate:modelValue"](value);
  await settle();
}

async function submit(mounted) {
  await mounted.nodes("form")[0].props.onSubmit({ preventDefault() {}, stopPropagation() {} });
  await settle();
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  mountedApps.splice(0).forEach(app => app.unmount());
  vi.unstubAllGlobals();
});

describe("network creation form", () => {
  it("validates required fields and posts every entered bridge/IP value to the API base path", async () => {
    const mounted = mountForm(NetworkForm, networkSource);
    await settle();
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(true);
    await submit(mounted);
    expect(axios.post).not.toHaveBeenCalled();

    await change(mounted.nodes("VTextField")[0], "private-net");
    await change(mounted.nodes("VSelect")[0], "bridge");
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(false);
    const ipValues = ["10.0.2.0/24", "10.0.2.1", "10.0.2.128/25", "2001:db8::/64", "2001:db8::1", "2001:db8::/80"];
    await change(mounted.nodes("VCheckbox")[0], true);
    await change(mounted.nodes("VCheckbox")[1], false);
    await change(mounted.nodes("VCheckbox")[2], true);
    for (const [index, value] of ipValues.entries()) {
      await change(mounted.nodes("VTextField")[index + 1], value);
    }
    axios.post.mockResolvedValueOnce({});
    await submit(mounted);

    expect(axios.post).toHaveBeenCalledWith("/resources/networks/", {
      name: "private-net", networkDriver: "bridge", network_devices: "",
      internal: true, attachable: false, ipv6_enabled: true,
      ipv4subnet: ipValues[0], ipv4gateway: ipValues[1], ipv4range: ipValues[2],
      ipv6subnet: ipValues[3], ipv6gateway: ipValues[4], ipv6range: ipValues[5]
    });
    expect(mounted.router.push).toHaveBeenCalledWith({ name: "Networks" });
    expect(mounted.vm.isLoading).toBe(false);
  });

  it("requires a macvlan interface only while that driver is selected", async () => {
    const mounted = mountForm(NetworkForm, networkSource);
    await change(mounted.nodes("VTextField")[0], "lan");
    await change(mounted.nodes("VSelect")[0], "macvlan");
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(true);
    await submit(mounted);
    expect(axios.post).not.toHaveBeenCalled();
    await change(mounted.nodes("VTextField")[1], "eth0");
    expect(mounted.vm.form.network_devices).toBe("eth0");
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(false);
    await change(mounted.nodes("VTextField")[1], "");
    await change(mounted.nodes("VSelect")[0], "ipvlan");
    expect(mounted.nodes("VBtn").at(-1).props.disabled).toBe(false);
  });

  it("keeps the form open after a failed create and lets Cancel return to the network list", async () => {
    const mounted = mountForm(NetworkForm, networkSource);
    await change(mounted.nodes("VTextField")[0], "lan");
    await change(mounted.nodes("VSelect")[0], "bridge");
    const error = new Error("Docker rejected the request");
    axios.post.mockRejectedValueOnce(error);
    await submit(mounted);
    expect(mounted.commit).toHaveBeenCalledWith("snackbar/setErr", error);
    expect(mounted.router.push).not.toHaveBeenCalled();
    expect(mounted.vm.isLoading).toBe(false);
    mounted.nodes("VBtn")[0].props.onClick();
    expect(mounted.router.push).toHaveBeenCalledWith({ name: "Networks" });
  });
});

describe("server settings import/export", () => {
  it.each([false, true])("validates file selection and uploads a File (array selection: %s)", async asArray => {
    const mounted = mountForm(ServerInfo, infoSource);
    await settle();
    expect(mounted.nodes("VBtn")[0].props.disabled).toBe(true);
    await submit(mounted);
    expect(axios.post).not.toHaveBeenCalled();
    const file = new File(['{"settings":{}}'], "export.json", { type: "application/json" });
    await change(mounted.nodes("VFileInput")[0], asArray ? [file] : file);
    expect(mounted.nodes("VBtn")[0].props.disabled).toBe(false);
    const response = { data: { detail: "Imported" } };
    axios.post.mockResolvedValueOnce(response);
    await submit(mounted);
    const [url, data] = axios.post.mock.calls[0];
    expect(url).toBe("/settings/export");
    expect(data.get("upload").name).toBe("export.json");
    expect(await data.get("upload").text()).toBe(await file.text());
    expect(mounted.commit).toHaveBeenCalledWith("snackbar/setSuccess", response);
  });

  it("reports import failures without emitting success", async () => {
    const error = new Error("invalid JSON");
    const context = { setErr: vi.fn(), setSuccess: vi.fn() };
    axios.post.mockRejectedValueOnce(error);
    await ServerInfo.methods.import_settings.call(context, new File(["bad"], "bad.json"));
    expect(context.setErr).toHaveBeenCalledWith(error);
    expect(context.setSuccess).not.toHaveBeenCalled();
  });

  it.each([false, true])("cleans up the download link and blob URL (click failure: %s)", async failClick => {
    const error = new Error("download blocked");
    const link = {
      setAttribute: vi.fn(), remove: vi.fn(),
      click: vi.fn(() => { if (failClick) throw error; })
    };
    const createObjectURL = vi.fn().mockReturnValue("blob:export");
    const revokeObjectURL = vi.fn();
    const appendChild = vi.fn();
    vi.stubGlobal("window", { URL: { createObjectURL, revokeObjectURL } });
    vi.stubGlobal("document", { createElement: vi.fn().mockReturnValue(link), body: { appendChild } });
    axios.mockResolvedValueOnce({ data: new Blob(["{}"], { type: "application/json" }) });
    const context = { setErr: vi.fn() };
    await ServerInfo.methods.export_settings.call(context);
    expect(link.setAttribute).toHaveBeenCalledWith("download", "export.json");
    expect(link.click).toHaveBeenCalledOnce();
    expect(link.remove).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
    if (failClick) expect(context.setErr).toHaveBeenCalledWith(error);
    else expect(context.setErr).not.toHaveBeenCalled();
  });

  it("reports an export request failure", async () => {
    const error = new Error("offline");
    const context = { setErr: vi.fn() };
    axios.mockRejectedValueOnce(error);
    await ServerInfo.methods.export_settings.call(context);
    expect(context.setErr).toHaveBeenCalledWith(error);
  });
});

describe("server template variables", () => {
  it("loads, validates and saves distinct rows, including removal of the first row", async () => {
    const original = [{ variable: "old", replacement: "/old" }];
    const dispatch = vi.fn().mockResolvedValue(original);
    const mounted = mountForm(ServerVariables, variablesSource, { dispatch });
    await settle();
    expect(mounted.nodes("VTextField")[0].props.modelValue).toBe("old");
    expect(mounted.nodes("VTextField")[1].props.modelValue).toBe("/old");
    await change(mounted.nodes("VTextField")[0], "edited");
    expect(original[0].variable).toBe("old");
    mounted.vm.addTemplateVariables();
    await settle();
    expect(mounted.nodes("VBtn").find(node => node.props.type === "submit").props.disabled).toBe(true);
    await submit(mounted);
    expect(dispatch).toHaveBeenCalledTimes(1);
    await change(mounted.nodes("VTextField")[2], "new");
    await change(mounted.nodes("VTextField")[3], "/new");
    mounted.vm.removeTemplateVariables(0);
    await settle();
    expect(mounted.nodes("VTextField")[0].props.modelValue).toBe("new");
    expect(mounted.nodes("VTextField")[1].props.modelValue).toBe("/new");
    expect(mounted.nodes("VBtn").find(node => node.props.type === "submit").props.disabled).toBe(false);
    await submit(mounted);
    expect(dispatch).toHaveBeenLastCalledWith("templates/writeTemplateVariables", [{ variable: "new", replacement: "/new" }]);
    expect(mounted.vm.saved).toBe(true);
  });

  it.each([false, true])("shows Saved only after the request succeeds (request failure: %s)", async fail => {
    let resolveRequest;
    let rejectRequest;
    const request = new Promise((resolve, reject) => { resolveRequest = resolve; rejectRequest = reject; });
    const context = {
      ...ServerVariables.data(), saved: true,
      form: { templateVariables: [{ variable: "dir", replacement: "/data" }] },
      writeTemplateVariables: vi.fn().mockReturnValue(request)
    };
    const pending = ServerVariables.methods.submitFormData.call(context);
    expect(context.saved).toBe(false);
    expect(context.isSaving).toBe(true);
    await ServerVariables.methods.submitFormData.call(context);
    expect(context.writeTemplateVariables).toHaveBeenCalledOnce();
    if (fail) rejectRequest(new Error("offline"));
    else resolveRequest([]);
    await pending;
    expect(context.saved).toBe(!fail);
    expect(context.isSaving).toBe(false);
  });
});

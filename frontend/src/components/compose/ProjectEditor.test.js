import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as Vue from "vue";
import axios from "axios";
import ProjectEditor from "./ProjectEditor.vue";
import editorSource from "./ProjectEditor.vue?raw";

vi.mock("axios", () => ({ default: { post: vi.fn() } }));
vi.mock("vue3-ace-editor", async () => {
  const { h } = await import("vue");
  return { VAceEditor: { props: ["value", "readonly"], setup: (props, { attrs }) => () => h("AceEditor", { ...props, ...attrs }) } };
});
vi.mock("ace-builds/src-noconflict/mode-yaml", () => ({}));
vi.mock("ace-builds/src-noconflict/theme-twilight", () => ({}));
vi.mock("ace-builds/src-noconflict/theme-textmate", () => ({}));

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
  remove,
});
function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const source = "services:\n  web:\n    image: nginx\n";
const preview = {
  name: "example", normalized_content: source + "    read_only: true\n", diff: "+    read_only: true\n",
  affected_services: [{ name: "web", change: "added" }], security_changes: [{ service: "web", fields: ["read_only"] }],
  warnings: [], preview_token: "a".repeat(64),
};
function mount({ name = "_", readProject = vi.fn().mockResolvedValue({ name: "example", content: source }) } = {}) {
  const render = Vue.compile(editorSource.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1]);
  const app = renderer.createApp({ ...ProjectEditor, render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  for (const tag of ["VCard", "VCardTitle", "VCardText", "VCardActions", "VProgressLinear", "VAlert", "VChip", "VTextField", "VBtn", "VSpacer", "VExpansionPanels", "VExpansionPanel", "VExpansionPanelText", "VCheckbox"])
    app.component(tag, { setup: (_, { attrs, slots }) => () => Vue.h(tag, attrs, slots.default?.()) });
  app.component("VDialog", { props: ["modelValue"], setup: (props, { slots }) => () => Vue.h("VDialog", { modelValue: props.modelValue }, props.modelValue ? slots.default?.() : []) });
  const route = Vue.reactive({ params: { projectName: name } });
  const commit = vi.fn();
  const router = { push: vi.fn().mockResolvedValue() };
  app.config.globalProperties.$route = route;
  app.config.globalProperties.$router = router;
  app.config.globalProperties.$store = { commit, dispatch: readProject };
  app.config.globalProperties.$vuetify = { theme: { global: { current: { dark: true } } } };
  const root = { children: [] };
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [
    ...(node.type === type ? [node] : []), ...(node.children || []).flatMap(child => nodes(type, child)),
  ];
  const text = (node = root) => [node.text || "", ...(node.children || []).map(text)].join(" ");
  return { vm, app, nodes, text, route, router, commit, readProject };
}
async function entered(mounted) {
  mounted.vm.form = { name: "example", content: source };
  await Vue.nextTick();
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
});
afterEach(() => {
  apps.splice(0).forEach(app => app.unmount());
  vi.unstubAllGlobals();
});

describe("Compose change preview", () => {
  it("renders separate diff rows without extra newline text and retains empty rows", async () => {
    const mounted = mount();
    await entered(mounted);
    const lines = ["--- Saved Compose", "+    read_only: true", "", "-    image: nginx"];
    axios.post.mockResolvedValueOnce({ data: { ...preview, diff: lines.join("\n") } });
    await mounted.vm.previewChanges();
    const diff = mounted.nodes("pre").find(node => node.props.class === "compose-diff");
    const rows = diff.children[0].children.filter(node => node.type === "span");
    expect(rows.map(node => node.text ?? "")).toEqual(lines);
    // Preformatted inline rows flow horizontally. Each row needs a block
    // boundary and a line-height floor so an empty line is still visible.
    const rowStyle = editorSource.match(/\.compose-diff span\s*\{([^}]+)\}/)[1];
    expect(rowStyle).toMatch(/display:\s*block\s*;/);
    expect(rowStyle).toMatch(/min-height:\s*1\.6em\s*;/);
  });
  it("requires a current reviewed preview and saves its token with the original input", async () => {
    const mounted = mount();
    await entered(mounted);
    expect(mounted.vm.canSave).toBe(false);
    await mounted.vm.submitCompose();
    expect(axios.post).not.toHaveBeenCalled();
    axios.post.mockResolvedValueOnce({ data: preview });
    await mounted.vm.previewChanges();
    expect(axios.post).toHaveBeenCalledExactlyOnceWith("/compose/preview", { name: "example", content: source });
    expect(mounted.text()).toContain("Security defaults applied");
    expect(mounted.text()).toContain("read_only");
    expect(mounted.vm.canSave).toBe(false);
    mounted.nodes("VCheckbox")[0].props["onUpdate:modelValue"](true);
    await Vue.nextTick();
    expect(mounted.vm.canSave).toBe(true);
    axios.post.mockResolvedValueOnce({ data: { name: "example", content: preview.normalized_content } });
    await mounted.vm.submitCompose();
    expect(axios.post).toHaveBeenLastCalledWith("/compose/example/edit", { name: "example", content: source, preview_token: preview.preview_token });
    expect(mounted.vm.isDirty).toBe(false);
    expect(mounted.router.push).toHaveBeenCalledWith({ path: "/projects/example" });
    const next = vi.fn();
    mounted.vm.requestLeave(next);
    expect(next).toHaveBeenCalledWith();
  });
  it("invalidates confirmation when YAML is edited", async () => {
    const mounted = mount();
    await entered(mounted);
    axios.post.mockResolvedValueOnce({ data: preview });
    await mounted.vm.previewChanges();
    mounted.vm.previewConfirmed = true;
    mounted.nodes("AceEditor")[0].props["onUpdate:value"](source + "# changed\n");
    await Vue.nextTick();
    expect(mounted.vm.preview).toBeNull();
    expect(mounted.vm.previewConfirmed).toBe(false);
    expect(mounted.vm.canSave).toBe(false);
  });
  it("ignores preview responses for a changed form", async () => {
    const mounted = mount();
    await entered(mounted);
    const pending = deferred();
    axios.post.mockReturnValueOnce(pending.promise);
    const request = mounted.vm.previewChanges();
    mounted.vm.form.name = "other";
    await Vue.nextTick();
    pending.resolve({ data: preview });
    await request;
    expect(mounted.vm.preview).toBeNull();
    expect(mounted.vm.isPreviewing).toBe(false);
  });
  it("preserves input and shows validation errors without permitting save", async () => {
    const mounted = mount();
    await entered(mounted);
    axios.post.mockRejectedValueOnce({ response: { status: 422, data: { detail: "Invalid YAML document" } } });
    await mounted.vm.previewChanges();
    expect(mounted.vm.form.content).toBe(source);
    expect(mounted.text()).toContain("Invalid YAML document");
    expect(mounted.vm.canSave).toBe(false);
  });
  it("requires a new preview after the saved file changes and blocks duplicate saves", async () => {
    const mounted = mount();
    await entered(mounted);
    axios.post.mockResolvedValueOnce({ data: preview });
    await mounted.vm.previewChanges();
    mounted.vm.previewConfirmed = true;
    const pending = deferred();
    axios.post.mockReturnValueOnce(pending.promise);
    const saving = mounted.vm.submitCompose();
    await mounted.vm.submitCompose();
    expect(axios.post).toHaveBeenCalledTimes(2);
    const next = vi.fn();
    ProjectEditor.beforeRouteLeave.call(mounted.vm, {}, {}, next);
    expect(next).toHaveBeenCalledWith(false);
    pending.reject({ response: { status: 409 } });
    await saving;
    expect(mounted.vm.form.content).toBe(source);
    expect(mounted.vm.preview).toBeNull();
    expect(mounted.vm.previewError).toContain("review a new preview");
    expect(mounted.router.push).not.toHaveBeenCalled();
  });
  it("rejects malformed preview details instead of rendering an unusable review", async () => {
    const mounted = mount();
    await entered(mounted);
    axios.post.mockResolvedValueOnce({ data: { ...preview, security_changes: [{ service: "web", fields: null }] } });
    await mounted.vm.previewChanges();
    expect(mounted.vm.preview).toBeNull();
    expect(mounted.text()).toContain("invalid Compose preview");
    expect(mounted.vm.canSave).toBe(false);
  });
  it("does not navigate from a save response after the editor is unmounted", async () => {
    const mounted = mount();
    await entered(mounted);
    axios.post.mockResolvedValueOnce({ data: preview });
    await mounted.vm.previewChanges();
    mounted.vm.previewConfirmed = true;
    const pending = deferred();
    axios.post.mockReturnValueOnce(pending.promise);
    const saving = mounted.vm.submitCompose();
    apps.splice(apps.indexOf(mounted.app), 1);
    mounted.app.unmount();
    pending.resolve({ data: { name: "example", content: preview.normalized_content } });
    await saving;
    expect(mounted.router.push).not.toHaveBeenCalled();
  });
  it("asks before route changes and browser unload, retaining input when canceled", async () => {
    const mounted = mount();
    await entered(mounted);
    const next = vi.fn();
    ProjectEditor.beforeRouteLeave.call(mounted.vm, {}, {}, next);
    await Vue.nextTick();
    expect(mounted.vm.leaveDialog).toBe(true);
    expect(next).not.toHaveBeenCalled();
    mounted.vm.resolveLeave(false);
    expect(next).toHaveBeenCalledWith(false);
    expect(mounted.vm.form.content).toBe(source);
    const event = { preventDefault: vi.fn(), returnValue: undefined };
    mounted.vm.beforeUnload(event);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(event.returnValue).toBe("");
    const discarded = vi.fn();
    ProjectEditor.beforeRouteUpdate.call(mounted.vm, {}, {}, discarded);
    mounted.vm.resolveLeave(true);
    expect(discarded).toHaveBeenCalledWith(true);
  });
  it("loads direct editor routes and ignores responses after switching projects", async () => {
    const first = deferred();
    const read = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce({ name: "other", content: source });
    const mounted = mount({ name: "example", readProject: read });
    expect(mounted.vm.isLoading).toBe(true);
    mounted.route.params.projectName = "other";
    await Vue.nextTick();
    await Vue.nextTick();
    first.resolve({ name: "example", content: "outdated" });
    await Vue.nextTick();
    await Vue.nextTick();
    expect(mounted.vm.form).toEqual({ name: "other", content: source });
    expect(mounted.vm.isDirty).toBe(false);
  });
});

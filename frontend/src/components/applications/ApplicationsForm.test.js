import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Vue from 'vue';
import { defineRule } from 'vee-validate';
import { required } from '@vee-validate/rules';
import axios from 'axios';
import ApplicationsForm from './ApplicationsForm.vue';
import source from './ApplicationsForm.vue?raw';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
defineRule('required', required);

const apps = [];
function remove(node) {
  const index = node.parent?.children.indexOf(node);
  if (index >= 0) node.parent.children.splice(index, 1);
  node.parent = null;
}
const renderer = Vue.createRenderer({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: 'text', text }),
  createComment: text => ({ type: 'comment', text }),
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

function mount({ template, appDetails } = {}) {
  const root = { children: [] };
  const render = Vue.compile(source.match(/^<template[^>]*>([\s\S]*)<\/template>/)[1], {
    isCustomElement: tag => tag === 'transition-group',
  });
  const app = renderer.createApp({ ...ApplicationsForm, render });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  // Real Form/Field validation and compiled bindings; host presentation nodes
  // expose the Vuetify model events without a DOM or additional dependencies.
  for (const name of [
    'VBtn', 'VCard', 'VCardTitle', 'VCardText', 'VCardActions', 'VIcon', 'VRow', 'VCol',
    'VSpacer', 'VDivider', 'VTextField', 'VSelect', 'VDialog', 'VFadeTransition',
    'VProgressLinear', 'VProgressCircular', 'VStepper', 'VStepperHeader', 'VStepperItem',
    'VStepperWindow', 'VStepperWindowItem', 'VExpansionPanels', 'VExpansionPanel',
    'VExpansionPanelTitle', 'VExpansionPanelText', 'VCheckbox', 'VAlert',
  ]) {
    app.component(name, {
      inheritAttrs: false,
      setup: (_, { attrs, slots }) => () => Vue.h(name, attrs, slots.default?.()),
    });
  }
  const warnings = [];
  app.config.warnHandler = message => warnings.push(message);
  const router = { push: vi.fn().mockResolvedValue() };
  app.config.globalProperties.$router = router;
  app.config.globalProperties.$route = {
    params: template ? { appId: 7 } : appDetails ? { appName: 'existing' } : {}, query: {},
  };
  app.config.globalProperties.$sanitize = value => value;
  app.config.globalProperties.$store = {
    commit: vi.fn(),
    dispatch: vi.fn(async action => {
      if (action === 'networks/_readNetworks') return [{ Name: 'bridge' }, { Name: 'private' }];
      if (action === 'templates/readTemplateApp') return template;
      if (action === 'apps/readApp') return appDetails;
    }),
  };
  const vm = app.mount(root);
  apps.push(app);
  const nodes = (type, node = root) => [
    ...(node.type === type ? [node] : []),
    ...(node.children || []).flatMap(child => nodes(type, child)),
  ];
  const field = name => [...nodes('VTextField'), ...nodes('VSelect')].find(node => node.props.name === name);
  return { vm, nodes, field, router, warnings };
}

async function settle() {
  await Vue.nextTick();
  await new Promise(resolve => setTimeout(resolve, 15));
  await Vue.nextTick();
}
async function change(node, value) {
  node.props['onUpdate:modelValue'](value);
  await settle();
}
const buttonText = node => [node.text || '', ...(node.children || []).map(buttonText)].join('');

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockResolvedValue({ data: {} });
  axios.post.mockResolvedValue({ data: {} });
});
afterEach(() => apps.splice(0).forEach(app => app.unmount()));

describe('container deployment form', () => {
  const validTemplate = overrides => ({
    name: 'web', image: 'nginx:alpine', restart_policy: 'unless-stopped',
    ...overrides,
  });

  it('defaults templates to restricted without trusting embedded approval or root user', async () => {
    const mounted = mount({ template: validTemplate({
      security_profile: 'image-default', container_user: '0:0', confirm_image_default: true,
    }) });
    await settle();
    expect(mounted.vm.form.security_profile).toBe('restricted');
    expect(mounted.vm.form.container_user).toBe('1000:1000');
    expect(mounted.vm.form.confirm_image_default).toBe(false);
    expect(mounted.nodes('VSelect').find(node => node.props.label === 'Network Mode').props.items).not.toContain('host');
    expect(mounted.nodes('VBtn').find(node => node.props['aria-label'] === 'Add device').props.disabled).toBe(true);
    await mounted.vm.submitFormData();
    expect(axios.post).toHaveBeenCalledWith('/apps/deploy', expect.objectContaining({
      security_profile: 'restricted', container_user: '1000:1000', confirm_image_default: false,
    }));
  });

  it.each(['0', '0:1000', '1000:0', 'root', '1000:root', '-1:1000', '2147483648', '1000:2147483648'])(
    'blocks restricted deployment for invalid container user %s', async user => {
      const mounted = mount({ template: validTemplate({}) });
      await settle();
      await change(mounted.nodes('VTextField').find(node => node.props.label === 'Container User (UID or UID:GID)'), user);
      expect(mounted.nodes('VBtn').find(node => buttonText(node) === 'Deploy').props.disabled).toBe(true);
      await mounted.vm.submitFormData();
      expect(axios.post).not.toHaveBeenCalled();
    },
  );

  it('requires a fresh image compatibility acknowledgement after switching profiles', async () => {
    const mounted = mount({ template: validTemplate({}) });
    await settle();
    const selector = mounted.nodes('VSelect').find(node => node.props.label === 'Security Profile');
    await change(selector, 'image-default');
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    await change(mounted.nodes('VCheckbox')[0], true);
    expect(mounted.vm.workloadSecurityValid).toBe(true);
    await change(selector, 'restricted');
    await change(selector, 'image-default');
    expect(mounted.vm.form.confirm_image_default).toBe(false);
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    await change(mounted.nodes('VCheckbox')[0], true);
    await mounted.vm.submitFormData();
    expect(axios.post).toHaveBeenCalledWith('/apps/deploy', expect.objectContaining({
      security_profile: 'image-default', confirm_image_default: true,
    }));
  });

  it.each([
    { network: 'host' },
    { network: '', network_mode: 'host' },
    { devices: [{ host: '/dev/input', container: '/dev/input' }] },
    { cap_add: ['SYS_ADMIN'] },
  ])('blocks restricted deployment with unsupported settings %j', async overrides => {
    const mounted = mount({ template: validTemplate(overrides) });
    await settle();
    expect(mounted.vm.workloadSecurityValid).toBe(false);
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('preserves a restricted existing container user when editing', async () => {
    const mounted = mount({ appDetails: {
      Id: 'abc', name: 'existing',
      Config: { Image: 'nginx', Cmd: [], Env: [], User: '2000:2001', Labels: { 'local.yachtplus.security.profile': 'restricted' } },
      HostConfig: { RestartPolicy: { Name: 'always' }, NetworkMode: 'bridge', Devices: [], Sysctls: {}, CapAdd: [], NanoCpus: 0, Memory: 0 },
      NetworkSettings: { Networks: { bridge: {} } }, Mounts: [], ports: {},
    } });
    await settle();
    expect(mounted.vm.form.security_profile).toBe('restricted');
    expect(mounted.vm.form.container_user).toBe('2000:2001');
    await mounted.vm.submitFormData();
    expect(axios.post).toHaveBeenCalledWith('/apps/deploy', expect.objectContaining({
      edit: true, security_profile: 'restricted', container_user: '2000:2001', confirm_image_default: false,
    }));
  });

  it('renders four Vuetify 3 steps, validates General and allows switching network selection', async () => {
    const mounted = mount();
    await settle();
    expect(mounted.warnings).toEqual([]);
    expect(mounted.nodes('VStepperItem').map(node => node.props.value)).toEqual([1, 2, 3, 4]);
    expect(mounted.nodes('VStepperWindowItem').map(node => node.props.value)).toEqual([1, 2, 3, 4]);
    expect(mounted.nodes('VExpansionPanelTitle')).toHaveLength(6);
    const next = mounted.nodes('VBtn').find(node => buttonText(node).includes('Continue'));
    expect(next.props.disabled).toBe(true);
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    await change(mounted.field('name'), 'web');
    await change(mounted.field('image'), 'nginx:alpine');
    await change(mounted.field('restart_policy'), 'unless-stopped');
    expect(next.props.disabled).toBe(false);
    next.props.onClick();
    await settle();
    expect(mounted.vm.deployStep).toBe(2);
    const network = mounted.nodes('VSelect').find(node => node.props.label === 'Network');
    const mode = mounted.nodes('VSelect').find(node => node.props.label === 'Network Mode');
    expect(network.props.items).toEqual(['bridge', 'private']);
    expect(network.props.disabled).toBe(false);
    expect(mode.props.disabled).toBe(true);
    await change(network, null);
    expect(mode.props.disabled).toBe(false);
    await change(mode, 'host');
    expect(network.props.disabled).toBe(true);
    await change(mode, null);
    expect(network.props.disabled).toBe(false);
  });

  it('posts distinct edited dynamic rows and all Advanced values through the UI', async () => {
    const template = {
      name: 'web', image: 'nginx:alpine', restart_policy: 'unless-stopped',
      network: 'bridge', network_mode: 'bridge',
      ports: [{ label: 'http', hport: '8080', cport: '80', proto: 'tcp' }, { label: 'dns', hport: '8053', cport: '53', proto: 'udp' }],
      volumes: [{ bind: '/data', container: '/data' }],
      env: [{ name: 'TZ', label: 'Timezone', default: 'UTC' }, { name: 'TOKEN', default: 'old' }],
      command: ['server'], devices: [{ host: '/dev/old', container: '/dev/old' }],
      labels: [{ label: 'team', value: 'old' }], sysctls: [{ name: 'net.ipv4.ip_forward', value: '0' }],
    };
    const mounted = mount({ template });
    await settle();
    await change(mounted.nodes('VSelect').find(node => node.props.label === 'Security Profile'), 'image-default');
    await change(mounted.nodes('VCheckbox')[0], true);
    expect(mounted.warnings).toEqual([]);
    expect(mounted.field('ports[1].proto').props.modelValue).toBe('udp');
    expect(mounted.field('env[0].name').props.modelValue).toBe('TZ');
    expect(mounted.vm.form.network_mode).toBe('');
    const values = {
      'ports[0].label': 'webui', 'ports[0].hport': '18080', 'ports[0].cport': '8080', 'ports[0].proto': 'udp',
      'ports[1].hport': '18053', 'volumes[0].bind': '/srv/data', 'volumes[0].container': '/config',
      'env[0].name': 'LANG', 'env[0].default': 'de_DE', 'env[1].default': 'a=b',
      'command[0]': 'daemon', 'devices[0].host': '/dev/new', 'devices[0].container': '/dev/device',
      'labels[0].label': 'owner', 'labels[0].value': 'operations',
      'sysctls[0].name': 'net.ipv4.ip_forward', 'sysctls[0].value': '1',
    };
    for (const [name, value] of Object.entries(values)) await change(mounted.field(name), value);
    await change(mounted.nodes('VSelect').find(node => node.props.label === 'Add Capabilities'), ['NET_BIND_SERVICE']);
    await change(mounted.nodes('VTextField').find(node => node.props.label === 'CPU Cores:'), '2');
    await change(mounted.nodes('VTextField').find(node => node.props.label === 'Memory Limit:'), '512m');
    mounted.vm.removeEnv(0);
    await settle();
    expect(mounted.field('env[0].name').props.modelValue).toBe('TOKEN');
    expect(mounted.field('env[0].default').props.modelValue).toBe('a=b');
    const deploy = mounted.nodes('VBtn').find(node => buttonText(node) === 'Deploy');
    expect(deploy.props.disabled).toBe(false);
    deploy.props.onClick();
    await settle();

    expect(axios.post).toHaveBeenCalledWith('/apps/deploy', expect.objectContaining({
      template_id: 7, name: 'web', image: 'nginx:alpine', restart_policy: 'unless-stopped',
      network: 'bridge', network_mode: '',
      ports: [{ label: 'webui', hport: '18080', cport: '8080', proto: 'udp' }, { label: 'dns', hport: '18053', cport: '53', proto: 'udp' }],
      volumes: [{ bind: '/srv/data', container: '/config' }],
      env: [{ name: 'TOKEN', default: 'a=b' }], command: ['daemon'],
      devices: [{ host: '/dev/new', container: '/dev/device' }],
      labels: [{ label: 'owner', value: 'operations' }],
      sysctls: [{ name: 'net.ipv4.ip_forward', value: '1' }],
      cap_add: ['NET_BIND_SERVICE'], cpus: '2', mem_limit: '512m',
      security_profile: 'image-default', confirm_image_default: true,
    }));
    expect(mounted.router.push).toHaveBeenCalledWith({ name: 'View Applications' });
    expect(template.ports[0].hport).toBe('8080');
    expect(template.env[0].name).toBe('TZ');
  });

  it('blocks deployment when an earlier step or an Advanced field is invalid', async () => {
    const mounted = mount();
    await settle();
    await change(mounted.field('name'), 'web');
    await change(mounted.field('image'), 'nginx');
    await change(mounted.field('restart_policy'), 'always');
    mounted.vm.addPort();
    mounted.vm.deployStep = 4;
    await settle();
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    expect(mounted.vm.deployStep).toBe(2);
    await change(mounted.field('ports[0].cport'), '80');
    mounted.vm.addCommand();
    await settle();
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    expect(mounted.vm.advancedPanels).toEqual([0]);
    await change(mounted.field('command[0]'), 'server');
    await mounted.vm.submitFormData();
    expect(axios.post).toHaveBeenCalledOnce();
  });

  it('shows existing command, device and sysctl values and preserves environment values containing equals', async () => {
    const mounted = mount({ appDetails: {
      Id: 'abc', name: 'existing',
      Config: { Image: 'nginx', Cmd: ['daemon'], Env: ['TOKEN=a=b'], Labels: {} },
      HostConfig: {
        RestartPolicy: { Name: 'always' }, NetworkMode: 'bridge',
        Devices: [{ PathOnHost: '/dev/input', PathInContainer: '/dev/device' }],
        Sysctls: { 'net.ipv4.ip_forward': '1' }, CapAdd: [], NanoCpus: 0, Memory: 0,
      },
      NetworkSettings: { Networks: { bridge: {} } }, Mounts: [], ports: {},
    } });
    await settle();

    expect(mounted.field('command[0]').props.modelValue).toBe('daemon');
    expect(mounted.field('devices[0].host').props.modelValue).toBe('/dev/input');
    expect(mounted.field('sysctls[0].name').props.modelValue).toBe('net.ipv4.ip_forward');
    expect(mounted.field('env[0].default').props.modelValue).toBe('a=b');
    expect(mounted.vm.form.security_profile).toBe('image-default');
    expect(mounted.vm.form.confirm_image_default).toBe(false);
    await mounted.vm.submitFormData();
    expect(axios.post).not.toHaveBeenCalled();
    await change(mounted.nodes('VCheckbox')[0], true);
    await change(mounted.field('command[0]'), 'worker');
    await mounted.vm.submitFormData();
    expect(axios.post).toHaveBeenCalledWith('/apps/deploy', expect.objectContaining({
      edit: true, id: 'abc', command: ['worker'],
      env: [{ label: 'TOKEN', name: 'TOKEN', default: 'a=b' }],
      devices: [{ host: '/dev/input', container: '/dev/device' }],
      sysctls: [{ name: 'net.ipv4.ip_forward', value: '1' }],
    }));
  });
});

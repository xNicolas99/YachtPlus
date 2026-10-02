<template lang="html">
  <div class="apps-form component">
    <h1>
      Deploy {{ form.name }}
      <v-btn
        v-if="!this.$route.params.appId && !this.$route.params.appName"
        tile
        :to="{ name: 'Deploy from Template' }"
        class="primary float-right"
      >
        <v-icon>mdi-plus</v-icon> From Template
      </v-btn>
    </h1>
    <v-card v-if="notes" color="blue-grey darken-2" class="mb-2">
      <v-card-title>Note:</v-card-title>
      <v-card-text v-html="$sanitize(notes)"></v-card-text>
    </v-card>
    <v-stepper class="foreground" v-model="deployStep" alt-labels non-linear hide-actions>
      <v-fade-transition>
        <v-progress-linear
          indeterminate
          v-if="isLoading"
          color="primary"
          bottom
        />
      </v-fade-transition>
      <v-stepper-header>
        <v-stepper-item
          :value="1"
          title="General"
          editable
          edit-icon="mdi-check"
          :complete="deployStep > 1"
        >
        </v-stepper-item>
        <v-divider></v-divider>
        <v-stepper-item
          :value="2"
          title="Networking"
          editable
          edit-icon="mdi-check"
          :complete="deployStep > 2"
        >
        </v-stepper-item>
        <v-divider></v-divider>
        <v-stepper-item
          :value="3"
          title="Volumes"
          editable
          edit-icon="mdi-check"
          :complete="deployStep > 3"
        >
        </v-stepper-item>
        <v-divider></v-divider>
        <v-stepper-item
          :value="4"
          title="Environment"
          editable
          edit-icon="mdi-check"
          :complete="deployStep > 4"
        >
        </v-stepper-item>
      </v-stepper-header>

      <v-stepper-window>
        <v-stepper-window-item :value="1" eager>
          <Form ref="obs1" v-slot="{ meta }" as="div">
            <form>
              <Field
                name="name"
                rules="required"
                v-model="form.name"
                v-slot="{ componentField, errors, meta: fieldMeta }"
              >
                <v-text-field
                  v-bind="componentField"
                  label="Name"
                  placeholder="My Container"
                  :error-messages="errors"
                  :success="fieldMeta.valid"
                  required
                ></v-text-field>
              </Field>
              <Field
                name="image"
                rules="required"
                v-model="form.image"
                v-slot="{ componentField, errors, meta: fieldMeta }"
              >
                <v-text-field
                  v-bind="componentField"
                  label="Image"
                  placeholder="image:my-image"
                  :error-messages="errors"
                  :success="fieldMeta.valid"
                  required
                ></v-text-field>
              </Field>
              <Field
                name="restart_policy"
                rules="required"
                v-model="form['restart_policy']"
                v-slot="{ componentField, errors, meta: fieldMeta }"
              >
                <v-select
                  v-bind="componentField"
                  :items="['always', 'on-failure', 'unless-stopped', 'none']"
                  label="Restart Policy"
                  :error-messages="errors"
                  :success="fieldMeta.valid"
                  required
                ></v-select>
              </Field>
            </form>
            <v-btn
              color="primary"
              @click="deployStep = 2"
              :disabled="!meta.valid || isLoading"
              class="float-right"
            >
              Continue
            </v-btn>
          </Form>
        </v-stepper-window-item>

        <v-stepper-window-item :value="2" eager>
          <Form ref="obs2" v-slot="{ meta }" as="div">
            <form>
              <v-row>
                <v-col>
                  <v-select
                    :items="availableNetworks"
                    label="Network"
                    clearable
                    v-model="form.network"
                    :disabled="!!form.network_mode"
                  />
                </v-col>
                <v-col>
                  <v-select
                    :items="availableNetworkModes"
                    label="Network Mode"
                    clearable
                    v-model="form.network_mode"
                    :disabled="!!form.network"
                  />
                </v-col>
              </v-row>
              <transition-group
                v-if="form.network_mode !== 'host' && form.network !== 'host'"
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
                >
                <v-row v-for="(item, index) in form.ports" :key="index">
                  <v-col>
                    <Field
                      v-model="item.label"
                      :name="`ports[${index}].label`"
                      rules=""
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        type="string"
                        label="Label"
                        placeholder="webui"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.hport"
                      :name="`ports[${index}].hport`"
                      rules=""
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        type="number"
                        label="Host"
                        placeholder="80"
                        min="0"
                        max="65535"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.cport"
                      :name="`ports[${index}].cport`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        type="number"
                        label="Container"
                        placeholder="80"
                        min="0"
                        max="65535"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.proto"
                      :name="`ports[${index}].proto`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-select
                        :items="['tcp', 'udp']"
                        label="Protocol"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-select>
                    </Field>
                  </v-col>

                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removePort(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn
                    v-if="
                      form.network_mode !== 'host' && form.network !== 'host'
                    "
                    icon
                    class="align-self-center"
                    @click="addPort"
                  >
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
            <v-btn
              color="primary"
              @click="deployStep = 3"
              :disabled="!meta.valid || isLoading"
              class="float-right"
            >
              Continue
            </v-btn>
            <v-btn
              color="secondary"
              @click="deployStep = 1"
              class="mx-2 float-right primary--text"
            >
              Back
            </v-btn>
          </Form>
        </v-stepper-window-item>

        <v-stepper-window-item :value="3" eager>
          <Form ref="obs3" v-slot="{ meta }" as="div">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.volumes" :key="index">
                  <v-col>
                    <Field
                      v-model="item.bind"
                      :name="`volumes[${index}].bind`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Host"
                        placeholder="/yachtplus/image/share"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.container"
                      :name="`volumes[${index}].container`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Container"
                        placeholder="/share"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeVolume(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" @click="addVolume" aria-label="Add volume" title="Add volume">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
            <v-btn
              color="primary"
              @click="deployStep = 4"
              :disabled="!meta.valid || isLoading"
              class="float-right"
            >
              Continue
            </v-btn>
            <v-btn
              color="secondary"
              @click="deployStep = 2"
              class="mx-2 float-right primary--text"
            >
              Back
            </v-btn>
          </Form>
        </v-stepper-window-item>

        <v-stepper-window-item :value="4" eager>
          <Form ref="obs4" v-slot="{ meta }" as="div">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.env" :key="index">
                  <v-col>
                    <Field
                      v-model="item.name"
                      :name="`env[${index}].name`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        :label="item.label || 'Name'"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.default"
                      :name="`env[${index}].default`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Value"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        :messages="item.description"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeEnv(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" @click="addEnv" aria-label="Add environment variable" title="Add environment variable">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
            <v-btn
              v-if="form.edit == true"
              color="primary"
              @click="editDialog = true"
              :disabled="!meta.valid || isLoading || !workloadSecurityValid"
              class="float-right"
            >
              <div v-if="isLoading">
                Deploying
                <v-progress-circular
                  indeterminate
                  color="white"
                  size="15"
                  width="2"
                />
              </div>
              <div v-else>Deploy</div>
            </v-btn>
            <v-btn
              v-else
              color="primary"
              @click="nextStep(4)"
              :disabled="!meta.valid || isLoading || !workloadSecurityValid"
              class="float-right"
            >
              <div v-if="isLoading">
                Deploying
                <v-progress-circular
                  indeterminate
                  color="white"
                  size="15"
                  width="2"
                />
              </div>
              <div v-else>Deploy</div>
            </v-btn>
            <v-btn
              color="secondary"
              @click="deployStep = 3"
              class="mx-2 float-right primary--text"
            >
              Back
            </v-btn>
          </Form>
        </v-stepper-window-item>
      </v-stepper-window>
    </v-stepper>
    <v-card v-if="conflictErrors.length > 0" class="mt-5 error">
      <v-card-title>
        Deployment Conflicts
      </v-card-title>
      <v-card-text>
        <ul>
          <li v-for="(error, index) in conflictErrors" :key="index">
            {{ error.message }}
          </li>
        </ul>
      </v-card-text>
    </v-card>
    <v-card class="mt-5" data-testid="workload-security">
      <v-card-title>Container Security</v-card-title>
      <v-card-text>
        <v-select
          :model-value="form.security_profile"
          :items="securityProfiles"
          label="Security Profile"
          :disabled="isLoading"
          @update:model-value="changeSecurityProfile"
        />
        <template v-if="form.security_profile === 'restricted'">
          <p class="mb-3">Restricted runs as a non-root numeric user with a read-only root filesystem. All capabilities are dropped except any allowed capabilities you explicitly add. Writable temporary storage is provided at /tmp and /run. Host networking and device passthrough are blocked.</p>
          <v-text-field
            v-model="form.container_user"
            label="Container User (UID or UID:GID)"
            placeholder="1000:1000"
            :disabled="isLoading"
            :error-messages="containerUserValid ? [] : ['Enter a nonzero numeric UID and optional nonzero GID (maximum 2147483647).']"
          />
          <p>Mount writable volumes for application data and ensure the selected user can access them.</p>
        </template>
        <template v-else>
          <v-alert type="warning" class="mb-3">Image compatibility uses the image's user, which may be root, a writable root filesystem and Docker's default capabilities. Administrator approval is required for each deployment.</v-alert>
          <v-checkbox
            v-model="form.confirm_image_default"
            :disabled="isLoading"
            label="I understand and approve image compatibility for this deployment"
            data-testid="confirm-image-default"
          />
        </template>
        <p class="mt-3">Both profiles prevent gaining new privileges and limit the container to 256 processes.</p>
        <v-alert v-if="workloadSecurityError" type="error" class="mt-3" role="alert">{{ workloadSecurityError }}</v-alert>
      </v-card-text>
    </v-card>
    <v-card color="primary" class="mt-5">
      <v-card-title>
        Advanced
      </v-card-title>
      <Form ref="advanced" as="div">
      <v-expansion-panels v-model="advancedPanels" variant="accordion" multiple>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Command</v-col>
              <v-col cols="4" class="text--secondary">
                (Container Commands)
              </v-col>
            </v-row>
          </v-expansion-panel-title>
          <v-expansion-panel-text eager color="foreground" class="mt-5">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.command" :key="index">
                  <v-col>
                    <Field
                      v-model="form.command[index]"
                      :name="`command[${index}]`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        :label="'Command ' + index + ':'"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeCommand(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" @click="addCommand" aria-label="Add command" title="Add command">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Devices</v-col>
              <v-col cols="4" class="text--secondary">
                (Passthrough Devices)
              </v-col>
            </v-row>
          </v-expansion-panel-title>
          <v-expansion-panel-text eager color="foreground">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.devices" :key="index">
                  <v-col>
                    <Field
                      v-model="item.container"
                      :name="`devices[${index}].container`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Container"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.host"
                      :name="`devices[${index}].host`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Host"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeDevices(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" :disabled="form.security_profile === 'restricted' || isLoading" @click="addDevices" aria-label="Add device" title="Add device">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Labels</v-col>
              <v-col cols="4" class="text--secondary">
                (Container Labels)
              </v-col>
            </v-row>
          </v-expansion-panel-title>
          <v-expansion-panel-text eager color="foreground">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.labels" :key="index">
                  <v-col>
                    <Field
                      v-model="item.label"
                      :name="`labels[${index}].label`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Label"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.value"
                      :name="`labels[${index}].value`"
                      rules=""
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Value"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeLabels(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" @click="addLabels" aria-label="Add label" title="Add label">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Sysctls</v-col>
              <v-col cols="4" class="text--secondary"> (Kernel Options) </v-col>
            </v-row>
          </v-expansion-panel-title>
          <v-expansion-panel-text eager color="foreground">
            <form>
              <transition-group
                name="slide"
                enter-active-class="animated fadeInLeft fast-anim"
                leave-active-class="animated fadeOutLeft fast-anim"
              >
                <v-row v-for="(item, index) in form.sysctls" :key="index">
                  <v-col>
                    <Field
                      v-model="item.name"
                      :name="`sysctls[${index}].name`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Name"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col>
                    <Field
                      v-model="item.value"
                      :name="`sysctls[${index}].value`"
                      rules="required"
                      v-slot="{ componentField, errors, meta: fieldMeta }"
                    >
                      <v-text-field
                        label="Value"
                        v-bind="componentField"
                        :error-messages="errors"
                        :success="fieldMeta.valid"
                        required
                      ></v-text-field>
                    </Field>
                  </v-col>
                  <v-col class="d-flex justify-end" cols="1">
                    <v-btn
                      icon
                      class="align-self-center"
                      @click="removeSysctls(index)"
                    >
                      <v-icon>mdi-minus</v-icon>
                    </v-btn>
                  </v-col>
                </v-row>
              </transition-group>
              <v-row>
                <v-col cols="12" class="d-flex justify-end">
                  <v-btn icon class="align-self-center" @click="addSysctls" aria-label="Add sysctl" title="Add sysctl">
                    <v-icon>mdi-plus</v-icon>
                  </v-btn>
                </v-col>
              </v-row>
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Capabilities</v-col>
              <v-col cols="4" class="text--secondary">
                (Special Permissions/Capabilities)
              </v-col>
            </v-row></v-expansion-panel-title
          >
          <v-expansion-panel-text eager color="foreground">
            <form>
              <v-select
                v-model="form['cap_add']"
                :items="cap_options"
                label="Add Capabilities"
                multiple
                hide-selected
                clearable
                chips
                closable-chips
              />
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title color="foreground">
            <v-row no-gutters>
              <v-col cols="2">Runtime</v-col>
              <v-col cols="4" class="text--secondary">
                (CPU/MEM Limits)
              </v-col>
            </v-row></v-expansion-panel-title
          >
          <v-expansion-panel-text eager color="foreground">
            <form>
              <v-text-field
                v-model="form['cpus']"
                label="CPU Cores:"
                clearable
              />
              <v-text-field
                v-model="form['mem_limit']"
                label="Memory Limit:"
                placeholder="(1000b,100k,10m,1g)"
                clearable
              />
            </form>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
      </Form>
    </v-card>
    <v-dialog v-model="editDialog" max-width="290">
      <v-card>
        <v-card-title class="headline" style="word-break: break-all;">
          Are you sure you want to edit this container?
        </v-card-title>
        <v-card-text>
          This will remove the currently running container and deploy a new one
          with the settings in this form. Please make sure your container data
          is persistant or backed up.
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="editDialog = false">
            Cancel
          </v-btn>
          <v-btn
            variant="text"
            color="yellow"
            :disabled="isLoading || !workloadSecurityValid"
            @click="
              nextStep(4);
              editDialog = false;
            "
          >
            Edit
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from "axios";
import { mapActions, mapMutations } from "vuex";
import { Form, Field } from "vee-validate";

export default {
  components: {
    Field,
    Form
  },
  data() {
    return {
      deployStep: 1,
      deploySteps: 4,
      advancedPanels: [],
      notes: "",
      networks: [],
      volumes: [],
      editDialog: false,
      form: {
        name: "",
        image: "",
        restart_policy: "",
        network: "bridge",
        network_mode: "",
        ports: [],
        volumes: [],
        env: [],
        command: [],
        devices: [],
        labels: [],
        sysctls: [],
        cap_add: [],
        cpus: undefined,
        mem_limit: undefined,
        security_profile: "restricted",
        container_user: "1000:1000",
        confirm_image_default: false
      },
      conflictErrors: [],
      network_modes: ["bridge", "none", "host"],
      isLoading: false,
      cap_options: [
        "CHOWN", "DAC_OVERRIDE", "FSETID", "FOWNER", "KILL", "SETGID",
        "SETUID", "SETPCAP", "NET_BIND_SERVICE", "SYS_CHROOT", "AUDIT_WRITE"
      ]
    };
  },
  computed: {
    availableNetworks() {
      return this.form.security_profile === "restricted" ? this.networks.filter(network => network !== "host") : this.networks;
    },
    availableNetworkModes() {
      return this.form.security_profile === "restricted" ? this.network_modes.filter(mode => mode !== "host") : this.network_modes;
    },
    securityProfiles() {
      return [
        { title: "Restricted (recommended)", value: "restricted" },
        { title: "Image compatibility (administrator approval)", value: "image-default" }
      ];
    },
    containerUserValid() {
      const user = this.form.container_user;
      return typeof user === "string" && /^[1-9][0-9]{0,9}(?::[1-9][0-9]{0,9})?$/.test(user) &&
        user.split(":").every(part => Number(part) <= 2147483647);
    },
    workloadSecurityError() {
      if (!["restricted", "image-default"].includes(this.form.security_profile)) return "Select a container security profile.";
      if (this.form.cap_add.some(capability => !this.cap_options.includes(capability))) return "Remove unsupported capabilities before deploying.";
      if (this.form.security_profile === "image-default") {
        return this.form.confirm_image_default === true ? "" : "Confirm image compatibility before deploying.";
      }
      if (!this.containerUserValid) return "Restricted containers require a nonzero numeric UID and optional nonzero GID.";
      if (this.form.network_mode === "host" || this.form.network === "host") return "Restricted containers cannot use host networking. Choose another network or explicitly approve image compatibility.";
      if (this.form.devices.length) return "Restricted containers cannot use device passthrough. Remove the devices or explicitly approve image compatibility.";
      return "";
    },
    workloadSecurityValid() {
      return !this.workloadSecurityError;
    }
  },
  methods: {
    changeSecurityProfile(profile) {
      if (this.isLoading || !["restricted", "image-default"].includes(profile)) return;
      this.form.security_profile = profile;
      this.form.confirm_image_default = false;
    },
    ...mapActions({
      readTemplateApp: "templates/readTemplateApp",
      readNetworks: "networks/_readNetworks",
      readApp: "apps/readApp"
    }),
    ...mapMutations({
      setErr: "snackbar/setErr",
      setMessage: "snackbar/setMessage"
    }),
    addCommand() {
      this.form.command.push("");
    },
    removeCommand(index) {
      this.form.command.splice(index, 1);
    },
    addPort() {
      this.form.ports.push({ hport: "", cport: "", proto: "tcp" });
    },
    removePort(index) {
      this.form.ports.splice(index, 1);
    },
    addVolume() {
      this.form.volumes.push({ container: "", bind: "" });
    },
    removeVolume(index) {
      this.form.volumes.splice(index, 1);
    },
    addEnv() {
      this.form.env.push({ name: "", label: "", default: "" });
    },
    removeEnv(index) {
      this.form.env.splice(index, 1);
    },
    addDevices() {
      this.form.devices.push({ container: "", host: "" });
    },
    removeDevices(index) {
      this.form.devices.splice(index, 1);
    },
    addLabels() {
      this.form.labels.push({ label: "", value: "" });
    },
    removeLabels(index) {
      this.form.labels.splice(index, 1);
    },
    addSysctls() {
      this.form.sysctls.push({ name: "", value: "" });
    },
    removeSysctls(index) {
      this.form.sysctls.splice(index, 1);
    },
    addCap_add() {
      this.form.cap_add.push("");
    },
    removeCap_add(index) {
      this.form.cap_add.splice(index, 1);
    },
    transform_ports(ports, app) {
      let portlist = [];
      for (let port in ports) {
        let _port = port.split("/") || "";
        var cport = _port[0] || "";
        if (ports[port]) {
          var hport = ports[port][0].HostPort || "";
        } else {
          continue;
        }
        var proto = _port[1] || "";
        var label = app.Config.Labels[`local.yacht.port.${hport}`] || "";
        let port_entry = {
          cport: cport,
          hport: hport,
          proto: proto,
          label: label
        };
        portlist.push(port_entry);
      }
      return portlist;
    },
    transform_volumes(volumes) {
      let volumelist = [];
      for (let volume in volumes) {
        let container = volumes[volume].Destination || "";
        let bind = volumes[volume].Source || "";
        let volume_entry = {
          bind: bind,
          container: container
        };
        volumelist.push(volume_entry);
      }
      return volumelist;
    },
    transform_env(envs) {
      let envlist = [];
      for (let env in envs) {
        let _env = envs[env].split("=");
        let name = _env[0];
        let value = _env.slice(1).join("=");
        let env_entry = {
          label: name,
          name: name,
          default: value
        };
        envlist.push(env_entry);
      }
      return envlist;
    },
    transform_labels(labels) {
      let labellist = [];
      for (let _label in labels) {
        let label = _label;
        let value = labels[label];
        let label_entry = {
          label: label,
          value: value
        };
        labellist.push(label_entry);
      }
      return labellist;
    },
    transform_cpus(_cpus) {
      let cpus = _cpus / 10 ** 9;
      if (cpus != 0) {
        return cpus;
      }
      return undefined;
    },
    transform_mem_limit(bytes) {
      if (bytes != 0) {
        var i = Math.floor(Math.log(bytes) / Math.log(1024)),
          sizes = ["b", "k", "m", "g"];

        return (bytes / Math.pow(1024, i)).toFixed(2) * 1 + sizes[i];
      } else {
        return undefined;
      }
    },
    nextStep(n) {
      if (n === this.deploySteps) {
        // this.deployStep = 1;
        this.submitFormData();
      } else {
        this.deployStep = n + 1;
      }
    },
    async submitFormData() {
      if (this.isLoading) return;
      if (!this.workloadSecurityValid) return;
      this.isLoading = true;
      const refs = ["obs1", "obs2", "obs3", "obs4", "advanced"];
      const validation = await Promise.all(refs.map(ref => this.$refs[ref].validate()));
      const invalidStep = validation.findIndex(result => !result.valid);
      if (invalidStep !== -1) {
        if (invalidStep < this.deploySteps) this.deployStep = invalidStep + 1;
        else {
          const panels = { command: 0, devices: 1, labels: 2, sysctls: 3 };
          this.advancedPanels = [...new Set(Object.keys(validation[invalidStep].errors)
            .map(name => panels[name.split("[")[0]]))];
        }
        this.isLoading = false;
        return;
      }
      const payload = { ...this.form };

      // Add template_id if we are deploying from a template
      if (this.$route.params.appId) {
        payload.template_id = this.$route.params.appId;
      }

      this.conflictErrors = []; // Clear previous errors
      const url = `/apps/deploy`;
      return axios
        .post(url, payload)
        .then(() => {
          this.isLoading = false;
          this.$router.push({ name: "View Applications" });
        })
        .catch(err => {
          this.isLoading = false;
          this.deployStep = 1;

          if (err.response && err.response.status === 409 && err.response.data && err.response.data.conflicts) {
            this.conflictErrors = err.response.data.conflicts;
            this.setErr({
                response: {
                    statusText: "Conflict",
                    data: { detail: "Please check the conflicts below." }
                }
            });
          } else {
            this.setErr(err);
          }
        });
    },
    async populateNetworks() {
      const networks = await this.readNetworks();
      this.networks = networks.map(network => network.Name);
    },
    async populateForm() {
      if (this.$route.params.appId) {
        const appId = this.$route.params.appId;
        if (appId != null) {
          try {
            const app = await this.readTemplateApp(appId);
            this.form = {
              name: app.name || "",
              image: app.image || "",
              restart_policy: app.restart_policy || "",
              command: [...(app.command || [])],
              network: app.network || "",
              network_mode: app.network_mode || "",
              ports: (app.ports || []).map(item => ({ ...item })),
              volumes: (app.volumes || []).map(item => ({ ...item })),
              env: (app.env || []).map(item => ({ ...item })),
              devices: (app.devices || []).map(item => ({ ...item })),
              labels: (app.labels || []).map(item => ({ ...item })),
              sysctls: (app.sysctls || []).map(item => ({ ...item })),
              cap_add: [...(app.cap_add || [])],
              cpus: app.cpus,
              mem_limit: app.mem_limit,
              security_profile: "restricted",
              container_user: "1000:1000",
              confirm_image_default: false
            };
            this.notes = app.notes || null;
          } catch (error) {
            console.error(error, error.response);
            this.setErr(error);
          }
        }
      } else if (this.$route.params.appName) {
        const appName = this.$route.params.appName;
        const app = await this.readApp(appName);
        this.form = {
          name: app.name || "",
          image: app.Config.Labels?.['local.yachtplus.update.image'] || app.Config.Image || "",
          restart_policy: app.HostConfig.RestartPolicy.Name || "",
          command: [...(app.Config.Cmd || [])],
          network: Object.keys(app.NetworkSettings.Networks)[0] || "",
          network_mode: this.network_modes.includes(app.HostConfig.NetworkMode) ? app.HostConfig.NetworkMode : "",
          ports: this.transform_ports(app.ports, app) || [],
          volumes: this.transform_volumes(app.Mounts) || [],
          env: this.transform_env(app.Config.Env) || [],
          devices: (app.HostConfig.Devices || []).map(device => ({
            host: device.PathOnHost, container: device.PathInContainer
          })),
          labels: this.transform_labels(app.Config.Labels) || [],
          sysctls: Object.entries(app.HostConfig.Sysctls || {}).map(([name, value]) => ({ name, value })),
          cap_add: app.HostConfig.CapAdd || [],
          cpus: this.transform_cpus(app.HostConfig.NanoCpus),
          mem_limit: this.transform_mem_limit(app.HostConfig.Memory),
          edit: true,
          id: app.Id,
          security_profile: app.Config.Labels?.["local.yachtplus.security.profile"] === "restricted" ? "restricted" : "image-default",
          container_user: app.Config.Labels?.["local.yachtplus.security.profile"] === "restricted" ? (app.Config.User || "") : "1000:1000",
          confirm_image_default: false
        };
      } else if (this.$route.query.image) {
        // Handle deployment from Registry Browser (Unified Search)
        const image = this.$route.query.image;
        this.form.image = image;
        // Generate a name from the image (e.g. "nginx" from "library/nginx")
        const namePart = image.split('/').pop().split(':')[0];
        this.form.name = namePart;
        this.form.restart_policy = "unless-stopped"; // Default for new deploys
        this.form.network_mode = ""; // Default network
        this.form.network = "bridge";

        // Attempt to fetch image config (ports/volumes) from backend
        this.isLoading = true;
        try {
          const { data } = await axios.get('/registries/inspect', { params: { image: image } });
          if (data) {
            // Map Ports
            if (data.ExposedPorts) {
              this.form.ports = Object.keys(data.ExposedPorts).map(p => {
                const [port, proto] = p.split('/');
                return { cport: port, hport: port, proto: proto || 'tcp' };
              });
            }
            // Map Volumes
            if (data.Volumes) {
              // Generate a random string for unique volume names
              const rand = Math.random().toString(36).substring(2, 8);
              this.form.volumes = Object.keys(data.Volumes).map(v => {
                return { container: v, bind: `yachtplus_${namePart}_${rand}_${v.replace(/\//g, '_')}` };
              });
            }
          }
        } catch (e) {
          console.error("Failed to inspect remote image", e);
        } finally {
          this.isLoading = false;
        }
      }
      // Docker accepts a network or a network mode. Keep one selection active.
      if (this.form.network && this.form.network_mode) {
        if (this.form.network_mode === "bridge") this.form.network_mode = "";
        else this.form.network = "";
      }
      if (!this.form.network && !this.form.network_mode) this.form.network = "bridge";
    }
  },
  async created() {
    // ⚡ Bolt: Fetch form data and networks concurrently to reduce component mount time.
    await Promise.all([
      this.populateForm(),
      this.populateNetworks()
    ]);
  }
};
</script>

<style lang="css" scoped></style>

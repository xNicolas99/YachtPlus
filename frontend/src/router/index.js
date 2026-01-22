import { createRouter, createWebHashHistory } from 'vue-router'
import store from "../store";

// Templates
import Home from "../views/Home.vue";
import Login from "../views/auth/Login.vue";
import Setup from "../views/auth/Setup.vue";

// Templates
import Templates from "../views/Templates.vue";
import TemplatesShow from "../components/templates/TemplatesDetails.vue";
import TemplatesForm from "../components/templates/TemplatesForm.vue";
import TemplatesList from "../components/templates/TemplatesList.vue";

// Apps
import Applications from "../views/Applications.vue";
import AppContent from "../components/applications/ApplicationDetailsComponents/AppContent.vue";
import AppProcesses from "../components/applications/ApplicationDetailsComponents/AppProcesses.vue";
import AppLogs from "../components/applications/ApplicationDetailsComponents/AppLogs.vue";
import AppStats from "../components/applications/ApplicationDetailsComponents/AppStats.vue";
import ApplicationDetails from "../components/applications/ApplicationDetails.vue";
import ApplicationsList from "../components/applications/ApplicationsList.vue";
import ApplicationsForm from "../components/applications/ApplicationsForm.vue";
import ApplicationDeployFromTemplate from "../components/applications/ApplicationDeployFromTemplate.vue";

// Project
import Project from "../views/Project.vue";
import ProjectList from "../components/compose/ProjectList.vue";
import ProjectDetails from "../components/compose/ProjectDetails.vue";
import ProjectEditor from "../components/compose/ProjectEditor.vue";

// Resources
import Resources from "../views/Resources.vue";
// Images
import ImageList from "../components/resources/images/ImageList.vue";
import ImageDetails from "../components/resources/images/ImageDetails.vue";
// Volumes
import VolumeList from "../components/resources/volumes/VolumeList.vue";
import VolumeDetails from "../components/resources/volumes/VolumeDetails.vue";
// Networks
import NetworkList from "../components/resources/networks/NetworkList.vue";
import NetworkDetails from "../components/resources/networks/NetworkDetails.vue";
import NetworkForm from "../components/resources/networks/NetworkForm.vue";

// User Settings
import UserSettings from "../views/UserSettings.vue";
import ChangePasswordForm from "../components/userSettings/ChangePasswordForm.vue";
import UserInfo from "../components/userSettings/UserInfo.vue";

// Server Settings
// import ServerSettingsNav from "../components/serverSettings/ServerSettingsNav.vue"
import ServerSettings from "../views/ServerSettings.vue";
import ServerInfo from "../components/serverSettings/ServerInfo.vue";
import ServerVariables from "../components/serverSettings/ServerVariables.vue";
import Prune from "../components/serverSettings/Prune.vue";
import ServerUpdate from "../components/serverSettings/ServerUpdate.vue";
import Theme from "../components/serverSettings/Theme.vue";
import AuditLogs from "../components/serverSettings/AuditLogs.vue";
import UserManagement from "../views/UserManagement.vue";

const routes = [
  {
    path: "/",
    name: "Home",
    component: Home
  },
  {
    path: "/login",
    name: "Login",
    component: Login
  },
  {
    path: "/setup",
    name: "Setup",
    component: Setup
  },
  {
    path: "/templates",
    // name: "Templates",
    component: Templates,
    children: [
      {
        path: "",
        name: "View Templates",
        component: TemplatesList // perhaps rename to TemplatesIndex
      },
      {
        path: "new",
        name: "New Template",
        component: TemplatesForm // perhaps rename to TemplatesCreate
      },
      {
        path: ":templateId",
        name: "Template Details",
        component: TemplatesShow // perhaps rename to TemplateDetails
      }
    ]
  },
  {
    path: "/apps",
    component: Applications,
    children: [
      {
        name: "Deploy",
        path: "deploy/:appId",
        component: ApplicationsForm
      },
      {
        name: "Edit",
        path: "edit/:appName",
        component: ApplicationsForm
      },
      {
        name: "Deploy from Template",
        path: "templates",
        component: ApplicationDeployFromTemplate
      },
      {
        name: "View Applications",
        path: "/",
        component: ApplicationsList
      },
      {
        name: "Add Application",
        path: "deploy",
        component: ApplicationsForm
      },
      {
        path: ":appName",
        component: ApplicationDetails,
        children: [
          {
            name: "Processes",
            path: "top",
            component: AppProcesses
          },
          {
            name: "Info",
            path: "info",
            component: AppContent
          },
          {
            name: "Logs",
            path: "logs",
            component: AppLogs
          },
          {
            name: "Stats",
            path: "stats",
            component: AppStats
          }
        ]
      }
    ]
  },
  {
    path: "/projects",
    component: Project,
    children: [
      {
        name: "View Projects",
        path: "/",
        component: ProjectList
      },
      {
        name: "Edit Project",
        path: ":projectName/edit",
        component: ProjectEditor
      },
      {
        name: "Project Details",
        path: ":projectName",
        component: ProjectDetails
      }
    ]
  },
  {
    path: "/user",
    component: UserSettings,
    children: [
      {
        name: "User Info",
        path: "info",
        component: UserInfo
      },
      {
        name: "Change Password",
        path: "changePassword",
        component: ChangePasswordForm
      }
    ]
  },
  {
    path: "/users",
    component: UserManagement,
    name: "User Management"
  },
  {
    path: "/settings",
    component: ServerSettings,
    children: [
      {
        name: "Server Info",
        path: "info",
        component: ServerInfo
      },
      {
        name: "Theme",
        path: "theme",
        component: Theme
      },
      {
        name: "Template Variables",
        path: "templateVariables",
        component: ServerVariables
      },
      {
        name: "Audit Logs",
        path: "audit",
        component: AuditLogs
      },
      {
        name: "Prune",
        path: "prune",
        component: Prune
      },
      {
        name: "Update YachtPlus",
        path: "update",
        component: ServerUpdate
      }
    ]
  },
  {
    path: "/resources",
    component: Resources,
    children: [
      {
        name: "Images",
        path: "images",
        component: ImageList
      },
      {
        path: "images/:imageid",
        name: "Image Details",
        component: ImageDetails
      },
      {
        name: "Volumes",
        path: "volumes",
        component: VolumeList
      },
      {
        path: "volumes/:volumeName",
        name: "Volume Details",
        component: VolumeDetails
      },
      {
        name: "Networks",
        path: "networks",
        component: NetworkList
      },
      {
        path: "networks/new",
        name: "New Network",
        component: NetworkForm
      },
      {
        path: "networks/:networkid",
        name: "Network Details",
        component: NetworkDetails
      }
    ]
  }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

router.beforeEach(async (to, from, next) => {
  if (!store.state.auth.status) {
    await store.dispatch("auth/AUTH_CHECK");
  }

  const isSetup = store.getters["auth/isSetup"];
  const isLoggedIn = store.getters["auth/isAuthenticated"];

  if (!isSetup) {
    if (to.path !== "/setup") {
      next("/setup");
    } else {
      next();
    }
  } else {
    // System is setup
    if (to.path === "/setup") {
      // Cannot access setup if already setup
      next("/login");
    } else if (!isLoggedIn && to.path !== "/login") {
      next("/login");
    } else if (isLoggedIn && (to.path === "/login" || to.path === "/setup")) {
      next("/");
    } else {
      next();
    }
  }
});

export default router;

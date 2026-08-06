import { createRouter, createWebHashHistory } from 'vue-router'
import store from "../store";

// Lazy-loaded route components. Each `() => import(...)` becomes its own
// chunk, so the initial bundle only ships the shell + the first view
// instead of every page up front. This is the single biggest win for
// perceived startup time on a self-hosted UI.

const routes = [
  {
    path: "/",
    name: "Home",
    component: () => import("../views/Home.vue")
  },
  {
    path: "/login",
    name: "Login",
    component: () => import("../views/auth/Login.vue")
  },
  {
    path: "/setup",
    name: "Setup",
    component: () => import("../views/auth/Setup.vue")
  },
  {
    path: "/templates",
    component: () => import("../views/Templates.vue"),
    children: [
      {
        path: "",
        name: "View Templates",
        component: () => import("../components/templates/TemplatesList.vue")
      },
      {
        path: "new",
        name: "New Template",
        component: () => import("../components/templates/TemplatesForm.vue")
      },
      {
        path: ":templateId",
        name: "Template Details",
        component: () => import("../components/templates/TemplatesDetails.vue")
      }
    ]
  },
  {
    path: "/apps",
    component: () => import("../views/Applications.vue"),
    children: [
      {
        name: "Deploy",
        path: "deploy/:appId",
        component: () => import("../components/applications/ApplicationsForm.vue")
      },
      {
        name: "Edit",
        path: "edit/:appName",
        component: () => import("../components/applications/ApplicationsForm.vue")
      },
      {
        name: "Deploy from Template",
        path: "templates",
        component: () => import("../components/applications/ApplicationDeployFromTemplate.vue")
      },
      {
        name: "View Applications",
        path: "/",
        component: () => import("../components/applications/ApplicationsList.vue")
      },
      {
        name: "Add Application",
        path: "deploy",
        component: () => import("../components/applications/ApplicationsForm.vue")
      },
      {
        path: ":appName",
        component: () => import("../components/applications/ApplicationDetails.vue"),
        children: [
          {
            name: "Processes",
            path: "top",
            component: () => import("../components/applications/ApplicationDetailsComponents/AppProcesses.vue")
          },
          {
            name: "Info",
            path: "info",
            component: () => import("../components/applications/ApplicationDetailsComponents/AppContent.vue")
          },
          {
            name: "Logs",
            path: "logs",
            component: () => import("../components/applications/ApplicationDetailsComponents/AppLogs.vue")
          },
          {
            name: "Stats",
            path: "stats",
            component: () => import("../components/applications/ApplicationDetailsComponents/AppStats.vue")
          }
        ]
      }
    ]
  },
  {
    path: "/projects",
    component: () => import("../views/Project.vue"),
    children: [
      {
        name: "View Projects",
        path: "/",
        component: () => import("../components/compose/ProjectList.vue")
      },
      {
        name: "Edit Project",
        path: ":projectName/edit",
        component: () => import("../components/compose/ProjectEditor.vue")
      },
      {
        name: "Project Details",
        path: ":projectName",
        component: () => import("../components/compose/ProjectDetails.vue")
      }
    ]
  },
  {
    path: "/user",
    component: () => import("../views/UserSettings.vue"),
    children: [
      {
        name: "User Info",
        path: "info",
        component: () => import("../components/userSettings/UserInfo.vue")
      },
      {
        name: "Change Password",
        path: "changePassword",
        component: () => import("../components/userSettings/ChangePasswordForm.vue")
      }
    ]
  },
  {
    path: "/users",
    component: () => import("../views/UserManagement.vue"),
    name: "User Management"
  },
  {
    path: "/settings",
    component: () => import("../views/ServerSettings.vue"),
    children: [
      {
        name: "Server Info",
        path: "info",
        component: () => import("../components/serverSettings/ServerInfo.vue")
      },
      {
        name: "Theme",
        path: "theme",
        component: () => import("../components/serverSettings/Theme.vue")
      },
      {
        name: "Template Variables",
        path: "templateVariables",
        component: () => import("../components/serverSettings/ServerVariables.vue")
      },
      {
        name: "Audit Logs",
        path: "audit",
        component: () => import("../components/serverSettings/AuditLogs.vue")
      },
      {
        name: "Prune",
        path: "prune",
        component: () => import("../components/serverSettings/Prune.vue")
      },
      {
        name: "Update YachtPlus",
        path: "update",
        component: () => import("../components/serverSettings/ServerUpdate.vue")
      }
    ]
  },
  {
    path: "/resources",
    component: () => import("../views/Resources.vue"),
    children: [
      {
        name: "Images",
        path: "images",
        component: () => import("../components/resources/images/ImageList.vue")
      },
      {
        path: "images/:imageid",
        name: "Image Details",
        component: () => import("../components/resources/images/ImageDetails.vue")
      },
      {
        name: "Volumes",
        path: "volumes",
        component: () => import("../components/resources/volumes/VolumeList.vue")
      },
      {
        path: "volumes/:volumeName",
        name: "Volume Details",
        component: () => import("../components/resources/volumes/VolumeDetails.vue")
      },
      {
        name: "Networks",
        path: "networks",
        component: () => import("../components/resources/networks/NetworkList.vue")
      },
      {
        path: "networks/new",
        name: "New Network",
        component: () => import("../components/resources/networks/NetworkForm.vue")
      },
      {
        path: "networks/:networkid",
        name: "Network Details",
        component: () => import("../components/resources/networks/NetworkDetails.vue")
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

  // Treat `null` (= unknown) as "do not redirect to setup". Only an
  // explicit `false` from the API counts. Without this guard, a
  // transient /setup/status failure during cold start would still
  // bounce a finished install into the wizard.
  if (isSetup === false) {
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

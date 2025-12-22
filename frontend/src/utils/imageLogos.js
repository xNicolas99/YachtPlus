// File: frontend/src/utils/imageLogos.js

const REGISTRY_FALLBACKS = {
  dockerhub:
    "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/docker.svg",
  ghcr: "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/github.svg",
  linuxserver:
    "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/linuxserver.svg",
  "linuxserver.io":
    "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/linuxserver.svg"
};

/**
 * Normalize image name to match logo naming conventions
 * @param {string} imageName
 */
function normalizeImageName(imageName) {
  if (!imageName) return "";
  // Remove version tags: "plex:latest" -> "plex"
  let normalized = imageName.split(":")[0];

  // Remove registry prefix: "ghcr.io/linuxserver/plex" -> "linuxserver/plex"
  normalized = normalized.replace(/^[a-z0-9.-]+\.(io|com|org)\//i, "");

  // For linuxserver images: "linuxserver/plex" -> "plex"
  if (normalized.startsWith("linuxserver/")) {
    normalized = normalized.split("linuxserver/")[1];
  }

  // Remove other org prefixes: "portainer/portainer-ce" -> "portainer-ce"
  if (normalized.includes("/")) {
    normalized = normalized.split("/").pop();
  }

  // Convert to lowercase
  normalized = normalized.toLowerCase();

  // Handle special cases
  const specialCases = {
    "portainer-ce": "portainer",
    "home-assistant": "home-assistant",
    "nginx-proxy-manager": "nginx-proxy-manager",
    vaultwarden: "vaultwarden" // formerly bitwarden_rs
  };

  return specialCases[normalized] || normalized;
}

/**
 * Try multiple CDN sources with fallback chain
 * @param {string} imageName
 * @param {string} registry
 */
export function getImageLogoWithFallbacks(imageName, registry) {
  const normalized = normalizeImageName(imageName);

  // Handle case where registry might be 'linuxserver' or 'linuxserver.io'
  const isLinuxServer =
    registry === "linuxserver" || registry === "linuxserver.io";

  // Priority order of logo sources
  const logoSources = [
    // 1. dashboard-icons (most comprehensive)
    `https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/${normalized}.svg`,

    // 2. LinuxServer.io Fleet logos (if applicable)
    isLinuxServer
      ? `https://fleet.linuxserver.io/images/${normalized}-logo.png`
      : null,

    // 3. Shields.io dynamic logo
    `https://img.shields.io/badge/-${normalized}-blue?logo=${normalized}&style=flat-square`,

    // 4. Registry fallback
    REGISTRY_FALLBACKS[registry] || REGISTRY_FALLBACKS["dockerhub"]
  ].filter(Boolean);

  return {
    sources: logoSources,
    fallback: REGISTRY_FALLBACKS[registry] || REGISTRY_FALLBACKS["dockerhub"]
  };
}

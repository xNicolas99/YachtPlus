import { describe, it, expect } from 'vitest';
import { getImageLogoWithFallbacks } from './imageLogos.js';

describe('getImageLogoWithFallbacks', () => {
  it('returns fleet linuxserver source and proper registry fallback for linuxserver', () => {
    const result = getImageLogoWithFallbacks('plex', 'linuxserver');

    // Check fallback
    expect(result.fallback).toBe("https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/linuxserver.svg");

    // Check sources
    expect(result.sources).toContain('https://fleet.linuxserver.io/images/plex-logo.png');
    expect(result.sources).toContain('https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/plex.svg');
    expect(result.sources).toContain('https://img.shields.io/badge/-plex-blue?logo=plex&style=flat-square');
  });

  it('handles github container registry', () => {
    const result = getImageLogoWithFallbacks('org/app:latest', 'ghcr');
    expect(result.fallback).toBe("https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/github.svg");
    expect(result.sources).toContain('https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/app.svg');
  });

  it('handles standard dockerhub images', () => {
    const result = getImageLogoWithFallbacks('nginx', 'dockerhub');
    expect(result.fallback).toBe("https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/docker.svg");
    expect(result.sources).toContain('https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg/nginx.svg');
    expect(result.sources).not.toContain('https://fleet.linuxserver.io/images/nginx-logo.png');
  });
});

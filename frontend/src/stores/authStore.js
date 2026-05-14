import { defineStore } from 'pinia';
import axios from 'axios';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    user: null,
    isAuthenticated: false
  }),
  actions: {
    async login(credentials) {
      if (credentials.email && !credentials.username) {
        credentials.username = credentials.email;
      }
      try {
        const formData = new URLSearchParams();
        formData.append('username', credentials.username);
        formData.append('password', credentials.password);

        const res = await axios.post('/api/auth/login', formData);
        this.token = res.data.access_token;
        this.isAuthenticated = true;
        localStorage.setItem('token', this.token);
        return true;
      } catch (error) {
        throw error;
      }
    },
    logout() {
      this.token = null;
      this.user = null;
      this.isAuthenticated = false;
      localStorage.removeItem('token');
    }
  }
});

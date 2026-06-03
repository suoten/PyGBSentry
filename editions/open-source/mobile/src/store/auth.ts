import { defineStore } from "pinia";
import type { UserProfile } from "@/types/api";
import { clearProfile, clearToken, getProfile, getToken, setProfile, setToken } from "@/utils/storage";

interface AuthState {
  token: string;
  profile: UserProfile | null;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    token: getToken(),
    profile: getProfile<UserProfile>()
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token)
  },
  actions: {
    setAuth(token: string, profile: UserProfile | null) {
      this.token = token;
      this.profile = profile;
      setToken(token);
      if (profile) setProfile(profile as unknown as Record<string, unknown>);
    },
    logout() {
      this.token = "";
      this.profile = null;
      clearToken();
      clearProfile();
    }
  }
});

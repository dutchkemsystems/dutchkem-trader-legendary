import { create } from "zustand";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
}

function getInitialToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export const useAuthStore = create<AuthState>((set) => ({
  token: getInitialToken(),
  isAuthenticated: !!getInitialToken(),
  login: (token: string) => {
    localStorage.setItem("token", token);
    set({ token, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, isAuthenticated: false });
  },
}));

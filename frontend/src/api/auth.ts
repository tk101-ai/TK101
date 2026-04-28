import api from "./client";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  department: string;
  role: string;
  is_active: boolean;
  created_at: string;
  modules: string[];
}

export const login = (data: LoginRequest) =>
  api.post<{ access_token: string; token_type: string }>("/api/auth/login", data);

export const getMe = () => api.get<User>("/api/auth/me");

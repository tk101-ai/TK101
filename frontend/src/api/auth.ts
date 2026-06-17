import api from "./client";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  department: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  department: string;
  departments?: string[];
  role: string;
  is_active: boolean;
  status: string;
  created_at: string;
  modules: string[];
}

export const login = (data: LoginRequest) =>
  api.post<{ access_token: string; token_type: string }>("/api/auth/login", data);

export const register = (data: RegisterRequest) =>
  api.post<User>("/api/auth/register", data);

export const getMe = () => api.get<User>("/api/auth/me");

export const logout = () => api.post<void>("/api/auth/logout");

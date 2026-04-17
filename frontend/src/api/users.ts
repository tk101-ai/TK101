import api from "./client";

export interface User {
  id: string;
  email: string;
  name: string;
  department: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface CreateUserRequest {
  email: string;
  password: string;
  name: string;
  department: string;
  role: string;
}

export interface UpdateUserRequest {
  name?: string;
  department?: string;
  role?: string;
  is_active?: boolean;
}

export const getUsers = () => api.get<User[]>("/api/users");

export const createUser = (data: CreateUserRequest) =>
  api.post<User>("/api/users", data);

export const updateUser = (userId: string, data: UpdateUserRequest) =>
  api.patch<User>(`/api/users/${userId}`, data);

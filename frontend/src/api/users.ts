import api from "./client";

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
}

export interface CreateUserRequest {
  email: string;
  password: string;
  name: string;
  department: string;
  role: string;
  departments?: string[];
}

export interface UpdateUserRequest {
  name?: string;
  department?: string;
  role?: string;
  is_active?: boolean;
  status?: string;
  departments?: string[];
}

export interface ApproveRequest {
  department: string;
  role: string;
  departments?: string[];
}

export const getUsers = (status?: string) =>
  api.get<User[]>("/api/users", { params: status ? { status } : undefined });

export const createUser = (data: CreateUserRequest) =>
  api.post<User>("/api/users", data);

export const updateUser = (userId: string, data: UpdateUserRequest) =>
  api.patch<User>(`/api/users/${userId}`, data);

export const approveUser = (userId: string, data: ApproveRequest) =>
  api.post<User>(`/api/users/${userId}/approve`, data);

export const rejectUser = (userId: string) =>
  api.post<User>(`/api/users/${userId}/reject`);

export const deleteUser = (userId: string) =>
  api.delete<void>(`/api/users/${userId}`);

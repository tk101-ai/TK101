import { Navigate } from "react-router-dom";
import type { ReactElement } from "react";
import type { User } from "../api/auth";

interface ProtectedRouteProps {
  user: User;
  module: string;
  role?: "admin";
  children: ReactElement;
}

export default function ProtectedRoute({ user, module, role, children }: ProtectedRouteProps) {
  const allowedModules = user.modules ?? [];
  if (!allowedModules.includes(module)) {
    return <Navigate to="/" replace />;
  }
  if (role && user.role !== role) {
    return <Navigate to="/" replace />;
  }
  return children;
}

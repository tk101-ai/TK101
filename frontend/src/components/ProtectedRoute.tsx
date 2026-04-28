import { Navigate } from "react-router-dom";
import type { ReactElement } from "react";
import type { User } from "../api/auth";

interface ProtectedRouteProps {
  user: User;
  module: string;
  children: ReactElement;
}

export default function ProtectedRoute({ user, module, children }: ProtectedRouteProps) {
  const allowedModules = user.modules ?? [];
  if (!allowedModules.includes(module)) {
    return <Navigate to="/" replace />;
  }
  return children;
}

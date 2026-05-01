import { useState, useEffect } from "react";
import { AUTH_TOKEN_KEY, AUTH_ROLE_KEY, AUTH_USER_KEY, API_BASE_URL } from "./constants";

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export function getDashboardPath(role) {
  if (role === "student") return "/student/dashboard";
  if (role === "super_admin") return "/admin/dashboard";
  if (role === "teacher" || role === "faculty") return "/faculty/dashboard";
  return "/login";
}

export function getStoredAuthRole() {
  return localStorage.getItem(AUTH_ROLE_KEY);
}

export function getStoredAuthUser() {
  try {
    const raw = localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function hasAuthToken() {
  return Boolean(localStorage.getItem(AUTH_TOKEN_KEY));
}

export function isFacultyRole(role) {
  return role === "teacher" || role === "super_admin" || role === "faculty";
}

export function toInitials(name, fallback = "F") {
  if (!name) return fallback;
  return String(name)
    .split(" ")
    .map((part) => part.trim()[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function buildProfileFromUser(user, fallbackRole = "faculty") {
  if (!user) {
    return {
      avatar: fallbackRole === "admin" ? "A" : "F",
      name: fallbackRole === "admin" ? "Admin" : "Faculty",
      meta: "",
      photoPath: "",
      role: fallbackRole,
    };
  }
  return {
    avatar: toInitials(user.name, fallbackRole === "admin" ? "A" : "F"),
    name: user.name || (fallbackRole === "admin" ? "Admin" : "Faculty"),
    meta: user.email || user.roll_no || "",
    photoPath: user.photoPath || user.photo_path || "",
    role: user.role || fallbackRole,
  };
}

export function persistAuth({ token, role, user }) {
  localStorage.setItem(AUTH_TOKEN_KEY, token || "session");
  localStorage.setItem(AUTH_ROLE_KEY, role);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("authChange"));
}

export function clearAuth() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_ROLE_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  window.dispatchEvent(new Event("authChange"));
}

export function useSessionProfile(fallbackRole = "faculty") {
  const [profile, setProfile] = useState(() => buildProfileFromUser(getStoredAuthUser(), fallbackRole));

  useEffect(() => {
    let mounted = true;

    async function hydrate() {
      try {
        const response = await fetch(apiUrl("/api/auth/whoami"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.authenticated || !mounted) return;

        persistAuth({ token: "session", role: payload.role, user: payload.user || {} });
        // state will be updated by the event listener below
      } catch {
        // keep cached profile
      }
    }

    hydrate();

    function handleAuthChange() {
      if (mounted) {
        setProfile(buildProfileFromUser(getStoredAuthUser(), fallbackRole));
      }
    }

    window.addEventListener("authChange", handleAuthChange);

    return () => {
      mounted = false;
      window.removeEventListener("authChange", handleAuthChange);
    };
  }, [fallbackRole]);

  return profile;
}

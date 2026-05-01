import React, { Fragment, useEffect, useMemo, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  FaArrowRightFromBracket, FaBars, FaHouse
} from "react-icons/fa6";
import { getStoredAuthRole, getStoredAuthUser, hasAuthToken, apiUrl, clearAuth, persistAuth, buildProfileFromUser } from "../utils/auth";
import { SIDEBAR_LOGO_URL, iconMap, THEME_KEY } from "../utils/constants";

function AuthGate({ roles, children }) {
  const [status, setStatus] = useState("checking");
  const localRole = getStoredAuthRole();

  useEffect(() => {
    let mounted = true;

    async function verify() {
      const localRole = getStoredAuthRole();
      const localTokenPresent = hasAuthToken();
      const localAuthAllowed = localTokenPresent && localRole && roles.some(r => String(r).toLowerCase() === String(localRole).toLowerCase());

      if (!localTokenPresent || !localRole) {
        if (mounted) setStatus("denied");
        return;
      }

      try {
        const response = await fetch(apiUrl("/api/auth/whoami"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));

        if (response.ok && payload.authenticated) {
          const role = payload.role;
          const isAllowed = roles.some(r => String(r).toLowerCase() === String(role || "").toLowerCase());

          if (!isAllowed) {
            console.warn(`AuthGate: Role "${role}" not in allowed list:`, roles);
            if (mounted) setStatus("denied");
            return;
          }

          persistAuth({ token: "session", role, user: payload.user || getStoredAuthUser() || {} });
          if (mounted) setStatus("allowed");
          return;
        }

        console.warn("AuthGate: Authenticated check failed", payload);
        clearAuth();
        if (mounted) setStatus("denied");
      } catch (err) {
        if (localAuthAllowed) {
          console.warn("AuthGate: whoami request failed, using cached auth state", err);
          if (mounted) setStatus("allowed");
          return;
        }

        console.error("AuthGate Exception:", err);
        clearAuth();
        if (mounted) setStatus("denied");
      }
    }

    verify();
    return () => {
      mounted = false;
    };
  }, [roles]);

  if (status === "checking") {
    const loadingVariant = String(localRole || "").toLowerCase() === "super_admin" ? "admin" : "faculty";
    return (
      <FullScreenPortalSkeleton variant={loadingVariant} />
    );
  }

  if (status === "denied") {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function RequireFacultyAuth({ children }) {
  return <AuthGate roles={["teacher", "super_admin", "faculty"]}>{children}</AuthGate>;
}

function RequireAdminAuth({ children }) {
  return <AuthGate roles={["super_admin"]}>{children}</AuthGate>;
}

function PageShell({ variant, nav, title, subtitle, profile, actions, sidebarAction, children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [theme, setTheme] = useState(() => {
    if (typeof document !== "undefined") {
      if (document.body.classList.contains("dark")) return "dark";
      if (document.body.classList.contains("light")) return "light";
    }
    return localStorage.getItem(THEME_KEY) || "light";
  });
  const location = useLocation();
  const storedUser = getStoredAuthUser();
  const storedRole = getStoredAuthRole();

  const authDrivenProfile =
    variant === "faculty" || variant === "admin"
      ? buildProfileFromUser(storedUser, variant === "admin" ? "admin" : "faculty")
      : profile;

  const effectiveProfile = {
    ...profile,
    ...authDrivenProfile,
    avatar: authDrivenProfile?.avatar || profile?.avatar || "U",
    name: authDrivenProfile?.name || profile?.name || "User",
    meta: authDrivenProfile?.meta || profile?.meta || "",
    photoPath: authDrivenProfile?.photoPath || profile?.photoPath || "",
  };

  const effectiveNav = useMemo(() => {
    // Hide admin shortcut for non-admin faculty users to keep sidebar focused.
    if (variant === "faculty" && String(storedRole || "").toLowerCase() !== "super_admin") {
      return nav.filter((item) => item.to !== "/admin/dashboard");
    }
    return nav;
  }, [nav, storedRole, variant]);

  const profileMenuItems = useMemo(() => {
    if (variant !== "faculty") return [];

    const items = [{ label: "Profile", to: "/faculty/profile" }];
    if (String(storedRole || "").toLowerCase() === "super_admin") {
      items.push({ label: "Admin Dashboard", to: "/admin/dashboard" });
    }
    return items;
  }, [variant, storedRole]);

  useEffect(() => {
    setProfileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.classList.remove("light", "dark");
    document.body.classList.add(theme);
    localStorage.setItem(THEME_KEY, theme);
    window.dispatchEvent(new CustomEvent("theme-change", { detail: { theme } }));
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const isNavItemActive = (targetPath) => {
    if (!targetPath) return false;
    if (location.pathname === targetPath) return true;
    return location.pathname.startsWith(`${targetPath}/`);
  };

  return (
    <div className={`portal-shell ${variant}`}>
      <div
        className={`sidebar-overlay${sidebarOpen ? " show" : ""}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />
      <aside className={`portal-sidebar${sidebarOpen ? " open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-mark">
             <img src={SIDEBAR_LOGO_URL} alt="FaceMarkPro" />
          </div>
          <div className="brand-copy">
            <div className="brand-title">
              <span>FaceMark</span>
              <span className="accent">Pro</span>
            </div>
            <p className="brand-subtitle">Your face is your Attendance</p>
          </div>
        </div>

        <div
          className={`profile-section ${profileMenuItems.length ? "profile-trigger" : ""}`}
          onClick={() => {
            if (profileMenuItems.length) setProfileMenuOpen((open) => !open);
          }}
          role={profileMenuItems.length ? "button" : undefined}
          tabIndex={profileMenuItems.length ? 0 : undefined}
          onKeyDown={(event) => {
            if (!profileMenuItems.length) return;
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setProfileMenuOpen((open) => !open);
            }
          }}
        >
          <div className="profile-photo">
            {effectiveProfile.photoPath ? (
              <img src={effectiveProfile.photoPath} alt={effectiveProfile.name} />
            ) : (
              effectiveProfile.avatar
            )}
          </div>
          <div className="profile-copy">
            <h5>{effectiveProfile.name}</h5>
            {effectiveProfile.meta ? <p>{effectiveProfile.meta}</p> : null}
          </div>
        </div>

        {profileMenuItems.length && profileMenuOpen ? (
          <div className="profile-dropdown">
            {profileMenuItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="profile-dropdown-link"
                onClick={() => {
                  setSidebarOpen(false);
                  setProfileMenuOpen(false);
                }}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ) : null}


        <nav className="nav-links">
          {effectiveNav.map((item, index) => {
            const Icon = iconMap[item.icon];
            const link = (
              <Link
                key={item.to}
                to={item.to}
                className={`nav-link${isNavItemActive(item.to) ? " active" : ""}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="nav-icon">{Icon ? <Icon /> : "*"}</span>
                <span>{item.label}</span>
              </Link>
            );

            if (index === 0 && sidebarAction) {
              return (
                <div key={`${item.to}-row`} className="sidebar-top-action-row">
                  {link}
                  {sidebarAction}
                </div>
              );
            }

            return link;
          })}
        </nav>

        <div className="sidebar-footer">
          {variant === "faculty" && String(storedRole || "").toLowerCase() === "super_admin" ? (
            <Link
              to="/admin/dashboard"
              className={`nav-link nav-link-dashboard${isNavItemActive("/admin/dashboard") ? " active" : ""}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="nav-icon">
                <FaHouse />
              </span>
              <span>Admin Dashboard</span>
            </Link>
          ) : null}
          <div className="sidebar-footer-row">
              <Link
                to="/login"
                className="nav-link logout-link"
                onClick={() => {
                  clearAuth();
                  setSidebarOpen(false);
                }}
              >
              <span className="nav-icon">
                <FaArrowRightFromBracket />
              </span>
              <span>Logout</span>
            </Link>
            <button
              type="button"
              className={`sidebar-mini-switch ${theme === "dark" ? "is-dark" : ""}`}
              aria-label="Toggle day and night mode"
              aria-pressed={theme === "dark"}
              onClick={toggleTheme}
            >
              <span />
            </button>
          </div>
        </div>
      </aside>

      <main className="portal-main">
        <header className="page-header">
          <div className="page-heading">
            <button className="sidebar-toggle" type="button" onClick={() => setSidebarOpen(true)}>
              <FaBars />
            </button>
            <div>
              <h1>{title}</h1>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
          </div>
          {actions ? <div className="page-actions">{actions}</div> : null}
        </header>
        {children}
      </main>
    </div>
  );
}

function SectionCard({ title, action, children, className = "" }) {
  return (
    <section className={`content-card ${className}`}>
      {(title || action) && (
        <div className="section-head">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function StatGrid({ stats }) {
  return (
    <div className="stats-grid">
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <article key={stat.label} className="stat-card">
            <div className="stat-copy">
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </div>
            <div className={`stat-icon tone-${stat.tone}`} aria-hidden="true">
              {Icon ? <Icon /> : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function SimpleTable({ columns, rows }) {
  return (
    <div className="table-wrap">
      <table className="simple-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProfileFields({ items }) {
  return (
    <div className="profile-fields">
      {items.map(([label, value]) => (
        <div key={label} className="field-row">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function FormGrid({ fields, action }) {
  return (
    <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
      <div className="field-grid">
        {fields.map((field) => (
          <label key={field.label} className="field-label">
            <span>{field.label}</span>
            <input type={field.type} placeholder={field.placeholder || ""} />
          </label>
        ))}
      </div>
      <button className="primary-btn" type="submit">
        {action}
      </button>
    </form>
  );
}

function SkeletonBlock({ className = "" }) {
  return <div className={`skeleton-block ${className}`.trim()} />;
}

function TableSkeleton({ rows = 5, columns = 4, className = "" }) {
  const rowStyle = { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` };

  return (
    <div className={`table-wrap skeleton-table-wrap ${className}`.trim()}>
      <div className="table-skeleton-grid" role="presentation">
        <div className="table-skeleton-row table-skeleton-row-head" style={rowStyle}>
          {Array.from({ length: columns }, (_, index) => (
            <div key={`head-${index}`} className="table-skeleton-cell">
              <SkeletonBlock className="skeleton-line skeleton-cell-head" />
            </div>
          ))}
        </div>

        {Array.from({ length: rows }, (_, rowIndex) => (
          <div key={`row-${rowIndex}`} className="table-skeleton-row" style={rowStyle}>
            {Array.from({ length: columns }, (_, colIndex) => (
              <div key={`cell-${rowIndex}-${colIndex}`} className="table-skeleton-cell">
                <SkeletonBlock className={`skeleton-line skeleton-cell${colIndex === 0 ? " short" : ""}`} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function FilterSkeleton({ fields = 6 }) {
  return (
    <div className="report-filter-grid">
      {Array.from({ length: fields }, (_, index) => (
        <div key={`filter-${index}`} className="field-label skeleton-filter-item">
          <SkeletonBlock className="skeleton-line skeleton-label" />
          <SkeletonBlock className="skeleton-input" />
        </div>
      ))}
    </div>
  );
}

function DashboardSkeleton({ variant = "faculty" }) {
  if (variant === "student") {
    return (
      <div className="dashboard-skeleton student">
        <div className="dashboard-skeleton-stats">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={`student-stat-${index}`} className="dashboard-skeleton-card stat">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="skeleton-line skeleton-text short" />
            </div>
          ))}
        </div>

        <div className="dashboard-skeleton-grid student-grid">
          <div className="dashboard-skeleton-card schedule">
            <SkeletonBlock className="skeleton-line skeleton-title" />
            <SkeletonBlock className="skeleton-table-bars" />
            <SkeletonBlock className="skeleton-table-bars" />
            <SkeletonBlock className="skeleton-table-bars short" />
          </div>

          <div className="dashboard-skeleton-card attendance">
            <SkeletonBlock className="skeleton-line skeleton-title" />
            <SkeletonBlock className="skeleton-chart" />
          </div>

          <div className="dashboard-skeleton-card timetable">
            <SkeletonBlock className="skeleton-line skeleton-title" />
            <SkeletonBlock className="skeleton-chart" />
          </div>

          <div className="dashboard-skeleton-card actions">
            <SkeletonBlock className="skeleton-line skeleton-title short" />
            <SkeletonBlock className="skeleton-line skeleton-text" />
            <SkeletonBlock className="skeleton-line skeleton-text" />
            <SkeletonBlock className="skeleton-line skeleton-text short" />
          </div>

          <div className="dashboard-skeleton-card summary">
            <SkeletonBlock className="skeleton-line skeleton-title" />
            <SkeletonBlock className="skeleton-table-bars" />
            <SkeletonBlock className="skeleton-table-bars" />
            <SkeletonBlock className="skeleton-table-bars short" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-skeleton faculty">
      <div className="dashboard-skeleton-grid">
        <div className="dashboard-skeleton-card hero">
          <SkeletonBlock className="skeleton-line skeleton-title" />
          <SkeletonBlock className="skeleton-line skeleton-text" />
          <SkeletonBlock className="skeleton-chart" />
        </div>
        <div className="dashboard-skeleton-card side">
          <SkeletonBlock className="skeleton-line skeleton-title short" />
          <SkeletonBlock className="skeleton-line skeleton-text short" />
          <SkeletonBlock className="skeleton-line skeleton-text" />
        </div>
        <div className="dashboard-skeleton-card chart">
          <SkeletonBlock className="skeleton-line skeleton-title" />
          <SkeletonBlock className="skeleton-chart" />
        </div>
        <div className="dashboard-skeleton-card table">
          <SkeletonBlock className="skeleton-line skeleton-title" />
          <SkeletonBlock className="skeleton-table-bars" />
          <SkeletonBlock className="skeleton-table-bars" />
          <SkeletonBlock className="skeleton-table-bars short" />
        </div>
      </div>
    </div>
  );
}

function FullScreenPortalSkeleton({ variant = "faculty" }) {
  return (
    <div className={`portal-shell portal-loading-screen ${variant}`}>
      <aside className="portal-sidebar portal-sidebar-skeleton">
        <div className="sidebar-brand">
          <div className="brand-mark portal-skeleton-square">
            <SkeletonBlock className="portal-skeleton-fill" />
          </div>
          <div className="portal-skeleton-copy">
            <SkeletonBlock className="skeleton-line skeleton-title short" />
            <SkeletonBlock className="skeleton-line skeleton-text short" />
          </div>
        </div>

        <div className="profile-section portal-skeleton-profile">
          <div className="profile-photo portal-skeleton-avatar">
            <SkeletonBlock className="portal-skeleton-fill" />
          </div>
          <div className="portal-skeleton-copy">
            <SkeletonBlock className="skeleton-line skeleton-title short" />
            <SkeletonBlock className="skeleton-line skeleton-text short" />
          </div>
        </div>

        <div className="nav-links portal-skeleton-nav">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              key={`nav-skeleton-${index}`}
              className={`nav-link portal-skeleton-nav-item${index === 0 ? " active" : ""}`}
            >
              <span className="nav-icon portal-skeleton-icon">
                <SkeletonBlock className="portal-skeleton-fill" />
              </span>
              <SkeletonBlock className={`skeleton-line${index === 0 ? " short" : ""}`} />
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-row portal-skeleton-footer">
            <SkeletonBlock className="portal-skeleton-logout" />
            <SkeletonBlock className="portal-skeleton-toggle" />
          </div>
        </div>
      </aside>

      <main className="portal-main portal-main-skeleton">
        <header className="page-header portal-skeleton-header">
          <div className="page-heading portal-skeleton-heading">
            <div>
              <SkeletonBlock className="skeleton-line portal-skeleton-page-title" />
              <SkeletonBlock className="skeleton-line portal-skeleton-page-subtitle" />
            </div>
          </div>
          <SkeletonBlock className="portal-skeleton-header-action" />
        </header>

        <div className="portal-skeleton-dashboard">
          <div className="portal-skeleton-grid top">
            <div className="dashboard-skeleton-card portal-skeleton-card wide">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="portal-skeleton-widget-bar" />
              <SkeletonBlock className="portal-skeleton-timetable" />
            </div>
            <div className="portal-skeleton-column">
              <div className="dashboard-skeleton-card portal-skeleton-card">
                <SkeletonBlock className="skeleton-line skeleton-title short" />
                <SkeletonBlock className="portal-skeleton-hero-card" />
              </div>
              <div className="portal-skeleton-grid compact">
                <div className="dashboard-skeleton-card portal-skeleton-card compact">
                  <SkeletonBlock className="skeleton-line skeleton-title short" />
                  <SkeletonBlock className="skeleton-line skeleton-text short" />
                  <SkeletonBlock className="skeleton-line skeleton-text short" />
                </div>
                <div className="dashboard-skeleton-card portal-skeleton-card compact">
                  <SkeletonBlock className="skeleton-line skeleton-title short" />
                  <SkeletonBlock className="portal-skeleton-widget-bar" />
                  <SkeletonBlock className="skeleton-line skeleton-text" />
                </div>
              </div>
            </div>
          </div>

          <div className="portal-skeleton-grid middle">
            <div className="dashboard-skeleton-card portal-skeleton-card">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="portal-skeleton-widget-bar" />
              <SkeletonBlock className="skeleton-chart portal-skeleton-chart-tall" />
            </div>
            <div className="dashboard-skeleton-card portal-skeleton-card">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="portal-skeleton-widget-bar" />
              <SkeletonBlock className="skeleton-chart portal-skeleton-chart-medium" />
            </div>
          </div>

          <div className="portal-skeleton-grid bottom">
            <div className="dashboard-skeleton-card portal-skeleton-card">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="portal-skeleton-widget-bar" />
              <SkeletonBlock className="portal-skeleton-calendar" />
            </div>
            <div className="dashboard-skeleton-card portal-skeleton-card">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="skeleton-line skeleton-text" />
              <SkeletonBlock className="skeleton-line skeleton-text" />
              <SkeletonBlock className="skeleton-line skeleton-text short" />
            </div>
            <div className="dashboard-skeleton-card portal-skeleton-card">
              <SkeletonBlock className="skeleton-line skeleton-title short" />
              <SkeletonBlock className="portal-skeleton-widget-bar" />
              <SkeletonBlock className="skeleton-line skeleton-text" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export { AuthGate, RequireFacultyAuth, RequireAdminAuth, PageShell, SectionCard, StatGrid, SimpleTable, ProfileFields, FormGrid, SkeletonBlock, TableSkeleton, FilterSkeleton, DashboardSkeleton, FullScreenPortalSkeleton };

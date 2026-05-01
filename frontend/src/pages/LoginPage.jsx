import React, { Fragment, useEffect, useMemo, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Responsive, WidthProvider } from "react-grid-layout";
import {
  FaArrowRightFromBracket, FaBars, FaCalendarDays, FaCamera, FaChartLine,
  FaEye, FaEyeSlash, FaGear, FaHouse, FaPlus, FaUpload, FaUserCheck,
  FaUserGear, FaUserGraduate, FaUserPen, FaUsers, FaVideo, FaPlay
} from "react-icons/fa6";

import { apiUrl, getDashboardPath, getStoredAuthRole, getStoredAuthUser, hasAuthToken, persistAuth, useSessionProfile, isFacultyRole } from "../utils/auth";
import { adminNav, facultyNav, studentNav, studentStats, adminStats, facultyStats, todaysClasses, recentAttendance, facultyStudents, weeklyTimetable, FACULTY_DASHBOARD_KEY, FACULTY_GRID_COLS, defaultFacultyWidgets, facultyWidgetCatalog, FACULTY_KEY, STUDENT_KEY, SIDEBAR_LOGO_URL } from "../utils/constants";
import { normalizeFacultyLayout, getWidgetSizeClass } from "../utils/constants";
import { PageShell, SectionCard, StatGrid, SimpleTable, ProfileFields, FormGrid } from "../components/Shared";

function LoginPage({ theme, setTheme, defaultRoute }) {
  const navigate = useNavigate();
  const [activeRole, setActiveRole] = useState("faculty");
  const [facultyEmail, setFacultyEmail] = useState(() => localStorage.getItem(FACULTY_KEY) || "");
  const [facultyPassword, setFacultyPassword] = useState("");
  const [rememberFaculty, setRememberFaculty] = useState(!!localStorage.getItem(FACULTY_KEY));
  const [showFacultyPw, setShowFacultyPw] = useState(false);
  const [studentRoll, setStudentRoll] = useState(() => localStorage.getItem(STUDENT_KEY) || "");
  const [studentPassword, setStudentPassword] = useState("");
  const [rememberStudent, setRememberStudent] = useState(!!localStorage.getItem(STUDENT_KEY));
  const [showStudentPw, setShowStudentPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const isDark = theme === "dark";

  function storeLoginCredential(username, password, displayName) {
    if (typeof window === "undefined") return;
    const credentialApi = navigator.credentials;
    if (!credentialApi || typeof credentialApi.store !== "function") return;

    try {
      const PasswordCredentialCtor = window.PasswordCredential;
      if (!PasswordCredentialCtor) return;
      const credential = new PasswordCredentialCtor({
        id: username,
        password,
        name: displayName || username,
      });
      credentialApi.store(credential);
    } catch (error) {
      console.debug("Credential save not supported:", error);
    }
  }

  /*
  useEffect(() => {
    const role = getStoredAuthRole();
    if (hasAuthToken() && role) {
      if (role === "student") {
        navigate("/student/dashboard", { replace: true });
      } else {
        // Faculty or Admin
        navigate("/faculty/dashboard", { replace: true });
      }
    }
  }, [navigate]);
  */

  async function handleFacultyLogin(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/auth/login/faculty"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email: facultyEmail, password: facultyPassword }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok && data.success) {
        const role = data.role || "faculty";
        const user = data.user || {};
        
        persistAuth({ token: data.token || "session", role: role, user: user });
        
        if (rememberFaculty) localStorage.setItem(FACULTY_KEY, facultyEmail);
        else localStorage.removeItem(FACULTY_KEY);

        storeLoginCredential(facultyEmail, facultyPassword, user?.name || user?.full_name || "FaceMark Pro");

        const dest = data.redirectPath || data.redirect_path || getDashboardPath(role);
        navigate(dest, { replace: true });
      } else {
        setError(data.message || (data.errors && data.errors[0]) || "Invalid credentials.");
      }
    } catch (err) {
      console.error("Login Error:", err);
      setError("Network error. Please ensure the backend is running.");
    } finally { setLoading(false); }
  }

  async function handleStudentLogin(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/auth/login/student"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ roll_no: studentRoll, password: studentPassword }),
      });
      const data = await res.json().catch(() => ({}));
      
      if (res.ok && data.success) {
        const role = "student";
        persistAuth({ token: data.token || "session", role: role, user: data.user || {} });
        
        if (rememberStudent) localStorage.setItem(STUDENT_KEY, studentRoll);
        else localStorage.removeItem(STUDENT_KEY);

        storeLoginCredential(studentRoll, studentPassword, data.user?.name || data.user?.full_name || "FaceMark Pro");

        const dest = data.redirectPath || data.redirect_path || "/student/dashboard";
        navigate(dest, { replace: true });
      } else {
        setError(data.message || (data.errors && data.errors[0]) || "Invalid credentials.");
      }
    } catch (err) {
      console.error("Student Login Error:", err);
      setError("Network error. Please ensure the backend is running.");
    } finally { setLoading(false); }
  }

  return (
    <div className={`login-page-wrap ${isDark ? "lp-dark" : "lp-light"}`}>
      {/* Loading Overlay */}
      {loading && (
        <div className="lp-loading-overlay">
          <div className="lp-lds-ripple"><div></div><div></div></div>
          <p className="lp-loading-text">Logging in...</p>
        </div>
      )}

      {/* Theme Toggle */}
      <div className="lp-theme-container">
        <label className="lp-theme-switch">
          <input 
            type="checkbox" 
            checked={isDark} 
            onChange={() => setTheme(isDark ? "light" : "dark")} 
          />
          <div className="lp-ts-container">
            <div className="lp-ts-clouds"></div>
            <div className="lp-ts-stars">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 144 55" fill="none">
                <path fillRule="evenodd" clipRule="evenodd" d="M22 10a1 1 0 100-2 1 1 0 000 2zm40 5a1 1 0 100-2 1 1 0 000 2zm30 15a1 1 0 100-2 1 1 0 000 2zm-50 10a1 1 0 100-2 1 1 0 000 2zm70-15a1 1 0 100-2 1 1 0 000 2z" fill="currentColor"></path>
              </svg>
            </div>
            <div className="lp-ts-circle">
              <div className="lp-ts-sun-moon">
                <div className="lp-ts-moon-spots">
                  <div className="lp-ts-spot"></div>
                  <div className="lp-ts-spot"></div>
                  <div className="lp-ts-spot"></div>
                </div>
              </div>
            </div>
          </div>
        </label>
      </div>

      <div className="lp-container anim-group">
        <div className="lp-brand-box lp-anim-item in" style={{ animationDelay: "100ms" }}>
          <div className="lp-brand-logo-wrap">
            <img src={SIDEBAR_LOGO_URL} alt="FaceMark Pro" className="lp-brand-logo-img" />
          </div>
          <div className="lp-brand-title">FaceMark Pro</div>
          <p className="lp-brand-subtitle">Your face is your Attendance</p>
          <h2 className="lp-welcome-title">Welcome Back!</h2>
        </div>

        <div className="lp-role-toggle lp-anim-item in" style={{ animationDelay: "200ms" }}>
          <div className="lp-role-indicator" style={{ transform: activeRole === "student" ? "translateX(100%)" : "translateX(0)" }}></div>
          <button type="button" className={`lp-role-btn ${activeRole === "faculty" ? "active" : ""}`} onClick={() => { setActiveRole("faculty"); setError(""); }}>Faculty</button>
          <button type="button" className={`lp-role-btn ${activeRole === "student" ? "active" : ""}`} onClick={() => { setActiveRole("student"); setError(""); }}>Student</button>
        </div>

        {error && <div className="lp-error-box lp-anim-item in">{error}</div>}

        <div className="lp-anim-item in" style={{ animationDelay: "300ms" }}>
          {activeRole === "faculty" ? (
            <form onSubmit={handleFacultyLogin} className="lp-form">
              <h3 style={{ margin: "0 0 12px 0", fontSize: "18px" }}>Faculty Login</h3>
              <div className="lp-form-group">
                <input
                  type="text"
                  name="username"
                  className="lp-input"
                  placeholder="Email"
                  value={facultyEmail}
                  onChange={e => setFacultyEmail(e.target.value)}
                  autoComplete="username"
                  required
                />
              </div>
              <div className="lp-form-group">
                <input
                  type={showFacultyPw ? "text" : "password"}
                  name="password"
                  className="lp-input"
                  placeholder="Password"
                  value={facultyPassword}
                  onChange={e => setFacultyPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <button type="button" className="lp-eye-icon" onClick={() => setShowFacultyPw(v => !v)}>
                  {showFacultyPw ? <FaEyeSlash /> : <FaEye />}
                </button>
              </div>
              <label className="lp-remember-me">
                <input type="checkbox" checked={rememberFaculty} onChange={e => setRememberFaculty(e.target.checked)} />
                Remember Me
              </label>
              <button type="submit" className="lp-submit" disabled={loading}>Login</button>
            </form>
          ) : (
            <form onSubmit={handleStudentLogin} className="lp-form">
              <h3 style={{ margin: "16px 0 12px 0", fontSize: "18px" }}>Student Login</h3>
              <div className="lp-form-group">
                <input
                  type="text"
                  name="roll_no"
                  className="lp-input"
                  placeholder="Roll Number"
                  value={studentRoll}
                  onChange={e => setStudentRoll(e.target.value)}
                  autoComplete="username"
                  required
                />
                <small className="lp-input-hint">Use your unique ID (e.g. 24CSE01)</small>
              </div>
              <div className="lp-form-group">
                <input
                  type={showStudentPw ? "text" : "password"}
                  name="student_password"
                  className="lp-input"
                  placeholder="Password"
                  value={studentPassword}
                  onChange={e => setStudentPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <button type="button" className="lp-eye-icon" onClick={() => setShowStudentPw(v => !v)}>
                  {showStudentPw ? <FaEyeSlash /> : <FaEye />}
                </button>
              </div>
              <label className="lp-remember-me">
                <input type="checkbox" checked={rememberStudent} onChange={e => setRememberStudent(e.target.checked)} />
                Remember Me
              </label>
              <button type="submit" className="lp-submit" disabled={loading}>Login</button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default LoginPage;

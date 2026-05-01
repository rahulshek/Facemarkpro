import { FaArrowRightFromBracket, FaBars, FaCalendarDays, FaCamera, FaChartLine, FaEye, FaEyeSlash, FaGear, FaHouse, FaPlus, FaUpload, FaUserCheck, FaUserGear, FaUserGraduate, FaUserPen, FaUsers, FaVideo, FaPlay } from "react-icons/fa6";
import { Responsive, WidthProvider } from "react-grid-layout";

export const THEME_KEY = "theme";
export const FACULTY_KEY = "rememberedEmail";
export const STUDENT_KEY = "rememberedRollNo";
export const AUTH_TOKEN_KEY = "authToken";
export const AUTH_ROLE_KEY = "authRole";
export const AUTH_USER_KEY = "authUser";

function resolveApiBaseUrl() {
  // In dev, use same-origin so Vite proxy can forward /api to backend.
  // This also works with DevTunnel (phone access) where only port 5173 is exposed.
  if (import.meta.env.DEV) {
    return "";
  }

  const configured = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  if (!configured) return "";

  // In local dev, avoid localhost/127.0.0.1 host mismatch because it breaks cookie-based sessions.
  if (typeof window !== "undefined") {
    try {
      const parsed = new URL(configured);
      const apiHost = parsed.hostname.toLowerCase();
      const webHost = window.location.hostname.toLowerCase();
      const normalizeLocalHost = (host) => (host === "127.0.0.1" ? "localhost" : host);

      if (normalizeLocalHost(apiHost) !== normalizeLocalHost(webHost)) {
        return "";
      }
    } catch {
      return "";
    }
  }

  return configured;
}

export const API_BASE_URL = resolveApiBaseUrl();

import sidebarLogoRaw from "../../static/img/logo.svg";
export const SIDEBAR_LOGO_URL = sidebarLogoRaw;


export const adminNav = [
  { label: "Dashboard", to: "/admin/dashboard", icon: "home" },
  { label: "Academic Setup", to: "/admin/academic-setup", icon: "gear" },
  { label: "Faculty", to: "/admin/manage-faculty", icon: "users" },
  { label: "Students", to: "/admin/manage-students", icon: "graduation" },
  { label: "Face Reg.", to: "/admin/manage-faces", icon: "camera" },
  { label: "Reports", to: "/admin/reports", icon: "chart" },
];

export const facultyNav = [
  { label: "Dashboard", to: "/faculty/dashboard", icon: "home" },
  { label: "Attendance", to: "/faculty/attendance", icon: "calendar" },
  { label: "Manual Attendance", to: "/faculty/manual-attendance", icon: "edit" },
  { label: "Reports", to: "/faculty/reports", icon: "chart" },
  { label: "Profile", to: "/faculty/profile", icon: "user" },
];

export const studentNav = [
  { label: "Dashboard", to: "/student/dashboard", icon: "home" },
  { label: "Attendance", to: "/student/attendance", icon: "chart" },
  { label: "Profile", to: "/student/profile", icon: "user" },
  { label: "Change Password", to: "/student/change-password", icon: "key" },
];

export const iconMap = {
  home: FaHouse,
  users: FaUsers,
  graduation: FaUserGraduate,
  camera: FaUserCheck,
  chart: FaChartLine,
  calendar: FaCalendarDays,
  edit: FaUserPen,
  user: FaUserGear,
  gear: FaGear,
  key: FaUserPen,
  logout: FaArrowRightFromBracket,
};

export const studentStats = [
  { value: "87%", label: "Overall Attendance", tone: "blue" },
  { value: "4", label: "Classes Today", tone: "amber" },
  { value: "6", label: "Total Subjects", tone: "cyan" },
  { value: "Active", label: "Status", tone: "green" },
];

export const adminStats = [
  { value: "24", label: "Total Faculty", tone: "purple" },
  { value: "640", label: "Total Students", tone: "blue" },
  { value: "100%", label: "System Health", tone: "green" },
];

export const facultyStats = [
  { value: "4", label: "Lectures Today", tone: "blue" },
  { value: "128", label: "Students", tone: "green" },
  { value: "92%", label: "Attendance Avg", tone: "purple" },
  { value: "3", label: "Pending Tasks", tone: "amber" },
];

export const todaysClasses = [
  { time: "09:00 - 10:00", subject: "DBMS", faculty: "R. Sharma" },
  { time: "10:15 - 11:15", subject: "Python", faculty: "N. Verma" },
  { time: "12:00 - 01:00", subject: "Maths", faculty: "S. Iyer" },
  { time: "02:00 - 03:00", subject: "SQL Lab", faculty: "A. Khan" },
];

export const recentAttendance = [
  { date: "2026-04-07", subject: "DBMS", status: "Present" },
  { date: "2026-04-06", subject: "Python", status: "Present" },
  { date: "2026-04-05", subject: "Maths", status: "Absent" },
  { date: "2026-04-04", subject: "SQL Lab", status: "Present" },
];

export const facultyStudents = [
  { rollNo: "22CS101", name: "Aditi Singh", branch: "CSE", semester: "6", section: "A" },
  { rollNo: "22CS102", name: "Rohan Das", branch: "CSE", semester: "6", section: "A" },
  { rollNo: "22CS103", name: "Megha Patel", branch: "CSE", semester: "6", section: "A" },
  { rollNo: "22CS104", name: "Sarthak Rao", branch: "CSE", semester: "6", section: "A" },
];

export const weeklyTimetable = [
  ["Monday", "DBMS", "Python", "Break", "Maths", "SQL Lab"],
  ["Tuesday", "Python", "DBMS", "Break", "English", "Project"],
  ["Wednesday", "Maths", "DBMS", "Break", "Python", "Lab"],
  ["Thursday", "SQL", "Maths", "Break", "DBMS", "Python"],
  ["Friday", "Project", "English", "Break", "Maths", "Seminar"],
];


export const ResponsiveGridLayout = WidthProvider(Responsive);
export const FACULTY_DASHBOARD_KEY = "facultyDashboardWidgets";
export const FACULTY_GRID_COLS = 12;

export const facultyWidgetCatalog = [
  { id: "timetable", title: "Timetable", icon: "Cal", size: { w: 7, h: 4 }, minSize: { w: 4, h: 3 } },
  { id: "current-lecture", title: "Current Lecture", icon: "Lec", size: { w: 5, h: 2 }, minSize: { w: 2, h: 2 } },
  { id: "attendance-overview", title: "Attendance Overview", icon: "Att", size: { w: 3, h: 2 }, minSize: { w: 3, h: 2 } },
  { id: "monthly-trend", title: "Monthly Attendance Trend", icon: "Trd", size: { w: 5, h: 4 }, minSize: { w: 4, h: 3 } },
  { id: "subject-attendance", title: "Subject-wise Attendance", icon: "Sub", size: { w: 5, h: 3 }, minSize: { w: 3, h: 2 } },
  { id: "attendance-heatmap", title: "Attendance Heatmap", icon: "Map", size: { w: 6, h: 4 }, minSize: { w: 4, h: 3 } },
  { id: "student-list", title: "Student List", icon: "Stu", size: { w: 4, h: 4 }, minSize: { w: 3, h: 3 } },
  { id: "notifications", title: "Notifications", icon: "Not", size: { w: 3, h: 3 }, minSize: { w: 2, h: 2 } },
  { id: "quick-stats", title: "Quick Stats", icon: "Qck", size: { w: 2, h: 2 }, minSize: { w: 2, h: 2 } },
  { id: "calendar", title: "Calendar", icon: "Day", size: { w: 4, h: 5 }, minSize: { w: 3, h: 4 } },
];

export const defaultFacultyWidgets = [
  { i: "timetable", x: 0, y: 0, w: 7, h: 4 },
  { i: "current-lecture", x: 7, y: 0, w: 5, h: 2 },
  { i: "attendance-overview", x: 9, y: 2, w: 3, h: 2 },
  { i: "quick-stats", x: 7, y: 2, w: 2, h: 2 },
  { i: "monthly-trend", x: 0, y: 4, w: 6, h: 4 },
  { i: "attendance-heatmap", x: 6, y: 4, w: 6, h: 4 },
  { i: "calendar", x: 0, y: 8, w: 4, h: 5 },
  { i: "notifications", x: 4, y: 8, w: 3, h: 3 },
  { i: "subject-attendance", x: 7, y: 8, w: 5, h: 3 },
];

export function normalizeFacultyLayout(layout) { return layout.map((item) => { const catalogItem = facultyWidgetCatalog.find((widget) => widget.id === item.i); const fallbackW = catalogItem?.size.w || 3; const fallbackH = catalogItem?.size.h || 3; const minW = Math.max(1, Math.min(Number(item.minW || catalogItem?.minSize?.w || 1), FACULTY_GRID_COLS)); const minH = Math.max(1, Number(item.minH || catalogItem?.minSize?.h || 1)); const safeW = Math.max(minW, Math.min(Number(item.w || fallbackW), FACULTY_GRID_COLS)); const safeX = Math.max(0, Math.min(Number(item.x || 0), FACULTY_GRID_COLS - safeW)); return { ...item, minW, minH, w: safeW, h: Math.max(minH, Number(item.h || fallbackH)), x: safeX, y: Math.max(0, Number(item.y || 0)), }; }); }
export function getWidgetSizeClass(layoutItem) { const width = Math.max(1, Number(layoutItem?.w || 0)); const height = Math.max(1, Number(layoutItem?.h || 0)); const shortSide = Math.min(width, height); const longSide = Math.max(width, height); const area = width * height; if (area <= 4 || (shortSide === 1 && area <= 6)) return "tiny"; if (area <= 9 || (shortSide <= 2 && longSide >= 4) || (shortSide <= 2 && area <= 12)) return "compact"; return "regular"; }

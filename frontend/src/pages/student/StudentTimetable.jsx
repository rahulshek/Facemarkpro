import React, { Fragment, useEffect, useMemo, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Responsive, WidthProvider } from "react-grid-layout";
import {
  FaArrowRightFromBracket, FaBars, FaCalendarDays, FaCamera, FaChartLine,
  FaEye, FaEyeSlash, FaGear, FaHouse, FaPlus, FaUpload, FaUserCheck,
  FaUserGear, FaUserGraduate, FaUserPen, FaUsers, FaVideo, FaPlay
} from "react-icons/fa6";

import { apiUrl, getDashboardPath, getStoredAuthRole, getStoredAuthUser, hasAuthToken, persistAuth, useSessionProfile, isFacultyRole } from "../../utils/auth";
import { adminNav, facultyNav, studentNav, studentStats, adminStats, facultyStats, todaysClasses, recentAttendance, facultyStudents, weeklyTimetable, FACULTY_DASHBOARD_KEY, FACULTY_GRID_COLS, defaultFacultyWidgets, facultyWidgetCatalog, FACULTY_KEY, STUDENT_KEY, SIDEBAR_LOGO_URL } from "../../utils/constants";
import { normalizeFacultyLayout, getWidgetSizeClass } from "../../utils/constants";
import { PageShell, SectionCard, StatGrid, SimpleTable, ProfileFields, FormGrid, DashboardSkeleton } from "../../components/Shared";

const DEFAULT_WEEKLY_HEADERS = ["09:00", "10:00", "11:00", "12:00", "02:00"];

function StudentTimetable() {
  const profile = useSessionProfile("student");
  const [loading, setLoading] = useState(true);
  const [timetable, setTimetable] = useState([]);
  const [headers, setHeaders] = useState(DEFAULT_WEEKLY_HEADERS);

  useEffect(() => {
    async function fetchTimetable() {
      try {
        setLoading(true);
        const res = await fetch(apiUrl("/api/student/dashboard"), {
          method: "GET",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        if (res.ok) {
          const json = await res.json();
          if (json.success) {
            setTimetable(json.weeklyTimetable || []);
            setHeaders(json.weeklyHeaders || DEFAULT_WEEKLY_HEADERS);
          }
        }
      } catch (err) {
        console.error("Failed to fetch timetable:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchTimetable();
  }, []);

  if (loading) {
    return <DashboardSkeleton variant="student" />;
  }

  const effectiveTimetable = timetable.length > 0 ? timetable : weeklyTimetable;
  const effectiveHeaders = headers.length > 0 ? headers : DEFAULT_WEEKLY_HEADERS;

  return (
    <PageShell
      variant="student"
      nav={studentNav}
      title="Student Timetable"
      subtitle="Your personalized weekly class schedule."
      profile={profile}
    >
      <SectionCard title="Weekly Timetable">
        <div className="table-wrap">
          <table className="matrix-table timetable">
            <thead>
              <tr>
                <th>Day</th>
                {effectiveHeaders.map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {effectiveTimetable.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  {row.map((cell, cellIdx) => (
                    <td
                      key={`${rowIdx}-${cellIdx}`}
                      className={cellIdx === 0 ? "day-cell" : "slot-cell"}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </PageShell>
  );
}

export default StudentTimetable;

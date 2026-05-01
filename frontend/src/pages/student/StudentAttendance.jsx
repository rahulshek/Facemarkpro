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

function StudentAttendance() {
  const profile = useSessionProfile("student");
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    detailedAttendance: [],
    overallStats: { semester: "0%", bestSubject: "0%", needsFocus: "0%" },
    recentAttendance: [],
  });

  useEffect(() => {
    async function fetchAttendance() {
      try {
        setLoading(true);
        const res = await fetch(apiUrl("/api/student/attendance"), {
          method: "GET",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        if (res.ok) {
          const json = await res.json();
          if (json.success) {
            setData({
              detailedAttendance: json.detailedAttendance || [],
              overallStats: json.overallStats || { semester: "0%", bestSubject: "0%", needsFocus: "0%" },
              recentAttendance: json.recentAttendance || [],
            });
          }
        }
      } catch (err) {
        console.error("Failed to fetch attendance:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchAttendance();
  }, []);

  if (loading) {
    return <DashboardSkeleton variant="student" />;
  }

  return (
    <PageShell
      variant="student"
      nav={studentNav}
      title="Attendance Overview"
      subtitle="Subject-wise attendance, recent records, and semester summary."
      profile={profile}
    >
      <StatGrid
        stats={[
          { value: data.overallStats.semester, label: "Semester", tone: "blue" },
          { value: data.overallStats.bestSubject, label: "Best Subject", tone: "green" },
          { value: data.overallStats.needsFocus, label: "Needs Focus", tone: "amber" },
        ]}
      />
      <div className="content-grid two">
        <SectionCard title="By Subject">
          {data.detailedAttendance.length > 0 ? (
            <SimpleTable
              columns={["Subject", "Attendance", "Trend"]}
              rows={data.detailedAttendance.map((row) => {
                let badgeClass = "neutral";
                if (row.trend === "Critical") badgeClass = "danger";
                else if (row.trend === "Watch") badgeClass = "warning";
                else if (row.trend === "Good") badgeClass = "info";
                else if (row.trend === "Excellent") badgeClass = "success";
                
                return [
                  row.subject,
                  row.attendance,
                  <span key={row.subject} className={`trend-badge ${badgeClass}`}>{row.trend}</span>
                ];
              })}
            />
          ) : (
            <p className="no-data-msg">No subject-wise attendance data found.</p>
          )}
        </SectionCard>
        <SectionCard title="Recent Records">
          {data.recentAttendance.length > 0 ? (
            <SimpleTable
              columns={["Date", "Subject", "Status"]}
              rows={data.recentAttendance.map((row) => [row.date, row.subject, row.status])}
            />
          ) : (
            <p className="no-data-msg">No recent attendance records found.</p>
          )}
        </SectionCard>
      </div>
    </PageShell>
  );
}

export default StudentAttendance;

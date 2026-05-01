import React, { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  FaCalendarDays, FaChartLine, FaClock, FaCircleCheck, FaCircleXmark,
  FaBook, FaUserCheck, FaArrowRight
} from "react-icons/fa6";

import { apiUrl, getStoredAuthUser, useSessionProfile } from "../../utils/auth";
import { studentNav, todaysClasses, recentAttendance, weeklyTimetable } from "../../utils/constants";
import { PageShell, SectionCard, StatGrid, SimpleTable, DashboardSkeleton } from "../../components/Shared";

const DEFAULT_WEEKLY_HEADERS = ["09:00", "10:00", "11:00", "12:00", "02:00"];

function StudentDashboard() {
  const profile = useSessionProfile("student");
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState({
    todayClasses: [],
    upcomingClasses: [],
    attendanceSummary: { present: 0, absent: 0, total: 0 },
    recentAttendance: [],
    weeklyHeaders: DEFAULT_WEEKLY_HEADERS,
    weeklyTimetable: [],
  });
  const [usingFallbackData, setUsingFallbackData] = useState(false);

  useEffect(() => {
    async function fetchDashboardData() {
      try {
        setLoading(true);
        const webResponse = await fetch(apiUrl("/api/student/dashboard"), {
          method: "GET",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });

        if (webResponse.ok) {
          const data = await webResponse.json();
          const summary = data.attendanceSummary || { present: 0, absent: 0, total: 0 };
          setDashboardData({
            todayClasses: data.todayClasses || data.todayAttendance || [],
            upcomingClasses: data.upcomingClasses || [],
            attendanceSummary: summary,
            recentAttendance: data.recentAttendance || [],
            weeklyHeaders: data.weeklyHeaders || DEFAULT_WEEKLY_HEADERS,
            weeklyTimetable: data.weeklyTimetable || [],
          });
          setUsingFallbackData(false);
          return;
        }

        setUsingFallbackData(true);
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error);
        setUsingFallbackData(true);
      } finally {
        setLoading(false);
      }
    }

    fetchDashboardData();
  }, []);

  if (loading) {
    return <DashboardSkeleton variant="student" />;
  }

  const storedUser = getStoredAuthUser();
  const displayName = storedUser?.name || storedUser?.roll_no || "Student";
  const displayMeta = storedUser?.branch ? `${storedUser.branch} / ${storedUser.semester || "Semester"}` : "Student";

  const effectiveRecentAttendance = (dashboardData.recentAttendance.length > 0 || !usingFallbackData) ? dashboardData.recentAttendance : recentAttendance;
  const effectiveTodayClasses = (dashboardData.todayClasses.length > 0 || !usingFallbackData) ? dashboardData.todayClasses : todaysClasses;
  const effectiveWeeklyTimetable = (dashboardData.weeklyTimetable.length > 0 || !usingFallbackData) ? dashboardData.weeklyTimetable : weeklyTimetable;
  const effectiveWeeklyHeaders = (dashboardData.weeklyHeaders.length > 0 || !usingFallbackData) ? dashboardData.weeklyHeaders : DEFAULT_WEEKLY_HEADERS;

  const derivedPresent = dashboardData.attendanceSummary.present || (usingFallbackData ? effectiveRecentAttendance.filter((row) => String(row.status).toLowerCase() === "present").length : 0);
  const derivedAbsent = dashboardData.attendanceSummary.absent || (usingFallbackData ? effectiveRecentAttendance.filter((row) => String(row.status).toLowerCase() === "absent").length : 0);
  const derivedTotal = dashboardData.attendanceSummary.total || (derivedPresent + derivedAbsent);
  const derivedPercentage = derivedTotal > 0 ? Math.round((derivedPresent / derivedTotal) * 100) : 0;

  const enhancedStats = [
    {
      label: "Present",
      value: derivedPresent,
      tone: "success",
    },
    {
      label: "Absent",
      value: derivedAbsent,
      tone: "danger",
    },
    {
      label: "Total Classes",
      value: derivedTotal,
      tone: "info",
    },
    {
      label: "Attendance %",
      value: derivedPercentage,
      tone: "warning",
    },
  ];

  return (
    <PageShell
      variant="student"
      nav={studentNav}
      title={`Welcome back, ${displayName}!`}
      subtitle="Here's your attendance overview and schedule."
      profile={{
        avatar: displayName.charAt(0).toUpperCase(),
        name: displayName,
        meta: displayMeta,
      }}
    >
      <StatGrid stats={enhancedStats} />
      {usingFallbackData ? (
        <p className="dashboard-data-note">Showing fallback sample data because live dashboard API data is unavailable right now.</p>
      ) : null}

      <div className="student-dashboard-grid">
        {/* Weekly Timetable */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaBook />
              <span>Weekly Timetable</span>
            </span>
          }
          className="student-card timetable-card"
        >
          <p className="timetable-mobile-hint">Swipe left/right to view all columns.</p>
          <div className="timetable-wrap">
            <table className="modern-timetable">
              <thead>
                <tr>
                  <th>Day</th>
                  {effectiveWeeklyHeaders.map((slot) => (
                    <th key={`slot-${slot}`}>{slot}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {effectiveWeeklyTimetable && effectiveWeeklyTimetable.map((row, rowIdx) => (
                  <tr key={rowIdx}>
                    {row.map((cell, cellIdx) => (
                      <td key={`${rowIdx}-${cellIdx}`} className={cellIdx === 0 ? "day-cell" : cell === "Break" ? "break-cell" : "class-cell"}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* Recent Attendance */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaChartLine />
              <span>Recent Attendance</span>
            </span>
          }
          action={<Link to="/student/attendance" className="view-all-link">View All</Link>}
          className="student-card attendance-card"
        >
          {effectiveRecentAttendance && effectiveRecentAttendance.length > 0 ? (
            <SimpleTable
              columns={["Date", "Subject", "Status"]}
              rows={effectiveRecentAttendance.slice(0, 5).map((row) => [
                row.date,
                row.subject,
                <span
                  key={row.date}
                  className={`attendance-badge ${row.status === "Present" ? "present" : "absent"}`}
                >
                  {row.status === "Present" ? <FaCircleCheck /> : <FaCircleXmark />}
                  {row.status}
                </span>,
              ])}
            />
          ) : (
            <div className="empty-state">
              <FaChartLine size={48} />
              <p>No attendance records available</p>
            </div>
          )}
        </SectionCard>

        {/* Today's Schedule */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaCalendarDays />
              <span>Today's Schedule</span>
            </span>
          }
          className="student-card schedule-card"
        >
          {effectiveTodayClasses && effectiveTodayClasses.length > 0 ? (
            <div className="schedule-timeline">
              {effectiveTodayClasses.map((item) => (
                <div key={`${item.time}-${item.subject}`} className="timeline-item modern">
                  <div className="timeline-marker">
                    <FaClock size={14} />
                  </div>
                  <div className="timeline-content">
                    <div className="timeline-time">{item.time}</div>
                    <div className="timeline-subject">{item.subject}</div>
                    <div className="timeline-faculty">
                      <FaUserCheck size={12} /> Prof. {item.faculty}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <FaCalendarDays size={48} />
              <p>No classes scheduled for today</p>
            </div>
          )}
        </SectionCard>

        {/* Quick Actions */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaArrowRight />
              <span>Quick Actions</span>
            </span>
          }
          className="student-card actions-card"
        >
          <div className="quick-actions">
            <Link to="/student/attendance" className="action-button">
              <FaChartLine /> View Attendance
            </Link>
            <Link to="/student/profile" className="action-button">
              <FaUserCheck /> My Profile
            </Link>
            <Link to="/student/change-password" className="action-button">
              <FaUserCheck /> Change Password
            </Link>
          </div>
        </SectionCard>

        {/* Attendance Summary Chart */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaChartLine />
              <span>Attendance Overview</span>
            </span>
          }
          className="student-card summary-card"
        >
          <div className="attendance-summary-widget">
            <div className="summary-stat">
              <div className="summary-icon success">
                <FaCircleCheck />
              </div>
              <div className="summary-text">
                <strong>{derivedPresent}</strong>
                <small>Classes Attended</small>
              </div>
            </div>
            <div className="summary-stat">
              <div className="summary-icon danger">
                <FaCircleXmark />
              </div>
              <div className="summary-text">
                <strong>{derivedAbsent}</strong>
                <small>Classes Missed</small>
              </div>
            </div>
            <div className="summary-stat">
              <div className="summary-icon info">
                <FaBook />
              </div>
              <div className="summary-text">
                <strong>{derivedPercentage}%</strong>
                <small>Attendance Rate</small>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </PageShell>
  );
}

export default StudentDashboard;

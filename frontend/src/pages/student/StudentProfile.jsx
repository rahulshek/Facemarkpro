import React, { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  FaUser, FaEnvelope, FaPhone, FaMapPin, FaAward, FaBook, FaCamera,
  FaGraduationCap, FaCalendarDays, FaPencil, FaCircleCheck, FaChartLine, FaXmark, FaCheck
} from "react-icons/fa6";

import { getStoredAuthUser, useSessionProfile, apiUrl } from "../../utils/auth";
import { studentNav } from "../../utils/constants";
import { PageShell, SectionCard } from "../../components/Shared";

function StudentProfile() {
  const profile = useSessionProfile("student");
  const storedUser = getStoredAuthUser() || {};
  const [showEditModal, setShowEditModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  
  const [editForm, setEditForm] = useState({
    email: "",
    phone: "",
    address: "",
  });

  useEffect(() => {
    if (storedUser) {
      setEditForm({
        email: storedUser.email || "",
        phone: storedUser.phone || "",
        address: storedUser.address || "",
      });
    }
  }, [storedUser?.roll_no]);

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch(apiUrl("/api/auth/update-profile/student"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(editForm),
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setMessage("Profile updated successfully!");
        // Update local storage
        const updatedUser = { ...storedUser, ...data.contact };
        localStorage.setItem("facemark_auth_user", JSON.stringify(updatedUser));
        setTimeout(() => {
          setShowEditModal(false);
          setMessage("");
          window.location.reload(); // Refresh to show new data
        }, 1500);
      } else {
        setError(data.message || "Failed to update profile");
      }
    } catch (err) {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const displayName = storedUser?.name || storedUser?.roll_no || "Student";

  return (
    <PageShell
      variant="student"
      nav={studentNav}
      title="My Profile"
      subtitle="View and manage your student information."
      profile={profile}
      actions={
        <Link to="/student/dashboard" className="btn-secondary">
          ← Back to Dashboard
        </Link>
      }
    >
      <div className="student-profile-grid">
        {/* Profile Header Card */}
        <SectionCard className="student-profile-header">
          <div className="profile-header-content">
            <div className="profile-avatar-large">
              {storedUser?.photoPath ? (
                <img src={storedUser.photoPath} alt={displayName} />
              ) : (
                <span>{displayName.charAt(0).toUpperCase()}</span>
              )}
            </div>
            <div className="profile-header-info">
              <h2>{displayName}</h2>
              <p className="profile-role">
                <FaGraduationCap /> Student
              </p>
              <p className="profile-roll">{storedUser?.roll_no || "Roll No Not Set"}</p>
              <div className="profile-badges">
                {storedUser?.faceRegistered && (
                  <span className="badge badge-success">
                    <FaCircleCheck /> Face Registered
                  </span>
                )}
                <span className="badge badge-info">
                  <FaBook /> Active
                </span>
              </div>
            </div>
          </div>
        </SectionCard>

        {/* Academic Information */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaGraduationCap />
              <span>Academic Information</span>
            </span>
          }
          className="student-profile-card"
        >
          <div className="profile-info-grid three">
            <div className="info-item">
              <div className="info-label">
                <FaGraduationCap /> Branch
              </div>
              <div className="info-value">{storedUser?.branch || "Not Specified"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">
                <FaCalendarDays /> Semester
              </div>
              <div className="info-value">{storedUser?.semester || "Not Specified"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">
                <FaAward /> Section
              </div>
              <div className="info-value">{storedUser?.section || "Not Specified"}</div>
            </div>
          </div>
        </SectionCard>

        {/* Contact Information */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaEnvelope />
              <span>Contact Information</span>
            </span>
          }
          actions={
            <button className="btn-icon-text small" onClick={() => setShowEditModal(true)}>
              <FaPencil /> Edit Contact
            </button>
          }
          className="student-profile-card"
        >
          <div className="profile-info-grid two">
            <div className="info-item full-width">
              <div className="info-label">
                <FaEnvelope /> Email Address
              </div>
              <div className="info-value">{storedUser?.email || "Not Provided"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">
                <FaPhone /> Phone Number
              </div>
              <div className="info-value">{storedUser?.phone || "Not Provided"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">
                <FaMapPin /> Address
              </div>
              <div className="info-value">{storedUser?.address || "Not Provided"}</div>
            </div>
          </div>
        </SectionCard>

        {/* Face Recognition Status */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaCamera />
              <span>Face Recognition</span>
            </span>
          }
          className="student-profile-card"
        >
          <div className="face-recognition-section">
            <div className="face-status">
              {storedUser?.faceRegistered ? (
                <>
                  <div className="status-icon success">
                    <FaCircleCheck />
                  </div>
                  <div className="status-text">
                    <h4>Face Registered</h4>
                    <p>Your face is registered in the system for attendance marking.</p>
                  </div>
                </>
              ) : (
                <>
                  <div className="status-icon warning">
                    <FaCamera />
                  </div>
                  <div className="status-text">
                    <h4>Face Not Registered</h4>
                    <p>Please register your face to enable automated attendance marking.</p>
                  </div>
                </>
              )}
            </div>
          </div>
        </SectionCard>

        {/* Account Actions */}
        <SectionCard
          title={
            <span className="section-title-with-icon">
              <FaPencil />
              <span>Account Settings</span>
            </span>
          }
          className="student-profile-card"
        >
          <div className="account-actions">
            <Link to="/student/change-password" className="action-link">
              <div className="action-icon">
                <FaPencil />
              </div>
              <div className="action-text">
                <h4>Change Password</h4>
                <p>Update your password to keep your account secure</p>
              </div>
              <span className="action-arrow">→</span>
            </Link>
            <Link to="/student/attendance" className="action-link">
              <div className="action-icon">
                <FaChartLine />
              </div>
              <div className="action-text">
                <h4>View Attendance</h4>
                <p>Check your attendance records and statistics</p>
              </div>
              <span className="action-arrow">→</span>
            </Link>
          </div>
        </SectionCard>
      </div>

      {/* Edit Profile Modal */}
      {showEditModal && (
        <div className="admin-modal-overlay" onClick={() => !loading && setShowEditModal(false)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>Edit Contact Information</h3>
              <button className="admin-modal-close" onClick={() => setShowEditModal(false)}>
                <FaXmark />
              </button>
            </div>
            <form className="admin-form" onSubmit={handleUpdateProfile}>
              {message && <div className="alert alert-success"><FaCheck /> {message}</div>}
              {error && <div className="alert alert-danger">{error}</div>}

              <div className="admin-form-group">
                <label className="admin-form-label">Email Address</label>
                <input
                  type="email"
                  className="admin-form-input"
                  placeholder="Enter your email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                />
              </div>

              <div className="admin-form-group">
                <label className="admin-form-label">Phone Number</label>
                <input
                  type="tel"
                  className="admin-form-input"
                  placeholder="Enter your phone number"
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                />
              </div>

              <div className="admin-form-group">
                <label className="admin-form-label">Residential Address</label>
                <textarea
                  className="admin-form-input"
                  rows="3"
                  placeholder="Enter your full address"
                  value={editForm.address}
                  onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
                ></textarea>
              </div>

              <div className="admin-modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowEditModal(false)}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button type="submit" className="primary-btn" disabled={loading}>
                  {loading ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PageShell>
  );
}

export default StudentProfile;


import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { 
  FaUser, FaEnvelope, FaPhone, FaMapPin, FaAward, FaBook, FaCamera,
  FaGraduationCap, FaCalendarDays, FaPencil, FaCircleCheck, FaChartLine, FaEye, FaTrash, FaPlus, FaKey
} from "react-icons/fa6";
import { apiUrl, useSessionProfile } from "../../utils/auth";
import { adminNav } from "../../utils/constants";
import { PageShell, SectionCard, SkeletonBlock } from "../../components/Shared";

function StudentsListSkeleton({ rows = 6 }) {
  return (
    <div className="table-wrap skeleton-table-wrap students-table-skeleton-shell">
      <table className="admin-table students-table-skeleton-table" aria-hidden="true">
        <thead>
          <tr>
            <th>Roll Number</th>
            <th>Name</th>
            <th>Branch</th>
            <th>Semester / Section</th>
            <th>Face</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, rowIndex) => (
            <tr key={`students-skeleton-row-${rowIndex}`}>
              <td><SkeletonBlock className="skeleton-line students-cell-roll" /></td>
              <td><SkeletonBlock className="skeleton-line students-cell-name" /></td>
              <td><SkeletonBlock className="skeleton-line students-cell-branch" /></td>
              <td><SkeletonBlock className="skeleton-line students-cell-sem" /></td>
              <td><SkeletonBlock className="skeleton-line students-cell-face" /></td>
              <td>
                <div className="students-cell-actions">
                  <SkeletonBlock className="skeleton-block students-action-dot" />
                  <SkeletonBlock className="skeleton-block students-action-dot" />
                  <SkeletonBlock className="skeleton-block students-action-wide" />
                  <SkeletonBlock className="skeleton-block students-action-dot" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AdminManageStudents() {
  const navigate = useNavigate();
  const profile = useSessionProfile("admin");
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [confirmState, setConfirmState] = useState({
    open: false,
    studentId: "",
  });
  const [showAddModal, setShowAddModal] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "",
    roll_no: "",
    branch: "",
    semester: "1",
    section: "A",
    email: "",
    phone: "",
    address: "",
  });
  const [branches, setBranches] = useState([]);
  const [openFaceRegistrationAfterAdd, setOpenFaceRegistrationAfterAdd] = useState(false);

  const [selectedStudent, setSelectedStudent] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [editForm, setEditForm] = useState({
    id: "",
    name: "",
    roll_no: "",
    branch: "",
    semester: "1",
    section: "A",
    email: "",
    phone: "",
    address: "",
  });
  const itemsPerPage = 10;

  useEffect(() => {
    loadStudents();
    loadBranches();
  }, []);

  async function loadBranches() {
    try {
      const res = await fetch(apiUrl("/api/admin/academic-setup"), {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success && Array.isArray(data.branches)) {
        const branchList = data.branches.map(b => ({
          code: b.code,
          name: b.name
        }));
        setBranches(branchList);
        if (branchList.length > 0) {
          setAddForm(prev => ({ ...prev, branch: branchList[0].code }));
        }
      }
    } catch (err) {
      console.error("Branches load error:", err);
    }
  }

  async function loadStudents() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(apiUrl("/api/admin/students"), {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok && data.success && Array.isArray(data.students)) {
        setStudents(data.students);
      } else {
        setError(data.message || "Failed to load students");
      }
    } catch (err) {
      console.error("Students load error:", err);
      setError("Network error while loading students");
    } finally {
      setLoading(false);
    }
  }

  // Automation: Update email based on name
  useEffect(() => {
    if (showAddModal) {
      const emailName = addForm.name.toLowerCase().replace(/\s+/g, "");
      if (emailName) {
        setAddForm(prev => ({
          ...prev,
          email: `${emailName}@facemarkpro.com`
        }));
      } else {
        setAddForm(prev => ({ ...prev, email: "" }));
      }
    }
  }, [addForm.name, showAddModal]);

  // Automation: Update roll number based on branch and existing students
  useEffect(() => {
    if (showAddModal && addForm.branch) {
      const yearShort = new Date().getFullYear().toString().slice(-2);
      const branchCode = addForm.branch.toUpperCase();
      
      // Find students in this branch to determine next sequence
      const branchStudents = students.filter(s => 
        (s.branch || "").toUpperCase() === branchCode
      );
      
      let nextSeq = 1;
      if (branchStudents.length > 0) {
        const sequences = branchStudents.map(s => {
          // Extract the numeric part at the end of roll_no (e.g., 24CSE01 -> 01)
          const match = (s.roll_no || "").match(/\d+$/);
          return match ? parseInt(match[0], 10) : 0;
        });
        nextSeq = Math.max(...sequences, 0) + 1;
      }
      
      const seqStr = String(nextSeq).padStart(2, '0');
      setAddForm(prev => ({
        ...prev,
        roll_no: `${yearShort}${branchCode}${seqStr}`
      }));
    }
  }, [addForm.branch, students, showAddModal]);

  // Update email for Edit modal too? (Optional, but usually name doesn't change much)
  useEffect(() => {
    if (showEditModal) {
      const emailName = editForm.name.toLowerCase().replace(/\s+/g, "");
      if (emailName && !editForm.email) { // Only auto-fill if email is empty
        setEditForm(prev => ({
          ...prev,
          email: `${emailName}@facemarkpro.com`
        }));
      }
    }
  }, [editForm.name, showEditModal]);

  const filteredStudents = useMemo(() => {
    return students.filter((s) =>
      (s.name || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.roll_no || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.branch || "").toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [students, searchQuery]);

  const totalPages = Math.ceil(filteredStudents.length / itemsPerPage);
  const paginatedStudents = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredStudents.slice(start, start + itemsPerPage);
  }, [filteredStudents, currentPage]);

  const executeDelete = async (studentId) => {
    try {
      const res = await fetch(apiUrl(`/api/admin/students/${studentId}`), {
        method: "DELETE",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setStudents((prev) => prev.filter((s) => s._id !== studentId));
        setActionMessage("Student removed successfully.");
      } else {
        setError(data.message || "Failed to delete student.");
      }
    } catch (err) {
      console.error("Delete error:", err);
      setError("Network error while deleting student.");
    }
  };

  const openDeleteConfirm = (studentId) => {
    setConfirmState({ open: true, studentId });
  };

  const closeDeleteConfirm = () => {
    setConfirmState({ open: false, studentId: "" });
  };

  const onConfirmDelete = async () => {
    const id = confirmState.studentId;
    closeDeleteConfirm();
    if (id) await executeDelete(id);
  };

  const handleAddStudent = async (e) => {
    e.preventDefault();
    setError("");
    setActionMessage("");

    if (!addForm.name.trim() || !addForm.roll_no.trim()) {
      setError("Name and roll number are required.");
      return;
    }

    try {
      setAddLoading(true);
      const res = await fetch(apiUrl("/api/admin/students"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          name: addForm.name.trim(),
          roll_no: addForm.roll_no.trim(),
          branch: addForm.branch,
          semester: Number(addForm.semester),
          section: addForm.section,
          email: addForm.email.trim(),
          phone: addForm.phone.trim(),
          address: addForm.address.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok && data.success) {
        const nextRollNo = addForm.roll_no.trim();
        const shouldOpenFaceRegistration = openFaceRegistrationAfterAdd;
        if (data.student) {
          setStudents((prev) => [data.student, ...prev]);
        } else {
          await loadStudents();
        }
        setShowAddModal(false);
        setAddForm({ name: "", roll_no: "", branch: "CSE", semester: "1", section: "A" });
        setOpenFaceRegistrationAfterAdd(false);

        if (shouldOpenFaceRegistration && nextRollNo) {
          navigate(`/admin/manage-faces?open=1&mode=create&roll=${encodeURIComponent(nextRollNo)}`);
          return;
        }

        setActionMessage("Student added successfully.");
      } else {
        setError(data.message || "Failed to add student.");
      }
    } catch (err) {
      console.error("Add student error:", err);
      setError("Network error while adding student.");
    } finally {
      setAddLoading(false);
    }
  };

  const handleOpenEdit = (student) => {
    setEditForm({
      id: student._id,
      name: student.name || "",
      roll_no: student.roll_no || "",
      branch: student.branch || "",
      semester: String(student.semester || "1"),
      section: student.section || "A",
      email: student.email || "",
      phone: student.phone || "",
      address: student.address || "",
    });
    setShowEditModal(true);
  };

  const handleEditStudent = async (e) => {
    e.preventDefault();
    setError("");
    setActionMessage("");

    try {
      setEditLoading(true);
      const res = await fetch(apiUrl(`/api/admin/students/${editForm.id}`), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          name: editForm.name.trim(),
          roll_no: editForm.roll_no.trim(),
          branch: editForm.branch,
          semester: Number(editForm.semester),
          section: editForm.section,
          email: editForm.email.trim(),
          phone: editForm.phone.trim(),
          address: editForm.address.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok && data.success) {
        setStudents((prev) =>
          prev.map((s) => (s._id === editForm.id ? { ...s, ...data.student } : s))
        );
        setShowEditModal(false);
        setActionMessage("Student updated successfully.");
      } else {
        setError(data.message || "Failed to update student.");
      }
    } catch (err) {
      console.error("Edit student error:", err);
      setError("Network error while updating student.");
    } finally {
      setEditLoading(false);
    }
  };

  const handleResetPassword = async (studentId) => {
    if (!window.confirm("Reset student password to default 123456?")) return;
    
    setError("");
    setActionMessage("");
    try {
      const res = await fetch(apiUrl(`/api/admin/students/${studentId}/reset-password`), {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success) {
        setActionMessage("Password reset to 123456 successfully.");
      } else {
        setError(data.message || "Failed to reset password.");
      }
    } catch (err) {
      console.error("Reset password error:", err);
      setError("Network error while resetting password.");
    }
  };

  return (
    <PageShell
      variant="admin"
      nav={adminNav}
      title="Manage Students"
      subtitle="Student master list with semester, section, and branch data."
      profile={profile}
    >
      <SectionCard title="Student List">
        <div className="admin-table-toolbar">
          <input
            type="text"
            className="search-input"
            placeholder="Search by name, roll number, or branch..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
          />
          <button className="primary-btn" onClick={() => setShowAddModal(true)}>
            <FaPlus /> Add Student
          </button>
        </div>

        {actionMessage ? <p className="success-copy">{actionMessage}</p> : null}

        {loading ? (
          <StudentsListSkeleton rows={6} />
        ) : error ? (
          <p className="error-copy">{error}</p>
        ) : paginatedStudents.length === 0 ? (
          <p className="muted-copy">No students found.</p>
        ) : (
          <>
            <div className="table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Roll Number</th>
                    <th>Name</th>
                    <th>Branch</th>
                    <th>Semester / Section</th>
                    <th>Face</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedStudents.map((s, idx) => (
                    <tr key={s._id || idx}>
                      <td className="student-roll">
                        <strong>{s.roll_no || "—"}</strong>
                      </td>
                      <td className="student-name">{s.name || "—"}</td>
                      <td>
                        <span className="dept-badge">{s.branch || "—"}</span>
                      </td>
                      <td>
                        <span className="semester-badge">
                          {s.semester}-{s.section || "—"}
                        </span>
                      </td>
                      <td>
                        <span className={`face-badge ${s.face_registered ? "registered" : "missing"}`}>
                          {s.face_registered ? "Registered" : "Not Registered"}
                        </span>
                      </td>
                      <td className="action-cell">
                        <button
                          className="action-btn view-btn"
                          title="View"
                          onClick={() => setSelectedStudent(s)}
                        >
                          <FaEye />
                        </button>
                        <button
                          className="action-btn edit-btn"
                          title="Edit"
                          onClick={() => handleOpenEdit(s)}
                        >
                          <FaPencil />
                        </button>
                        <button
                          className={`face-text-btn ${s.face_registered ? "reregister" : "add"}`}
                          title={s.face_registered ? "Re-register Face" : "Add Face"}
                          onClick={() => {
                            const mode = s.face_registered ? "replace" : "create";
                            navigate(
                              `/admin/manage-faces?open=1&mode=${mode}&roll=${encodeURIComponent(s.roll_no || "")}`
                            );
                          }}
                        >
                          <FaCamera /> {s.face_registered ? "Re-register Face" : "Add Face"}
                        </button>
                        <button
                          className="action-btn key-btn"
                          title="Reset Password to 123456"
                          onClick={() => handleResetPassword(s._id)}
                        >
                          <FaKey />
                        </button>
                        <button
                          className="action-btn delete-btn"
                          title="Delete"
                          onClick={() => openDeleteConfirm(s._id)}
                        >
                          <FaTrash />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="pagination-btn"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(currentPage - 1)}
                >
                  Previous
                </button>
                <span className="pagination-info">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  className="pagination-btn"
                  disabled={currentPage === totalPages}
                  onClick={() => setCurrentPage(currentPage + 1)}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </SectionCard>

      {confirmState.open ? (
        <div className="admin-modal-overlay" onClick={closeDeleteConfirm}>
          <div className="admin-modal admin-confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>Confirm Delete</h3>
              <button className="admin-modal-close" onClick={closeDeleteConfirm}>x</button>
            </div>
            <div className="admin-modal-body">
              <p className="admin-confirm-message">Are you sure you want to delete this student?</p>
              <div className="admin-confirm-actions">
                <button className="pagination-btn" onClick={closeDeleteConfirm}>Cancel</button>
                <button className="primary-btn" onClick={onConfirmDelete}>Confirm</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {showAddModal ? (
        <div className="admin-modal-overlay" onClick={() => !addLoading && setShowAddModal(false)}>
          <div className="admin-modal admin-form-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>Add New Student</h3>
              <button
                className="admin-modal-close"
                onClick={() => {
                  setShowAddModal(false);
                  setOpenFaceRegistrationAfterAdd(false);
                }}
                disabled={addLoading}
              >
                x
              </button>
            </div>
            <form className="admin-form" onSubmit={handleAddStudent}>
              <div className="admin-form-grid">
                <div>
                  <label className="admin-form-label">Full Name</label>
                  <input
                    className="admin-form-input"
                    type="text"
                    placeholder="Enter student name"
                    value={addForm.name}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, name: e.target.value }))}
                    required
                  />
                </div>
                <div>
                  <label className="admin-form-label">Roll Number</label>
                  <input
                    className="admin-form-input"
                    type="text"
                    placeholder="e.g. 24CSE01"
                    value={addForm.roll_no}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, roll_no: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="admin-form-grid-three">
                <div>
                  <label className="admin-form-label">Branch</label>
                  <select
                    className="admin-form-input"
                    value={addForm.branch}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, branch: e.target.value }))}
                    required
                  >
                    <option value="">Select Branch</option>
                    {branches.map((b) => (
                      <option key={b.code} value={b.code}>
                        {b.code}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="admin-form-label">Semester</label>
                  <select
                    className="admin-form-input"
                    value={addForm.semester}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, semester: e.target.value }))}
                  >
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                    <option value="6">6</option>
                    <option value="7">7</option>
                    <option value="8">8</option>
                  </select>
                </div>
                <div>
                  <label className="admin-form-label">Section</label>
                  <select
                    className="admin-form-input"
                    value={addForm.section}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, section: e.target.value }))}
                  >
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                    <option value="D">D</option>
                    <option value="E">E</option>
                    <option value="F">F</option>
                  </select>
                </div>
              </div>

              <div className="admin-form-divider">Contact Information (Optional)</div>

              <div className="admin-form-grid">
                <div>
                  <label className="admin-form-label">Email Address</label>
                  <input
                    className="admin-form-input"
                    type="email"
                    placeholder="student@example.com"
                    value={addForm.email}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, email: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="admin-form-label">Phone Number</label>
                  <input
                    className="admin-form-input"
                    type="tel"
                    placeholder="Enter phone number"
                    value={addForm.phone}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, phone: e.target.value }))}
                  />
                </div>
              </div>

              <label className="admin-form-label">Address</label>
              <textarea
                className="admin-form-input"
                rows="2"
                placeholder="Enter student's residential address"
                value={addForm.address}
                onChange={(e) => setAddForm((prev) => ({ ...prev, address: e.target.value }))}
              ></textarea>

              <div className="face-reg-checkbox">
                <input
                  type="checkbox"
                  id="openFaceRegistrationAfterAdd"
                  checked={openFaceRegistrationAfterAdd}
                  onChange={(e) => setOpenFaceRegistrationAfterAdd(e.target.checked)}
                />
                <label htmlFor="openFaceRegistrationAfterAdd">
                  Register Face after creating student
                </label>
              </div>

              <button className="primary-btn admin-form-submit" type="submit" disabled={addLoading}>
                {addLoading ? "Creating..." : "Create Student"}
              </button>
            </form>
          </div>
        </div>
      ) : null}
      {selectedStudent ? (
        <div className="admin-modal-overlay" onClick={() => setSelectedStudent(null)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>Student Information</h3>
              <button className="admin-modal-close" onClick={() => setSelectedStudent(null)}>x</button>
            </div>
            <div className="admin-modal-body">
              <div className="admin-info-row"><strong>Name:</strong> {selectedStudent.name || "—"}</div>
              <div className="admin-info-row"><strong>Roll Number:</strong> {selectedStudent.roll_no || "—"}</div>
              <div className="admin-info-row"><strong>Branch:</strong> {selectedStudent.branch || "—"}</div>
              <div className="admin-info-row"><strong>Semester:</strong> {selectedStudent.semester || "—"}</div>
              <div className="admin-info-row"><strong>Section:</strong> {selectedStudent.section || "—"}</div>
              <div className="admin-info-row"><strong>Email:</strong> {selectedStudent.email || "Not Provided"}</div>
              <div className="admin-info-row"><strong>Phone:</strong> {selectedStudent.phone || "Not Provided"}</div>
              <div className="admin-info-row"><strong>Address:</strong> {selectedStudent.address || "Not Provided"}</div>
              <div className="admin-info-row"><strong>Face Status:</strong> {selectedStudent.face_registered ? "Registered" : "Not Registered"}</div>
            </div>
          </div>
        </div>
      ) : null}

      {showEditModal ? (
        <div className="admin-modal-overlay" onClick={() => !editLoading && setShowEditModal(false)}>
          <div className="admin-modal admin-form-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>Edit Student</h3>
              <button
                className="admin-modal-close"
                onClick={() => setShowEditModal(false)}
                disabled={editLoading}
              >
                x
              </button>
            </div>
            <form className="admin-form" onSubmit={handleEditStudent}>
              <div className="admin-form-grid">
                <div>
                  <label className="admin-form-label">Full Name</label>
                  <input
                    className="admin-form-input"
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                    required
                  />
                </div>

                <div>
                  <label className="admin-form-label">Roll Number</label>
                  <input
                    className="admin-form-input"
                    type="text"
                    value={editForm.roll_no}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, roll_no: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="admin-form-grid-three">
                <div>
                  <label className="admin-form-label">Branch</label>
                  <select
                    className="admin-form-input"
                    value={editForm.branch}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, branch: e.target.value }))}
                  >
                    {branches.length === 0 ? (
                      <option value="">No branches created</option>
                    ) : (
                      branches.map((b) => (
                        <option key={b.code} value={b.code}>
                          {b.code}
                        </option>
                      ))
                    )}
                  </select>
                </div>
                <div>
                  <label className="admin-form-label">Semester</label>
                  <select
                    className="admin-form-input"
                    value={editForm.semester}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, semester: e.target.value }))}
                  >
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                    <option value="6">6</option>
                    <option value="7">7</option>
                    <option value="8">8</option>
                  </select>
                </div>
                <div>
                  <label className="admin-form-label">Section</label>
                  <select
                    className="admin-form-input"
                    value={editForm.section}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, section: e.target.value }))}
                  >
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                    <option value="D">D</option>
                    <option value="E">E</option>
                    <option value="F">F</option>
                  </select>
                </div>
              </div>

              <div className="admin-form-divider">Contact Details</div>
              
              <div className="admin-form-grid">
                <div>
                  <label className="admin-form-label">Email Address</label>
                  <input
                    className="admin-form-input"
                    type="email"
                    placeholder="student@example.com"
                    value={editForm.email}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, email: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="admin-form-label">Phone Number</label>
                  <input
                    className="admin-form-input"
                    type="tel"
                    placeholder="9876543210"
                    value={editForm.phone}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, phone: e.target.value }))}
                  />
                </div>
              </div>

              <label className="admin-form-label">Residential Address</label>
              <textarea
                className="admin-form-input"
                rows="2"
                placeholder="Street, City, State, Pincode"
                value={editForm.address}
                onChange={(e) => setEditForm((prev) => ({ ...prev, address: e.target.value }))}
              ></textarea>

              <button className="primary-btn admin-form-submit student-submit-btn" type="submit" disabled={editLoading}>
                {editLoading ? "Updating..." : "Save Changes"}
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

export default AdminManageStudents;

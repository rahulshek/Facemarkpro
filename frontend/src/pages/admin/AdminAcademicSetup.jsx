import React, { useEffect, useMemo, useState } from "react";
import { FaBook, FaBuilding, FaChartLine, FaPencil, FaPlus, FaTrash, FaUsers } from "react-icons/fa6";

import { apiUrl, useSessionProfile } from "../../utils/auth";
import { adminNav } from "../../utils/constants";
import { PageShell, SectionCard, SkeletonBlock, StatGrid } from "../../components/Shared";

const TABS = [
  { id: "branches", label: "Branches", singular: "Branch" },
  { id: "classes", label: "Classes", singular: "Class" },
  { id: "classrooms", label: "Classrooms", singular: "Classroom" },
  { id: "subjects", label: "Subjects", singular: "Subject" },
  { id: "assignments", label: "Assignments", singular: "Assignment" },
];

const EMPTY_FORMS = {
  branches: { id: "", code: "", name: "", active: true },
  classes: { id: "", branch: "", semester: "", section: "", label: "", active: true },
  classrooms: { id: "", name: "", type: "Classroom", capacity: "", active: true },
  subjects: { id: "", code: "", name: "", branch: "", semester: "", type: "theory", active: true },
  assignments: { id: "", faculty_email: "", branch: "", semester: "", section: "", subject_code: "", classroom: "", active: true, class_value: "" },
};

function AcademicSetupSkeleton({ columns, rows = 6 }) {
  return (
    <div className="table-wrap skeleton-table-wrap setup-table-skeleton-shell">
      <table className="admin-table setup-table-skeleton-table" aria-hidden="true">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={`setup-head-${column}`}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, rowIndex) => (
            <tr key={`setup-skeleton-row-${rowIndex}`}>
              {columns.map((column, columnIndex) => (
                <td key={`setup-skeleton-cell-${rowIndex}-${column}`}>
                  {columnIndex === columns.length - 1 ? (
                    <div className="setup-cell-actions">
                      <SkeletonBlock className="skeleton-block setup-action-dot" />
                      <SkeletonBlock className="skeleton-block setup-action-dot" />
                    </div>
                  ) : column.toLowerCase().includes("status") ? (
                    <SkeletonBlock className="skeleton-line setup-cell-status" />
                  ) : (
                    <SkeletonBlock className={`skeleton-line${columnIndex === 0 ? " setup-cell-primary" : " setup-cell-regular"}`} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AdminAcademicSetup() {
  const profile = useSessionProfile("admin");
  const [activeTab, setActiveTab] = useState("branches");
  const [setup, setSetup] = useState({
    summary: { branches: 0, classes: 0, classrooms: 0, subjects: 0, assignments: 0 },
    branches: [],
    classes: [],
    classrooms: [],
    subjects: [],
    assignments: [],
    faculty_options: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [form, setForm] = useState(EMPTY_FORMS.branches);

  useEffect(() => {
    loadSetup();
  }, []);

  async function loadSetup() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/admin/academic-setup"), {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        setError(payload.message || payload.error || "Failed to load academic setup.");
        return;
      }
      setSetup({
        summary: payload.summary || { branches: 0, classes: 0, classrooms: 0, subjects: 0, assignments: 0 },
        branches: payload.branches || [],
        classes: payload.classes || [],
        classrooms: payload.classrooms || [],
        subjects: payload.subjects || [],
        assignments: payload.assignments || [],
        faculty_options: payload.faculty_options || [],
      });
    } catch {
      setError("Network error while loading academic setup.");
    } finally {
      setLoading(false);
    }
  }

  const stats = useMemo(() => ([
    { value: String(setup.summary.branches || 0), label: "Branches", tone: "blue", icon: FaBuilding },
    { value: String(setup.summary.classes || 0), label: "Classes", tone: "green", icon: FaUsers },
    { value: String(setup.summary.classrooms || 0), label: "Classrooms", tone: "amber", icon: FaBuilding },
    { value: String(setup.summary.subjects || 0), label: "Subjects", tone: "purple", icon: FaBook },
    { value: String(setup.summary.assignments || 0), label: "Assignments", tone: "cyan", icon: FaChartLine },
  ]), [setup.summary]);

  const classOptions = useMemo(
    () => (setup.classes || []).map((item) => ({
      value: `${item.branch}|${item.semester}|${item.section}`,
      label: item.label || `${item.branch} / ${item.semester} / ${item.section}`,
      branch: item.branch,
      semester: item.semester,
      section: item.section,
    })),
    [setup.classes]
  );

  const branchOptions = useMemo(() => (setup.branches || []).map((item) => item.code), [setup.branches]);
  const classroomOptions = useMemo(() => (setup.classrooms || []).map((item) => item.name), [setup.classrooms]);

  const subjectOptions = useMemo(() => {
    const branch = String(form.branch || "").trim().toUpperCase();
    const semester = String(form.semester || "").trim();

    // If no branch or semester selected, show nothing in the assignment dropdown
    if (!branch && !semester) return [];

    return (setup.subjects || []).filter((item) => {
      const itemBranch = String(item.branch || "").trim().toUpperCase();
      const itemSem = String(item.semester ?? "").trim();

      if (branch && itemBranch !== branch) return false;
      if (semester && itemSem !== semester) return false;
      return true;
    });
  }, [form.branch, form.semester, setup.subjects]);

  const facultyOptions = useMemo(() => setup.faculty_options || [], [setup.faculty_options]);
  const currentItems = setup[activeTab] || [];

  function openCreateModal() {
    const defaultBranch = branchOptions[0] || "";
    const emptyForm = { ...EMPTY_FORMS[activeTab] };
    if ((activeTab === "classes" || activeTab === "subjects" || activeTab === "assignments") && defaultBranch) {
      emptyForm.branch = defaultBranch;
      if (activeTab === "classes") {
        emptyForm.label = defaultBranch;
      }
    }
    setForm(emptyForm);
    setModalOpen(true);
    setError("");
    setActionMessage("");
  }

  function openEditModal(item) {
    if (activeTab === "assignments") {
      setForm({
        ...item,
        faculty_email: item.faculty_email || "",
        branch: item.branch || "",
        semester: String(item.semester ?? ""),
        section: item.section || "",
        subject_code: item.subject_code || "",
        classroom: item.classroom || "",
        active: item.active !== false,
        class_value: item.branch && item.semester && item.section ? `${item.branch}|${item.semester}|${item.section}` : "",
      });
    } else {
      setForm({
        ...EMPTY_FORMS[activeTab],
        ...item,
        semester: item?.semester != null ? String(item.semester) : "",
        capacity: item?.capacity != null ? String(item.capacity) : "",
        active: item?.active !== false,
      });
    }
    setModalOpen(true);
    setError("");
    setActionMessage("");
  }

  function closeModal() {
    setModalOpen(false);
    setSaving(false);
    setForm({ ...EMPTY_FORMS[activeTab] });
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setActionMessage("");

    try {
      const payload = { ...form };
      if (activeTab === "assignments" && payload.class_value) {
        const [branch, semester, section] = String(payload.class_value).split("|");
        payload.branch = branch || payload.branch;
        payload.semester = semester || payload.semester;
        payload.section = section || payload.section;
      }

      const response = await fetch(apiUrl(`/api/admin/academic-setup/${activeTab}`), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.success) {
        throw new Error(result.message || result.error || "Save failed");
      }

      await loadSetup();
      setActionMessage(result.message || "Saved successfully.");
      closeModal();
    } catch (saveError) {
      setError(saveError.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item) {
    if (!item?.id || deletingId) return;
    const confirmed = window.confirm("Delete this record?");
    if (!confirmed) return;

    setDeletingId(item.id);
    setError("");
    setActionMessage("");
    try {
      const response = await fetch(apiUrl(`/api/admin/academic-setup/${activeTab}/${item.id}`), {
        method: "DELETE",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.success) {
        throw new Error(result.message || result.error || "Delete failed");
      }
      await loadSetup();
      setActionMessage(result.message || "Deleted successfully.");
    } catch (deleteError) {
      setError(deleteError.message || "Delete failed.");
    } finally {
      setDeletingId("");
    }
  }

  function renderRows() {
    if (activeTab === "branches") return currentItems.map((item) => [item.code, item.name, item.active ? "Active" : "Inactive", actionButtons(item)]);
    if (activeTab === "classes") return currentItems.map((item) => [item.branch, item.semester, item.section, item.label, item.active ? "Active" : "Inactive", actionButtons(item)]);
    if (activeTab === "classrooms") return currentItems.map((item) => [item.name, item.type || "Classroom", item.capacity || "-", item.active ? "Active" : "Inactive", actionButtons(item)]);
    if (activeTab === "subjects") return currentItems.map((item) => [item.code, item.name, item.branch, item.semester, item.type, item.active ? "Active" : "Inactive", actionButtons(item)]);
    return currentItems.map((item) => [item.faculty_name || item.faculty_email, item.subject_label, item.class_label, item.classroom || "-", item.active ? "Active" : "Inactive", actionButtons(item)]);
  }

  function actionButtons(item) {
    return (
      <div className="academic-setup-actions">
        <button type="button" className="action-btn view-btn" onClick={() => openEditModal(item)}><FaPencil /></button>
        <button type="button" className="action-btn delete-btn" onClick={() => handleDelete(item)} disabled={deletingId === item.id}><FaTrash /></button>
      </div>
    );
  }

  function renderColumns() {
    if (activeTab === "branches") return ["Code", "Name", "Status", "Actions"];
    if (activeTab === "classes") return ["Branch", "Semester", "Section", "Label", "Status", "Actions"];
    if (activeTab === "classrooms") return ["Name", "Type", "Capacity", "Status", "Actions"];
    if (activeTab === "subjects") return ["Code", "Name", "Branch", "Semester", "Type", "Status", "Actions"];
    return ["Faculty", "Subject", "Class", "Classroom", "Status", "Actions"];
  }

  return (
    <PageShell variant="admin" nav={adminNav} title="Academic Setup" subtitle="Manage master data for branches, classes, classrooms, subjects, and faculty assignments." profile={profile}>
      <section className="admin-overview-hero academic-setup-hero">
        <div className="admin-overview-hero-copy">
          <span className="admin-overview-kicker">Academic Setup</span>
          <h2>Central source of truth for academic structure</h2>
          <p>Keep branches, class groups, rooms, subjects, and faculty-class assignments in one admin-controlled space.</p>
        </div>
      </section>

      <div className="admin-overview-stats">
        <StatGrid stats={stats} />
      </div>

      <SectionCard title="Setup Manager" className="admin-overview-card">
        <div className="academic-setup-toolbar">
          <div className="academic-setup-tabs">
            {TABS.map((tab) => (
              <button key={tab.id} type="button" className={`academic-setup-tab${activeTab === tab.id ? " active" : ""}`} onClick={() => setActiveTab(tab.id)}>
                {tab.label}
              </button>
            ))}
          </div>
          <button className="primary-btn" type="button" onClick={openCreateModal}>
            <FaPlus /> Add {TABS.find((tab) => tab.id === activeTab)?.singular || "Item"}
          </button>
        </div>

        {actionMessage ? <p className="success-copy">{actionMessage}</p> : null}
        {loading ? <AcademicSetupSkeleton rows={6} columns={renderColumns()} /> : error ? <p className="error-copy">{error}</p> : (
          currentItems.length ? <div className="table-wrap"><table className="admin-table"><thead><tr>{renderColumns().map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{renderRows().map((row, rowIndex) => <tr key={`${activeTab}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div> : <p className="muted-copy">No {activeTab} added yet.</p>
        )}
      </SectionCard>

      {modalOpen ? (
        <div className="admin-modal-overlay" onClick={() => !saving && closeModal()}>
          <div className="admin-modal admin-form-modal academic-setup-modal" onClick={(event) => event.stopPropagation()}>
            <div className="admin-modal-header">
              <h3>{form.id ? "Edit" : "Add"} {TABS.find((tab) => tab.id === activeTab)?.singular || "Item"}</h3>
              <button className="admin-modal-close" type="button" onClick={closeModal} disabled={saving}>x</button>
            </div>
            <form className="admin-form academic-setup-form" onSubmit={handleSave}>
              {activeTab === "branches" ? (
                <>
                  <label className="admin-form-label">Branch Code</label>
                  <input className="admin-form-input" value={form.code || ""} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))} required />
                  <label className="admin-form-label">Branch Name</label>
                  <input className="admin-form-input" value={form.name || ""} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
                </>
              ) : null}

              {activeTab === "classes" ? (
                <>
                  <label className="admin-form-label">Branch</label>
                  <select
                    className="admin-form-input"
                    value={form.branch || ""}
                    onChange={(event) => {
                      const branch = event.target.value;
                      setForm((current) => ({
                        ...current,
                        branch,
                        label: `${branch}${current.semester ? " / " + current.semester : ""}${current.section ? " / " + current.section : ""}`,
                      }));
                    }}
                    required
                  >
                    <option value="" disabled>Select branch</option>
                    {branchOptions.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
                  </select>

                  <label className="admin-form-label">Semester</label>
                  <input
                    className="admin-form-input"
                    type="number"
                    min="1"
                    max="12"
                    value={form.semester || ""}
                    onChange={(event) => {
                      const semester = event.target.value;
                      setForm((current) => ({
                        ...current,
                        semester,
                        label: `${current.branch || ""}${current.branch && semester ? " / " : ""}${semester}${current.section ? " / " + current.section : ""}`,
                      }));
                    }}
                    required
                  />

                  <label className="admin-form-label">Section</label>
                  <input
                    className="admin-form-input"
                    value={form.section || ""}
                    onChange={(event) => {
                      const section = event.target.value.toUpperCase();
                      setForm((current) => ({
                        ...current,
                        section,
                        label: `${current.branch || ""}${current.branch && current.semester ? " / " : ""}${current.semester || ""}${(current.branch || current.semester) && section ? " / " : ""}${section}`,
                      }));
                    }}
                    required
                  />

                  <label className="admin-form-label">Label</label>
                  <input
                    className="admin-form-input"
                    value={form.label || ""}
                    onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
                    placeholder="CSE / 5 / A"
                  />
                </>
              ) : null}

              {activeTab === "classrooms" ? (
                <>
                  <label className="admin-form-label">Classroom Name</label>
                  <input className="admin-form-input" value={form.name || ""} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
                  <label className="admin-form-label">Type</label>
                  <input className="admin-form-input" value={form.type || ""} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value }))} />
                  <label className="admin-form-label">Capacity</label>
                  <input className="admin-form-input" type="number" min="0" value={form.capacity || ""} onChange={(event) => setForm((current) => ({ ...current, capacity: event.target.value }))} />
                </>
              ) : null}

              {activeTab === "subjects" ? (
                <>
                  <label className="admin-form-label">Subject Code</label>
                  <input className="admin-form-input" value={form.code || ""} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))} required />
                  <label className="admin-form-label">Subject Name</label>
                  <input className="admin-form-input" value={form.name || ""} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
                  <label className="admin-form-label">Branch</label>
                  <select className="admin-form-input" value={form.branch || ""} onChange={(event) => setForm((current) => ({ ...current, branch: event.target.value }))} required>
                    <option value="" disabled>Select branch</option>
                    {branchOptions.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
                  </select>
                  <label className="admin-form-label">Semester</label>
                  <input className="admin-form-input" type="number" min="1" max="12" value={form.semester || ""} onChange={(event) => setForm((current) => ({ ...current, semester: event.target.value }))} required />
                  <label className="admin-form-label">Type</label>
                  <select className="admin-form-input" value={form.type || "theory"} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value }))}><option value="theory">Theory</option><option value="lab">Lab</option><option value="tutorial">Tutorial</option></select>
                </>
              ) : null}

              {activeTab === "assignments" ? (
                <>
                  <label className="admin-form-label">Faculty</label>
                  <select className="admin-form-input" value={form.faculty_email || ""} onChange={(event) => setForm((current) => ({ ...current, faculty_email: event.target.value }))} required>
                    <option value="" disabled>Select faculty</option>
                    {facultyOptions.map((item) => <option key={item.email} value={item.email}>{item.label}</option>)}
                  </select>
                  
                  <label className="admin-form-label">Branch</label>
                  <select className="admin-form-input" value={form.branch || ""} onChange={(event) => setForm((current) => ({ ...current, branch: event.target.value, class_value: "", semester: "", section: "", subject_code: "" }))} required>
                    <option value="" disabled>Select branch</option>
                    {branchOptions.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
                  </select>
                  
                  <label className="admin-form-label">Class</label>
                  <select className="admin-form-input" value={form.class_value || ""} onChange={(event) => { const selected = classOptions.find((item) => item.value === event.target.value); setForm((current) => ({ ...current, class_value: event.target.value, branch: selected?.branch || current.branch, semester: selected ? String(selected.semester) : "", section: selected?.section || "", subject_code: "" })); }} required>
                    <option value="" disabled>Select class</option>
                    {classOptions.filter((item) => !form.branch || item.branch === form.branch).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                  
                  <label className="admin-form-label">Subject</label>
                  <select className="admin-form-input" value={form.subject_code || ""} onChange={(event) => setForm((current) => ({ ...current, subject_code: event.target.value }))} required>
                    <option value="" disabled>Select subject</option>
                    {subjectOptions.map((item) => <option key={item.code} value={item.code}>{item.name} ({item.code})</option>)}
                  </select>
                  
                  <label className="admin-form-label">Classroom</label>
                  <select className="admin-form-input" value={form.classroom || ""} onChange={(event) => setForm((current) => ({ ...current, classroom: event.target.value }))}>
                    <option value="">Not assigned</option>
                    {classroomOptions.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </>
              ) : null}

              <label className="admin-inline-check">
                <input type="checkbox" checked={form.active !== false} onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))} />
                <span>Active</span>
              </label>

              <button className="primary-btn admin-form-submit" type="submit" disabled={saving}>
                {saving ? "Saving..." : form.id ? "Save Changes" : "Create"}
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

export default AdminAcademicSetup;

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FaArrowRight, FaBook, FaCheck, FaClock, FaUserCheck, FaUsers } from "react-icons/fa6";

import { apiUrl, useSessionProfile } from "../../utils/auth";
import { facultyNav } from "../../utils/constants";
import { PageShell } from "../../components/Shared";

function ManualAttendance() {
  const navigate = useNavigate();
  const profile = useSessionProfile("faculty");
  const [lectures, setLectures] = useState([]);
  const [selectedLectureKey, setSelectedLectureKey] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [showConfirm, setShowConfirm] = useState(false);
  const [errorText, setErrorText] = useState("");

  const selectedLecture = useMemo(
    () => lectures.find((lecture) => lecture.key === selectedLectureKey) || null,
    [lectures, selectedLectureKey]
  );

  useEffect(() => {
    let mounted = true;

    async function loadLectures() {
      setIsLoading(true);
      setErrorText("");
      try {
        const response = await fetch(apiUrl("/api/faculty/dashboard"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!mounted) return;

        if (!response.ok || !payload.success) {
          setLectures([]);
          setErrorText("Unable to load today classes.");
          return;
        }

        const nowDay = new Date().toLocaleDateString("en-US", { weekday: "long" });
        const rows = (payload.lectures || [])
          .filter((lecture) => lecture.day === nowDay || lecture.day === "Any")
          .map((lecture, index) => ({
            key: `${lecture.branch}-${lecture.semester}-${lecture.section}-${lecture.subject}-${lecture.start_time}-${index}`,
            subject: lecture.subject || "Subject",
            branch: lecture.branch,
            semester: Number(lecture.semester || 0),
            section: lecture.section || "",
            classroom: lecture.classroom || "",
            start_time: lecture.start_time || "",
            end_time: lecture.end_time || "",
          }));

        setLectures(rows);
        if (rows.length) {
          setSelectedLectureKey(rows[0].key);
        }
      } catch {
        if (mounted) {
          setLectures([]);
          setErrorText("Failed to load classes.");
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    }

    loadLectures();
    return () => {
      mounted = false;
    };
  }, []);

  function handleProceed() {
    if (!selectedLecture) return;
    setShowConfirm(true);
  }

  function handleConfirmProceed() {
    if (!selectedLecture) return;
    navigate("/faculty/manual-attendance/mark", {
      state: { lecture: selectedLecture },
    });
  }

  return (
    <PageShell
      variant="faculty"
      nav={facultyNav}
      profile={profile}
    >
      <div className="manual-attendance-page">
        <section className="manual-attendance-hero">
          <h2>
            <FaUserCheck /> Manual Attendance
          </h2>
          <p>Select a lecture to mark attendance manually</p>
        </section>

        <section className="manual-attendance-table-wrap">
          <table className="manual-attendance-table">
            <thead>
              <tr>
                <th>Select</th>
                <th><FaBook /> Subject</th>
                <th><FaUsers /> Class</th>
                <th><FaClock /> Time</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={4}>Loading classes...</td>
                </tr>
              ) : lectures.length === 0 ? (
                <tr>
                  <td colSpan={4}>{errorText || "No classes found for today."}</td>
                </tr>
              ) : (
                lectures.map((lecture) => {
                  const active = selectedLectureKey === lecture.key;
                  return (
                    <tr key={lecture.key} className={active ? "active" : ""} onClick={() => setSelectedLectureKey(lecture.key)}>
                      <td>
                        <input
                          type="radio"
                          name="manual-lecture"
                          checked={active}
                          onChange={() => setSelectedLectureKey(lecture.key)}
                        />
                      </td>
                      <td>{lecture.subject}</td>
                      <td>{`${lecture.branch}-${lecture.semester}${lecture.section}`}</td>
                      <td>{`${lecture.start_time} - ${lecture.end_time}`}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </section>

        <div className="manual-attendance-actions">
          <button type="button" className="primary-btn" onClick={handleProceed} disabled={!selectedLecture}>
            <FaArrowRight /> Proceed to Mark Attendance
          </button>
        </div>
      </div>

      {showConfirm && selectedLecture ? (
        <div className="manual-modal-overlay" onClick={() => setShowConfirm(false)}>
          <div className="manual-modal" onClick={(event) => event.stopPropagation()}>
            <h3>Confirm Selection</h3>
            <p>
              Are you sure you want to proceed with marking attendance for
              <strong>{` ${selectedLecture.subject}`}</strong>,
              <strong>{` Class ${selectedLecture.branch}-${selectedLecture.semester}${selectedLecture.section}`}</strong>,
              <strong>{` Time ${selectedLecture.start_time} - ${selectedLecture.end_time}`}</strong>?
            </p>
            <div className="manual-modal-actions">
              <button type="button" className="modal-cancel-btn" onClick={() => setShowConfirm(false)}>
                Cancel
              </button>
              <button type="button" className="modal-confirm-btn" onClick={handleConfirmProceed}>
                <FaCheck /> Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

export default ManualAttendance;

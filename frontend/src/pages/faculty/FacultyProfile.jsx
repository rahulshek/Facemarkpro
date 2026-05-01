import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  FaBuilding,
  FaCalendarDays,
  FaCamera,
  FaCloudArrowUp,
  FaCropSimple,
  FaEnvelope,
  FaFloppyDisk,
  FaGraduationCap,
  FaIdBadge,
  FaLocationDot,
  FaPenToSquare,
  FaPhone,
  FaPlus,
  FaRotateLeft,
  FaTrash,
  FaUser,
  FaUserGear,
  FaXmark,
} from "react-icons/fa6";

import { apiUrl, getStoredAuthRole, persistAuth, useSessionProfile } from "../../utils/auth";
import { facultyNav } from "../../utils/constants";
import { PageShell } from "../../components/Shared";

const TIMETABLE_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const DEFAULT_TIMETABLE_ROWS = [
  { start_time: "09:00", end_time: "10:00" },
  { start_time: "10:00", end_time: "11:00" },
  { start_time: "11:00", end_time: "12:00" },
  { start_time: "13:00", end_time: "14:00" },
  { start_time: "14:00", end_time: "15:00" },
];
const TIMETABLE_TIME_OPTIONS = Array.from({ length: 29 }, (_, index) => {
  const totalMinutes = (7 * 60) + (index * 30);
  const hours = String(Math.floor(totalMinutes / 60)).padStart(2, "0");
  const minutes = String(totalMinutes % 60).padStart(2, "0");
  return `${hours}:${minutes}`;
});

function timeToMinutes(value) {
  const [hourText = "0", minuteText = "0"] = String(value || "").split(":");
  const hours = Number(hourText);
  const minutes = Number(minuteText);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return Number.MAX_SAFE_INTEGER;
  }
  return (hours * 60) + minutes;
}

const createEmptyTimetableForm = (details = {}) => ({
  id: "",
  day: "Monday",
  start_time: "09:00",
  end_time: "10:00",
  subject: "",
  subject_code: "",
  subject_value: "",
  classroom: "",
  branch: details.department || "",
  semester: "",
  section: "A",
  class_value: "",
});

function sortTimetableSlots(slots) {
  return [...(slots || [])].sort((first, second) => {
    const dayDiff = TIMETABLE_DAYS.indexOf(first.day) - TIMETABLE_DAYS.indexOf(second.day);
    if (dayDiff !== 0) return dayDiff;
    const startDiff = timeToMinutes(first.start_time) - timeToMinutes(second.start_time);
    if (startDiff !== 0) return startDiff;
    const endDiff = timeToMinutes(first.end_time) - timeToMinutes(second.end_time);
    if (endDiff !== 0) return endDiff;
    return String(first.subject || "").localeCompare(String(second.subject || ""));
  });
}

function FacultyProfile() {
  const profile = useSessionProfile("faculty");
  const [details, setDetails] = useState(() => ({
    name: profile.name || "Faculty",
    email: profile.meta || "",
    department: "",
    role: "Faculty",
    photoPath: profile.photoPath || "",
  }));
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState("upload");
  const [imageSource, setImageSource] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [editorError, setEditorError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isStartingCamera, setIsStartingCamera] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [isProfileLoading, setIsProfileLoading] = useState(true);
  const [isEditingInfo, setIsEditingInfo] = useState(false);
  const [isSavingInfo, setIsSavingInfo] = useState(false);
  const [infoForm, setInfoForm] = useState({
    name: "",
    phone: "",
    qualification: "",
    address: "",
  });
  const [timetableSlots, setTimetableSlots] = useState([]);
  const [timetableDays, setTimetableDays] = useState(TIMETABLE_DAYS);
  const [timetableOptions, setTimetableOptions] = useState({
    branches: [],
    classes: [],
    classrooms: [],
    subjects: [],
    assigned_classes: [],
  });
  const [isTimetableLoading, setIsTimetableLoading] = useState(true);
  const [isEditingTimetable, setIsEditingTimetable] = useState(false);
  const [isSavingTimetable, setIsSavingTimetable] = useState(false);
  const [isDeletingTimetable, setIsDeletingTimetable] = useState("");
  const [timetableError, setTimetableError] = useState("");
  const [timetableForm, setTimetableForm] = useState(createEmptyTimetableForm());

  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const streamRef = useRef(null);
  const dragRef = useRef(null);

  useEffect(() => {
    let mounted = true;

    async function hydrateProfile() {
      try {
        const response = await fetch(apiUrl("/api/faculty/profile"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.success || !mounted) return;

        const data = payload.profile || {};
        setDetails({
          name: data.name || "Faculty",
          email: data.email || "",
          department: data.department || "",
          role: data.role || "Faculty",
          photoPath: data.photo_path || "",
          faculty_id: data.faculty_id || "",
          phone: data.phone || "",
          joined_date: data.joined_date || "",
          qualification: data.qualification || "",
          address: data.address || "",
        });
        setInfoForm({
          name: data.name || "",
          phone: data.phone || "",
          qualification: data.qualification || "",
          address: data.address || "",
        });
        setTimetableForm((current) => ({
          ...current,
          branch: current.branch || data.department || "",
        }));
        persistAuth({
          token: "session",
          role: data.role || getStoredAuthRole() || "faculty",
          user: {
            name: data.name || "Faculty",
            email: data.email || "",
            role: data.role || "faculty",
            department: data.department || "",
            photo_path: data.photo_path || "",
          },
        });
      } catch {
        // keep session profile fallback
      } finally {
        if (mounted) setIsProfileLoading(false);
      }
    }

    hydrateProfile();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadTimetableOptions() {
      try {
        const response = await fetch(apiUrl("/api/faculty/profile/timetable/options"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!mounted || !response.ok || !payload.success) return;
        setTimetableOptions({
          branches: Array.isArray(payload.branches) ? payload.branches : [],
          assigned_classes: Array.isArray(payload.assigned_classes) ? payload.assigned_classes : [],
          classes: Array.isArray(payload.classes) ? payload.classes : [],
          classrooms: Array.isArray(payload.classrooms) ? payload.classrooms : [],
          subjects: Array.isArray(payload.subjects) ? payload.subjects : [],
        });
      } catch {
        // keep empty fallback options
      }
    }

    async function loadTimetable() {
      try {
        const response = await fetch(apiUrl("/api/faculty/profile/timetable"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!mounted) return;
        if (!response.ok || !payload.success) {
          setTimetableError(payload.error || payload.message || "Could not load your timetable.");
          return;
        }
        setTimetableSlots(sortTimetableSlots(payload.timetable || []));
        setTimetableDays(Array.isArray(payload.days) && payload.days.length ? payload.days : TIMETABLE_DAYS);
      } catch {
        if (mounted) setTimetableError("Could not load your timetable.");
      } finally {
        if (mounted) setIsTimetableLoading(false);
      }
    }

    loadTimetableOptions();
    loadTimetable();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!editorOpen || editorMode !== "camera" || imageSource) return undefined;

    let cancelled = false;

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setEditorError("Camera is not supported on this device/browser.");
        return;
      }

      setIsStartingCamera(true);
      setEditorError("");
      stopStream();

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      } catch {
        setEditorError("Unable to access camera. You can still upload a photo.");
      } finally {
        if (!cancelled) setIsStartingCamera(false);
      }
    }

    startCamera();
    return () => {
      cancelled = true;
      if (!imageSource) stopStream();
    };
  }, [editorOpen, editorMode, imageSource]);

  useEffect(() => () => stopStream(), []);

  function stopStream() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  function resetEditorState(nextMode = editorMode) {
    setEditorMode(nextMode);
    setImageSource("");
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setEditorError("");
  }

  function openEditor(mode = "upload") {
    setEditorOpen(true);
    resetEditorState(mode);
    setActionMessage("");
  }

  function closeEditor() {
    setEditorOpen(false);
    stopStream();
    resetEditorState("upload");
    setIsStartingCamera(false);
  }

  function handleFileSelect(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setImageSource(String(reader.result || ""));
      setZoom(1);
      setPan({ x: 0, y: 0 });
      setEditorError("");
      stopStream();
    };
    reader.readAsDataURL(file);
  }

  function captureFromCamera() {
    if (!videoRef.current) return;
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 720;
    canvas.height = video.videoHeight || 720;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    setImageSource(canvas.toDataURL("image/jpeg", 0.92));
    setZoom(1);
    setPan({ x: 0, y: 0 });
    stopStream();
  }

  function handlePointerDown(event) {
    if (!imageSource) return;
    const point = event.touches?.[0] || event;
    dragRef.current = {
      startX: point.clientX,
      startY: point.clientY,
      originX: pan.x,
      originY: pan.y,
    };
  }

  function handlePointerMove(event) {
    if (!dragRef.current) return;
    const point = event.touches?.[0] || event;
    const deltaX = point.clientX - dragRef.current.startX;
    const deltaY = point.clientY - dragRef.current.startY;
    setPan({
      x: dragRef.current.originX + deltaX,
      y: dragRef.current.originY + deltaY,
    });
  }

  function handlePointerUp() {
    dragRef.current = null;
  }

  async function saveCroppedPhoto() {
    if (!imageSource || isSaving) return;
    setIsSaving(true);
    setEditorError("");

    try {
      const image = await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = imageSource;
      });

      const stageSize = Math.max(240, Math.round(stageRef.current?.getBoundingClientRect().width || 320));
      const outputSize = 640;
      const baseScale = Math.max(stageSize / image.width, stageSize / image.height);
      const finalScale = baseScale * zoom;
      const drawWidth = image.width * finalScale;
      const drawHeight = image.height * finalScale;
      const scaleRatio = outputSize / stageSize;

      const canvas = document.createElement("canvas");
      canvas.width = outputSize;
      canvas.height = outputSize;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas not available");

      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, outputSize, outputSize);

      const dx = ((stageSize - drawWidth) / 2 + pan.x) * scaleRatio;
      const dy = ((stageSize - drawHeight) / 2 + pan.y) * scaleRatio;
      context.drawImage(image, dx, dy, drawWidth * scaleRatio, drawHeight * scaleRatio);

      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
      if (!blob) throw new Error("Unable to prepare cropped image");

      const formData = new FormData();
      formData.append("photo", blob, "faculty-profile.jpg");

      const response = await fetch(apiUrl("/profile/photo"), {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
      });

      const uploadPayload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(uploadPayload.message || "Photo upload failed");
      }

      const whoami = await fetch(apiUrl("/api/auth/whoami"), {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const payload = await whoami.json().catch(() => ({}));
      if (whoami.ok && payload.authenticated) {
        const user = payload.user || {};
        persistAuth({ token: "session", role: payload.role || getStoredAuthRole(), user });
        setDetails((current) => ({
          ...current,
          name: user.name || current.name,
          email: user.email || current.email,
          department: user.department || current.department,
          role: user.role || current.role,
          photoPath: user.photo_path || current.photoPath,
        }));
      } else {
        setDetails((current) => ({ ...current, photoPath: imageSource }));
      }

      setActionMessage("Profile photo updated successfully.");
      closeEditor();
    } catch (error) {
      setEditorError(error?.message || "Could not save the new profile photo. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  function openTimetableEditor(slot) {
    setTimetableError("");
    setActionMessage("");
    if (slot) {
      const selectedSubject = (timetableOptions.subjects || []).find(
        (item) =>
          String(item.subject_code || item.value || "").trim().toUpperCase() === String(slot.subject_code || "").trim().toUpperCase() ||
          String(item.subject_name || "").trim().toLowerCase() === String(slot.subject || "").trim().toLowerCase()
      );
      setTimetableForm({
        id: slot.id || "",
        day: slot.day || "Monday",
        start_time: slot.start_time || "09:00",
        end_time: slot.end_time || "10:00",
        subject: selectedSubject?.subject_name || slot.subject || "",
        subject_code: selectedSubject?.subject_code || slot.subject_code || "",
        subject_value: selectedSubject?.value || "",
        classroom: slot.classroom || "",
        branch: slot.branch || details.department || "",
        semester: String(slot.semester ?? ""),
        section: slot.section || "A",
        class_value: slot.branch && slot.semester && slot.section ? `${slot.branch}|${slot.semester}|${slot.section}` : "",
      });
    } else {
      setTimetableForm(createEmptyTimetableForm(details));
    }
    setIsEditingTimetable(true);
  }

  function closeTimetableEditor() {
    setIsEditingTimetable(false);
    setIsSavingTimetable(false);
    setTimetableError("");
    setTimetableForm(createEmptyTimetableForm(details));
  }

  async function saveTimetableSlot(event) {
    event.preventDefault();
    if (isSavingTimetable) return;
    setIsSavingTimetable(true);
    setTimetableError("");
    setActionMessage("");

    try {
      const response = await fetch(apiUrl("/api/faculty/profile/timetable"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          ...timetableForm,
          branch: String(timetableForm.branch || "").trim().toUpperCase(),
          section: String(timetableForm.section || "").trim().toUpperCase(),
          semester: String(timetableForm.semester || "").trim(),
          subject: String(timetableForm.subject || "").trim(),
          subject_code: String(timetableForm.subject_code || "").trim().toUpperCase(),
          class_value: selectedClassValue,
          start_time: String(timetableForm.start_time || "").trim(),
          end_time: String(timetableForm.end_time || "").trim(),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error || payload.message || "Could not save timetable slot.");
      }

      setTimetableSlots((current) => {
        const next = current.filter((slot) => slot.id !== payload.slot?.id);
        if (payload.slot) next.push(payload.slot);
        return sortTimetableSlots(next);
      });
      setActionMessage(payload.message || "Timetable updated successfully.");
      closeTimetableEditor();
    } catch (error) {
      setTimetableError(error.message || "Could not save timetable slot.");
    } finally {
      setIsSavingTimetable(false);
    }
  }

  async function deleteTimetableSlot(slot) {
    if (!slot?.id || isDeletingTimetable) return;
    const confirmed = window.confirm(`Delete ${slot.subject || "this slot"} on ${slot.day}?`);
    if (!confirmed) return;

    setIsDeletingTimetable(slot.id);
    setTimetableError("");
    setActionMessage("");

    try {
      const response = await fetch(apiUrl(`/api/faculty/profile/timetable/${slot.id}`), {
        method: "DELETE",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error(payload.error || payload.message || "Could not delete timetable slot.");
      }

      setTimetableSlots((current) => current.filter((item) => item.id !== slot.id));
      setActionMessage(payload.message || "Timetable slot deleted.");
      if (timetableForm.id === slot.id) {
        closeTimetableEditor();
      }
    } catch (error) {
      setTimetableError(error.message || "Could not delete timetable slot.");
    } finally {
      setIsDeletingTimetable("");
    }
  }

  const filteredClassOptions = useMemo(() => {
    const mergedClassMap = new Map();
    for (const item of timetableOptions.assigned_classes || []) {
      if (item?.value) {
        mergedClassMap.set(item.value, item);
      }
    }
    for (const item of timetableOptions.classes || []) {
      if (item?.value) {
        mergedClassMap.set(item.value, item);
      }
    }
    for (const slot of timetableSlots) {
      const branch = String(slot.branch || "").trim().toUpperCase();
      const semester = String(slot.semester ?? "").trim();
      const section = String(slot.section || "").trim().toUpperCase();
      if (!branch || !semester || !section) continue;
      const value = `${branch}|${semester}|${section}`;
      if (!mergedClassMap.has(value)) {
        mergedClassMap.set(value, {
          branch,
          semester: Number(slot.semester),
          section,
          value,
          label: `${branch} / ${semester} / ${section}`,
        });
      }
    }

    const allClassOptions = Array.from(mergedClassMap.values()).sort((first, second) =>
      String(first.label || "").localeCompare(String(second.label || ""))
    );
    const activeBranch = String(timetableForm.branch || "").trim().toUpperCase();
    const matches = allClassOptions.filter((item) => {
      if (!activeBranch) return true;
      return String(item.branch || "").trim().toUpperCase() === activeBranch;
    });
    return matches.length ? matches : allClassOptions;
  }, [timetableForm.branch, timetableForm.section, timetableForm.semester, timetableOptions.assigned_classes, timetableOptions.classes, timetableSlots]);

  const subjectOptions = useMemo(() => {
    const mergedSubjectMap = new Map();
    
    // Only use subjects that are explicitly assigned to the faculty
    for (const item of timetableOptions.subjects || []) {
      const key = String(item.value || item.subject_code || item.subject_name || "").trim();
      if (key) {
        mergedSubjectMap.set(key, item);
      }
    }

    const allSubjects = Array.from(mergedSubjectMap.values()).sort((first, second) => {
      const branchDiff = String(first.branch || "").localeCompare(String(second.branch || ""));
      if (branchDiff !== 0) return branchDiff;
      const semesterDiff = Number(first.semester || 0) - Number(second.semester || 0);
      if (semesterDiff !== 0) return semesterDiff;
      const sectionDiff = String(first.section || "").localeCompare(String(second.section || ""));
      if (sectionDiff !== 0) return sectionDiff;
      return String(first.label || first.subject_name || "").localeCompare(String(second.label || second.subject_name || ""));
    });
    
    return allSubjects;
  }, [timetableOptions.subjects]);

  const availableBranches = useMemo(() => {
    const branchSet = new Set((timetableOptions.branches || []).map((item) => String(item || "").trim().toUpperCase()).filter(Boolean));
    for (const classOption of filteredClassOptions) {
      const branch = String(classOption.branch || "").trim().toUpperCase();
      if (branch) branchSet.add(branch);
    }
    const currentBranch = String(timetableForm.branch || "").trim().toUpperCase();
    if (currentBranch) branchSet.add(currentBranch);
    return Array.from(branchSet).sort();
  }, [filteredClassOptions, timetableForm.branch, timetableOptions.branches]);

  const availableSemesters = useMemo(() => {
    const branch = String(timetableForm.branch || "").trim().toUpperCase();
    const semesterSet = new Set();
    for (const classOption of filteredClassOptions) {
      const classBranch = String(classOption.branch || "").trim().toUpperCase();
      if (branch && classBranch !== branch) continue;
      if (classOption.semester !== undefined && classOption.semester !== null && String(classOption.semester).trim() !== "") {
        semesterSet.add(String(classOption.semester));
      }
    }
    return Array.from(semesterSet).sort((first, second) => Number(first) - Number(second));
  }, [filteredClassOptions, timetableForm.branch]);

  const availableSections = useMemo(() => {
    const branch = String(timetableForm.branch || "").trim().toUpperCase();
    const semester = String(timetableForm.semester || "").trim();
    const sectionSet = new Set();
    for (const classOption of filteredClassOptions) {
      const classBranch = String(classOption.branch || "").trim().toUpperCase();
      const classSemester = String(classOption.semester ?? "").trim();
      if (branch && classBranch !== branch) continue;
      if (semester && classSemester !== semester) continue;
      if (classOption.section) sectionSet.add(String(classOption.section).trim().toUpperCase());
    }
    return Array.from(sectionSet).sort();
  }, [filteredClassOptions, timetableForm.branch, timetableForm.semester]);

  const selectedClassValue = useMemo(() => {
    const branch = String(timetableForm.branch || "").trim().toUpperCase();
    const semester = String(timetableForm.semester || "").trim();
    const section = String(timetableForm.section || "").trim().toUpperCase();
    if (!branch || !semester || !section) return "";
    const matchingClass = filteredClassOptions.find(
      (item) =>
        String(item.branch || "").trim().toUpperCase() === branch &&
        String(item.semester ?? "").trim() === semester &&
        String(item.section || "").trim().toUpperCase() === section
    );
    return matchingClass?.value || `${branch}|${semester}|${section}`;
  }, [filteredClassOptions, timetableForm.branch, timetableForm.section, timetableForm.semester]);

  useEffect(() => {
    if (!isEditingTimetable) return;
    const selectedValue = String(timetableForm.subject_value || "").trim();
    if (!selectedValue) return;
    const stillValid = subjectOptions.some((item) => String(item.value || "").trim() === selectedValue);
    if (!stillValid) {
      setTimetableForm((current) => ({
        ...current,
        subject: "",
        subject_code: "",
        subject_value: "",
      }));
    }
  }, [isEditingTimetable, subjectOptions, timetableForm.subject_value]);

  const infoCards = useMemo(
    () => [
      { label: "Full Name", value: details.name || "Not available", icon: FaUser },
      { label: "Email Address", value: details.email || "Not available", icon: FaEnvelope },
      { label: "Role", value: details.role || "Faculty", icon: FaUserGear },
      { label: "Department", value: details.department || "Not assigned", icon: FaBuilding },
      { label: "Faculty ID", value: details.faculty_id || "N/A", icon: FaIdBadge },
      { label: "Phone", value: details.phone || "N/A", icon: FaPhone },
      { label: "Joined Date", value: details.joined_date || "N/A", icon: FaCalendarDays },
      { label: "Qualification", value: details.qualification || "N/A", icon: FaGraduationCap },
      { label: "Address", value: details.address || "N/A", icon: FaLocationDot, wide: true },
    ],
    [details]
  );

  const cropStyle = imageSource
    ? {
        transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom})`,
      }
    : undefined;

  const timetableRows = useMemo(() => {
    const rowMap = new Map();
    for (const slot of timetableSlots) {
      const key = `${slot.start_time || ""}|${slot.end_time || ""}`;
      if (!rowMap.has(key)) {
        rowMap.set(key, {
          start_time: slot.start_time || "",
          end_time: slot.end_time || "",
        });
      }
    }

    const rows = rowMap.size ? Array.from(rowMap.values()) : DEFAULT_TIMETABLE_ROWS;
    return [...rows].sort((first, second) => {
      const startDiff = timeToMinutes(first.start_time) - timeToMinutes(second.start_time);
      if (startDiff !== 0) return startDiff;
      return timeToMinutes(first.end_time) - timeToMinutes(second.end_time);
    });
  }, [timetableSlots]);

  const timetableGridMap = useMemo(() => {
    const map = {};
    for (const slot of timetableSlots) {
      map[`${slot.day}|${slot.start_time}|${slot.end_time}`] = slot;
    }
    return map;
  }, [timetableSlots]);

  const timetableSummary = useMemo(() => {
    const activeDays = new Set(timetableSlots.map((slot) => slot.day).filter(Boolean)).size;
    const firstSlot = timetableSlots[0];
    return {
      total: timetableSlots.length,
      activeDays,
      firstSlot: firstSlot ? `${firstSlot.day}, ${firstSlot.start_time}` : "No slots yet",
    };
  }, [timetableSlots]);

  async function saveProfileInfo() {
    if (isSavingInfo) return;
    setIsSavingInfo(true);
    setActionMessage("");

    try {
      const response = await fetch(apiUrl("/api/faculty/profile"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(infoForm),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) {
        throw new Error("Profile update failed");
      }

      const next = payload.profile || {};
      setDetails((current) => ({
        ...current,
        ...next,
        photoPath: next.photo_path || current.photoPath,
      }));
      setInfoForm({
        name: next.name || "",
        phone: next.phone || "",
        qualification: next.qualification || "",
        address: next.address || "",
      });
      persistAuth({
        token: "session",
        role: next.role || getStoredAuthRole() || "faculty",
        user: {
          name: next.name || details.name,
          email: next.email || details.email,
          role: next.role || details.role,
          department: next.department || details.department,
          photo_path: next.photo_path || details.photoPath,
        },
      });
      setTimetableForm((current) => ({
        ...current,
        branch: current.branch || next.department || "",
      }));
      setActionMessage("Profile information updated successfully.");
      setIsEditingInfo(false);
    } catch {
      setActionMessage("Could not update profile information.");
    } finally {
      setIsSavingInfo(false);
    }
  }

  return (
    <PageShell
      variant="faculty"
      nav={facultyNav}
      title="Faculty Profile"
      subtitle="Personal details, profile photo settings, and your own timetable."
      profile={profile}
    >
      <section className="faculty-profile-shell">
        <div className="faculty-profile-hero">
          <div className="faculty-profile-photo-card">
            <div className="faculty-profile-photo-frame">
              {details.photoPath ? (
                <img src={details.photoPath} alt={details.name} className="faculty-profile-photo-image" />
              ) : (
                <span>{(details.name || "F").slice(0, 1)}</span>
              )}
            </div>
            <div className="faculty-profile-photo-actions">
              <button type="button" className="primary-btn" onClick={() => openEditor("upload")}>
                <FaCloudArrowUp /> Upload New Photo
              </button>
              <button type="button" className="pagination-btn" onClick={() => openEditor("camera")}>
                <FaCamera /> Use Camera
              </button>
            </div>
          </div>

          <div className="faculty-profile-hero-copy">
            <span className="faculty-profile-kicker">Faculty Profile</span>
            <h2>{details.name}</h2>
            <p>Keep your profile polished with a clear photo, updated details, and a timetable you can manage yourself whenever lectures change.</p>
            {actionMessage ? <div className="faculty-profile-success">{actionMessage}</div> : null}
            <div className="faculty-profile-meta-grid">
              {isProfileLoading
                ? Array.from({ length: 6 }).map((_, index) => (
                    <article key={`profile-skeleton-${index}`} className="faculty-profile-meta-card is-loading">
                      <span className="skeleton-line skeleton-label" />
                      <strong className="skeleton-line skeleton-text" />
                    </article>
                  ))
                : infoCards.map((item) => {
                    const Icon = item.icon;
                    return (
                      <article key={item.label} className={`faculty-profile-meta-card${item.wide ? " wide" : ""}`}>
                        <span>
                          {Icon ? <Icon /> : null}
                          {item.label}
                        </span>
                        <strong>{item.value}</strong>
                      </article>
                    );
                  })}
            </div>
            <div className="faculty-profile-inline-actions">
              <button type="button" className="primary-btn" onClick={() => setIsEditingInfo(true)}>
                <FaPenToSquare /> Edit Information
              </button>
            </div>
          </div>
        </div>

        <section className="faculty-timetable-panel">
          <div className="faculty-timetable-header">
            <div>
              <span className="faculty-profile-kicker">My Timetable</span>
              <h3>Manage your lecture slots</h3>
              <p>Add, update, or remove your own timetable entries here. Dashboard widgets and attendance flows will pick up the same data.</p>
            </div>
            <button type="button" className="primary-btn" onClick={() => openTimetableEditor()}>
              <FaPlus /> Add Slot
            </button>
          </div>

          <div className="faculty-timetable-summary">
            <article className="faculty-timetable-summary-card">
              <span>Total Slots</span>
              <strong>{timetableSummary.total}</strong>
            </article>
            <article className="faculty-timetable-summary-card">
              <span>Active Days</span>
              <strong>{timetableSummary.activeDays}</strong>
            </article>
            <article className="faculty-timetable-summary-card">
              <span>First Slot</span>
              <strong>{timetableSummary.firstSlot}</strong>
            </article>
          </div>

          {timetableError && !isEditingTimetable ? <p className="error-copy">{timetableError}</p> : null}

          <div className="faculty-timetable-matrix-shell">
            {isTimetableLoading ? (
              <div className="faculty-timetable-matrix-loading">
                <div className="skeleton-line skeleton-label" />
                <div className="skeleton-line skeleton-text" />
                <div className="skeleton-line skeleton-text" />
                <div className="skeleton-line skeleton-text" />
              </div>
            ) : (
              <div className="faculty-timetable-matrix-wrap">
                <table className="faculty-timetable-matrix">
                  <thead>
                    <tr>
                      <th>Time</th>
                      {timetableDays.map((day) => (
                        <th key={day}>{day.slice(0, 3)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {timetableRows.map((row) => (
                      <tr key={`${row.start_time}-${row.end_time}`}>
                        <th>
                          <span>{row.start_time}</span>
                          <small>{row.end_time}</small>
                        </th>
                        {timetableDays.map((day) => {
                          const slot = timetableGridMap[`${day}|${row.start_time}|${row.end_time}`];
                          return (
                            <td key={`${day}-${row.start_time}-${row.end_time}`}>
                              <button
                                type="button"
                                className={`faculty-timetable-cell${slot ? " filled" : " empty"}`}
                                onClick={() =>
                                  openTimetableEditor(
                                    slot || {
                                      day,
                                      start_time: row.start_time,
                                      end_time: row.end_time,
                                      branch: details.department || "",
                                      section: "A",
                                    }
                                  )
                                }
                              >
                                {slot ? (
                                  <>
                                    <strong>{slot.subject || "Untitled"}</strong>
                                    <span>{slot.classroom || slot.class_label || "Class not set"}</span>
                                    <small>{slot.class_label || "Class not set"}</small>
                                  </>
                                ) : (
                                  <>
                                    <strong>+ Add</strong>
                                    <span>{day}</span>
                                    <small>Click to add lecture</small>
                                  </>
                                )}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </section>

      {editorOpen ? (
        <div className="photo-cropper-overlay" onMouseUp={handlePointerUp} onTouchEnd={handlePointerUp}>
          <div className="photo-cropper-modal" onClick={(event) => event.stopPropagation()}>
            <div className="photo-cropper-header">
              <div>
                <h3>Edit Profile Photo</h3>
                <p>Upload or capture an image, then drag and zoom to crop it.</p>
              </div>
              <button type="button" className="photo-cropper-close" onClick={closeEditor}>
                <FaXmark />
              </button>
            </div>

            <div className="photo-cropper-toolbar">
              <button type="button" className={`photo-source-btn${editorMode === "upload" ? " active" : ""}`} onClick={() => resetEditorState("upload")}>
                <FaCloudArrowUp /> Upload
              </button>
              <button type="button" className={`photo-source-btn${editorMode === "camera" ? " active" : ""}`} onClick={() => resetEditorState("camera")}>
                <FaCamera /> Camera
              </button>
            </div>

            <div className="photo-cropper-body">
              <div className="photo-cropper-stage-panel">
                {!imageSource && editorMode === "upload" ? (
                  <label className="photo-dropzone">
                    <input type="file" accept="image/*" onChange={handleFileSelect} />
                    <FaCloudArrowUp />
                    <strong>Select a photo</strong>
                    <span>PNG, JPG, JPEG, WEBP and more</span>
                  </label>
                ) : null}

                {!imageSource && editorMode === "camera" ? (
                  <div className="photo-camera-panel">
                    <div className="photo-camera-frame">
                      <video ref={videoRef} muted playsInline autoPlay />
                      {isStartingCamera ? <div className="photo-camera-status">Starting camera...</div> : null}
                    </div>
                    <button type="button" className="primary-btn" onClick={captureFromCamera} disabled={isStartingCamera}>
                      <FaCamera /> Capture Photo
                    </button>
                  </div>
                ) : null}

                {imageSource ? (
                  <div
                    ref={stageRef}
                    className="photo-crop-stage"
                    onMouseDown={handlePointerDown}
                    onMouseMove={handlePointerMove}
                    onMouseLeave={handlePointerUp}
                    onTouchStart={handlePointerDown}
                    onTouchMove={handlePointerMove}
                  >
                    <img src={imageSource} alt="Crop preview" className="photo-crop-image" style={cropStyle} />
                    <div className="photo-crop-mask" />
                  </div>
                ) : null}
              </div>

              <div className="photo-cropper-controls">
                <div className="photo-cropper-card">
                  <div className="photo-cropper-card-head">
                    <FaCropSimple />
                    <strong>Crop Controls</strong>
                  </div>
                  <label className="photo-slider-group">
                    <span>Zoom</span>
                    <input type="range" min="1" max="2.6" step="0.01" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} disabled={!imageSource} />
                  </label>
                  <div className="photo-cropper-actions">
                    <button type="button" className="pagination-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} disabled={!imageSource}>
                      <FaRotateLeft /> Reset Crop
                    </button>
                    <button type="button" className="pagination-btn" onClick={() => resetEditorState(editorMode)}>
                      Choose Again
                    </button>
                  </div>
                  {editorError ? <p className="error-copy">{editorError}</p> : null}
                </div>

                <div className="photo-cropper-card">
                  <div className="photo-cropper-card-head">
                    <FaUser />
                    <strong>Preview Guidance</strong>
                  </div>
                  <ul className="plain-list profile-plain-list">
                    <li>Center your face inside the square crop area.</li>
                    <li>Use a little zoom so the face is clearly visible.</li>
                    <li>Camera capture and file upload both support the same crop flow.</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="photo-cropper-footer">
              <button type="button" className="pagination-btn" onClick={closeEditor}>
                Cancel
              </button>
              <button type="button" className="primary-btn" onClick={saveCroppedPhoto} disabled={!imageSource || isSaving}>
                <FaFloppyDisk /> {isSaving ? "Saving..." : "Save Photo"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isEditingInfo ? (
        <div className="photo-cropper-overlay">
          <div className="photo-cropper-modal profile-edit-modal" onClick={(event) => event.stopPropagation()}>
            <div className="photo-cropper-header">
              <div>
                <h3>Edit Profile Information</h3>
                <p>Update the faculty details shown on your profile page.</p>
              </div>
              <button type="button" className="photo-cropper-close" onClick={() => setIsEditingInfo(false)}>
                <FaXmark />
              </button>
            </div>

            <div className="faculty-profile-form-grid">
              <label className="field-label">
                <span>Full Name</span>
                <input value={infoForm.name} onChange={(event) => setInfoForm((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label className="field-label">
                <span>Phone</span>
                <input value={infoForm.phone} onChange={(event) => setInfoForm((current) => ({ ...current, phone: event.target.value }))} />
              </label>
              <label className="field-label">
                <span>Qualification</span>
                <input value={infoForm.qualification} onChange={(event) => setInfoForm((current) => ({ ...current, qualification: event.target.value }))} />
              </label>
              <label className="field-label faculty-profile-form-wide">
                <span>Address</span>
                <textarea rows={4} value={infoForm.address} onChange={(event) => setInfoForm((current) => ({ ...current, address: event.target.value }))} />
              </label>
            </div>

            <div className="photo-cropper-footer">
              <button type="button" className="pagination-btn" onClick={() => setIsEditingInfo(false)}>
                Cancel
              </button>
              <button type="button" className="primary-btn" onClick={saveProfileInfo} disabled={isSavingInfo}>
                <FaFloppyDisk /> {isSavingInfo ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isEditingTimetable ? (
        <div className="photo-cropper-overlay">
          <div className="photo-cropper-modal profile-edit-modal faculty-timetable-modal" onClick={(event) => event.stopPropagation()}>
            <form onSubmit={saveTimetableSlot}>
              <div className="photo-cropper-header">
                <div>
                  <h3>{timetableForm.id ? "Edit Timetable Slot" : "Add Timetable Slot"}</h3>
                  <p>Set the day, time, class, and room for one lecture slot. Overlapping times for the same day are blocked automatically.</p>
                </div>
                <button type="button" className="photo-cropper-close" onClick={closeTimetableEditor}>
                  <FaXmark />
                </button>
              </div>

              <div className="faculty-timetable-form-grid">
                <label className="field-label">
                  <span>Day</span>
                  <select value={timetableForm.day} onChange={(event) => setTimetableForm((current) => ({ ...current, day: event.target.value }))}>
                    {TIMETABLE_DAYS.map((day) => (
                      <option key={day} value={day}>
                        {day}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  <span>Start Time</span>
                  <select value={timetableForm.start_time} onChange={(event) => setTimetableForm((current) => ({ ...current, start_time: event.target.value }))}>
                    {TIMETABLE_TIME_OPTIONS.map((time) => (
                      <option key={`start-${time}`} value={time}>
                        {time}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  <span>End Time</span>
                  <select value={timetableForm.end_time} onChange={(event) => setTimetableForm((current) => ({ ...current, end_time: event.target.value }))}>
                    {TIMETABLE_TIME_OPTIONS.map((time) => (
                      <option key={`end-${time}`} value={time}>
                        {time}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label faculty-profile-form-wide">
                  <span>Subject</span>
                  <select
                    value={timetableForm.subject_value}
                    onChange={(event) => {
                      const selectedSubject = subjectOptions.find((item) => String(item.value || "").trim() === String(event.target.value || "").trim());
                      setTimetableForm((current) => ({
                        ...current,
                        subject_value: event.target.value,
                        subject_code: selectedSubject?.subject_code || "",
                        subject: selectedSubject?.subject_name || selectedSubject?.label || "",
                        branch: String(selectedSubject?.branch || current.branch || "").trim().toUpperCase(),
                        semester: selectedSubject?.semester !== undefined && selectedSubject?.semester !== null ? String(selectedSubject.semester) : current.semester,
                        section: String(selectedSubject?.section || current.section || "A").trim().toUpperCase(),
                        class_value: selectedSubject ? `${String(selectedSubject.branch || "").trim().toUpperCase()}|${String(selectedSubject.semester ?? "").trim()}|${String(selectedSubject.section || "").trim().toUpperCase()}` : current.class_value,
                        classroom: selectedSubject?.classroom || current.classroom,
                      }));
                    }}
                    disabled={!subjectOptions.length}
                  >
                    <option value="">{subjectOptions.length ? "Select subject" : "No subjects assigned"}</option>
                    {subjectOptions.map((subject) => {
                      const value = String(subject.value || "").trim();
                      const label = subject.label || subject.subject_name || value;
                      return (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      );
                    })}
                  </select>
                </label>
                <label className="field-label">
                  <span>Branch</span>
                  <select
                    value={timetableForm.branch}
                    onChange={(event) =>
                      setTimetableForm((current) => {
                        const nextBranch = event.target.value;
                        const currentClass = (filteredClassOptions || []).find((item) => item.value === current.class_value);
                        const keepCurrentClass = currentClass && currentClass.branch === nextBranch;
                        return {
                          ...current,
                          branch: nextBranch,
                          class_value: keepCurrentClass ? current.class_value : "",
                          semester: keepCurrentClass ? current.semester : "",
                          section: keepCurrentClass ? current.section : "A",
                          subject: keepCurrentClass ? current.subject : "",
                          subject_code: keepCurrentClass ? current.subject_code : "",
                          subject_value: keepCurrentClass ? current.subject_value : "",
                        };
                      })
                    }
                    disabled={Boolean(timetableForm.subject_value)}
                  >
                    <option value="">Select branch</option>
                    {availableBranches.map((branch) => (
                      <option key={branch} value={branch}>
                        {branch}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  <span>Semester</span>
                  <select
                    value={timetableForm.semester}
                    onChange={(event) =>
                      setTimetableForm((current) => ({
                        ...current,
                        semester: event.target.value,
                        class_value: "",
                        section: availableSections.includes(String(current.section || "").trim().toUpperCase()) ? current.section : "A",
                        subject: "",
                        subject_code: "",
                        subject_value: "",
                      }))
                    }
                    disabled={!availableSemesters.length || Boolean(timetableForm.subject_value)}
                  >
                    <option value="">{availableSemesters.length ? "Select semester" : "No semesters found"}</option>
                    {availableSemesters.map((semester) => (
                      <option key={semester} value={semester}>
                        {semester}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  <span>Section</span>
                  <select
                    value={timetableForm.section}
                    onChange={(event) =>
                      setTimetableForm((current) => ({
                        ...current,
                        section: event.target.value,
                        class_value: "",
                        subject: "",
                        subject_code: "",
                        subject_value: "",
                      }))
                    }
                    disabled={!availableSections.length || Boolean(timetableForm.subject_value)}
                  >
                    <option value="">{availableSections.length ? "Select section" : "No sections found"}</option>
                    {availableSections.map((section) => (
                      <option key={section} value={section}>
                        {section}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field-label faculty-profile-form-wide">
                  <span>Classroom</span>
                  <select value={timetableForm.classroom} onChange={(event) => setTimetableForm((current) => ({ ...current, classroom: event.target.value }))}>
                    <option value="">Select classroom</option>
                    {(timetableOptions.classrooms || []).map((classroom) => (
                      <option key={classroom} value={classroom}>
                        {classroom}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {timetableError ? <p className="error-copy faculty-timetable-error">{timetableError}</p> : null}

              <div className="photo-cropper-footer">
                <div className="faculty-timetable-modal-actions">
                  {timetableForm.id ? (
                    <button
                      type="button"
                      className="pagination-btn danger-btn"
                      onClick={() => deleteTimetableSlot({ id: timetableForm.id, subject: timetableForm.subject, day: timetableForm.day })}
                      disabled={isDeletingTimetable === timetableForm.id}
                    >
                      <FaTrash /> {isDeletingTimetable === timetableForm.id ? "Deleting..." : "Delete Slot"}
                    </button>
                  ) : null}
                  <button type="button" className="pagination-btn" onClick={closeTimetableEditor}>
                    Cancel
                  </button>
                </div>
                <button type="submit" className="primary-btn" disabled={isSavingTimetable}>
                  <FaFloppyDisk /> {isSavingTimetable ? "Saving..." : timetableForm.id ? "Update Slot" : "Add Slot"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

export default FacultyProfile;

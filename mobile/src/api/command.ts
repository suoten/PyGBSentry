import { request } from "@/utils/request";

export interface CommandSession {
  id: string;
  alarm_id?: string;
  title?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  participant_count?: number;
  instruction_count?: number;
  last_instruction_at?: string;
  duration_sec?: number;
}

export interface CommandParticipant {
  id: string;
  session_id: string;
  user_id: string;
  username: string;
  role: string;
  joined_at?: string;
}

export interface CommandInstruction {
  id: string;
  session_id: string;
  content: string;
  user_id?: string;
  created_at?: string;
}

export function createSession(alarmId?: string, title?: string) {
  return request<{ id: string; status?: string; title?: string }>({
    url: "/api/v1/command/sessions",
    method: "POST",
    data: {
      alarm_id: alarmId || null,
      title: title || null
    }
  });
}

export function listSessions(status = "", limit = 20, keyword = "") {
  const qStatus = encodeURIComponent(String(status || ""));
  const qLimit = encodeURIComponent(String(limit));
  const qKeyword = encodeURIComponent(String(keyword || ""));
  return request<CommandSession[]>({
    url: `/api/v1/command/sessions?status=${qStatus}&limit=${qLimit}&keyword=${qKeyword}`
  });
}

export function joinSession(sessionId: string, role = "participant") {
  return request<{ ok: boolean; session_id: string }>({
    url: `/api/v1/command/sessions/${encodeURIComponent(sessionId)}/join`,
    method: "POST",
    data: { role }
  });
}

export function closeSession(sessionId: string, summary = "") {
  return request<{ ok: boolean; session_id: string }>({
    url: `/api/v1/command/sessions/${encodeURIComponent(sessionId)}/close`,
    method: "POST",
    data: { summary }
  });
}

export function listParticipants(sessionId: string, role = "") {
  const qRole = encodeURIComponent(String(role || ""));
  return request<CommandParticipant[]>({
    url: `/api/v1/command/sessions/${encodeURIComponent(sessionId)}/participants?role=${qRole}`
  });
}

export function listInstructions(sessionId: string, limit = 50, keyword = "", sinceAt = "") {
  const qKeyword = encodeURIComponent(String(keyword || ""));
  const qSinceAt = encodeURIComponent(String(sinceAt || ""));
  return request<CommandInstruction[]>({
    url: `/api/v1/command/instructions?session_id=${encodeURIComponent(sessionId)}&limit=${encodeURIComponent(String(limit))}&keyword=${qKeyword}&since_at=${qSinceAt}`
  });
}

export function createInstruction(sessionId: string, content: string) {
  return request<CommandInstruction>({
    url: "/api/v1/command/instructions",
    method: "POST",
    data: {
      session_id: sessionId,
      content
    }
  });
}

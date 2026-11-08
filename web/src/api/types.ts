export interface OverviewStats {
  total_students: number;
  total_units: number;
  active_questions: number;
  submissions_today: number;
  approved_assignments: number;
  decided_assignments: number;
  approval_rate: number;
}

export interface UnitSummary {
  code: string;
  title: string;
  active_questions: number;
  students_started: number;
  average_points: number;
}

export interface OverviewResponse {
  stats: OverviewStats;
  units: UnitSummary[];
}

export interface StudentGradesSummary {
  registration: string;
  email: string;
  name: string | null;
  class_group: string | null;
  grades_by_unit: Record<string, number>;
  total_points: number;
}

export interface StudentsResponse {
  students: StudentGradesSummary[];
}

export type AttemptStatus = "running" | "passed" | "failed" | "error";
export type AssignmentState = "pending" | "passed" | "exhausted" | "replaced";

export interface AttemptDetail {
  id: number;
  number: number;
  status: AttemptStatus;
  tests_total: number | null;
  tests_passed: number | null;
  output: string | null;
  code: string;
  started_at: string;
  finished_at: string | null;
}

export interface AssignmentHistoryItem {
  id: number;
  unit_code: string;
  question_slug: string;
  question_title: string;
  round: number;
  state: AssignmentState;
  points: number;
  created_at: string;
  attempts: AttemptDetail[];
}

export interface StudentInfo {
  registration: string;
  email: string;
  name: string | null;
  class_group: string | null;
  created_at: string;
}

export interface StudentDetailReport {
  student: StudentInfo;
  grades_by_unit: Record<string, number>;
  total_points: number;
  assignments: AssignmentHistoryItem[];
}

export interface QuestionRateStat {
  slug: string;
  title: string;
  active: boolean;
  assigned_count: number;
  passed_count: number;
  exhausted_count: number;
  pending_count: number;
  pass_rate: number;
  avg_attempts: number;
}

export interface UnitDetailReport {
  code: string;
  title: string;
  questions: QuestionRateStat[];
}


export interface StudentCreateInput {
  registration: string;
  email: string;
  name?: string | null;
  class_group?: string | null;
}

export interface StudentUpdateInput {
  email: string;
  name?: string | null;
  class_group?: string | null;
}

export interface StudentMutationResponse {
  registration: string;
  email: string;
  name: string | null;
  class_group: string | null;
}

export interface ImportIssue {
  line_number: number;
  message: string;
}

export interface ImportCsvReport {
  created: number;
  updated: number;
  unchanged: number;
  has_errors: boolean;
  errors: ImportIssue[];
  warnings: ImportIssue[];
}

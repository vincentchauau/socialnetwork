import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicantCard } from "../../app/job/employer/[id]/applicant-card";
import JobPage from "../../app/job/job/[id]/page";
import { NEXT_STATUSES, hasResume, languagesToText, parseLanguages, parseLines, parseSkills, resumeFromProfile, skillsToText } from "../../app/job/lib";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 2, username: "bob", group: "user" } }) }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "7" }), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

const job = {
  id: 7, title: "Backend Engineer", company: "Acme", department: "Platform", location: "Hà Nội", remote: false, employment_type: "full_time",
  seniority: "senior", openings: 2, salary_min: 1000, salary_max: 2000, currency: "USD", salary_period: "month", snippet: "", tags: ["python"],
  status: "open", expired: false, expires_at: null, created_at: "2025-01-01T00:00:00Z", owner_username: "alice", is_owner: false, applied: false, saved: false,
  application_count: null, description: "Build services.", experience_min_years: 5, education_min: "bachelor",
  skills_required: [{ name: "Python", level: "advanced", years: 4 }], skills_preferred: [{ name: "Kubernetes", level: null, years: null }],
  languages: [{ language: "English", proficiency: "fluent" }], responsibilities: ["Design services"], benefits: ["Health insurance"],
  match: { score: 72, matched: ["Python"], partial: [], missing: ["SQL"], missing_preferred: ["Kubernetes"] },
};

const profile = {
  headline: "Dev", summary: "Builds things", skills: [{ name: "Python", level: "expert", years: 6 }],
  experience: [{ company: "Acme", title: "Engineer", start: "2020-01", end: null, description: "built", type: "full_time" }],
  education: [{ school: "HUST", degree: "BSc", field: "CS", start: "2015-09", end: "2019-06" }], languages: [{ language: "English", proficiency: "fluent" }],
  visibility: {}, email: "private@example.com",
};

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string) => {
    if (url.includes("/auth/me/profile")) return profile;
    return job;
  });
});

describe("the helpers of the structure", () => {
  it("reads skills from lines, with a level and the years when they are there", () => {
    expect(parseSkills("Python\nSQL, advanced, 3\n  \nGo, 2")).toEqual([
      { name: "Python", level: null, years: null },
      { name: "SQL", level: "advanced", years: 3 },
      { name: "Go", level: null, years: 2 },
    ]);
    expect(skillsToText(parseSkills("SQL, advanced, 3"))).toBe("SQL, advanced, 3");
  });

  it("reads languages and lines", () => {
    expect(parseLanguages("English, fluent\nFrench\nGerman, alien")).toEqual([
      { language: "English", proficiency: "fluent" },
      { language: "French", proficiency: "conversational" },
      { language: "German", proficiency: "conversational" },
    ]);
    expect(languagesToText(parseLanguages("English, fluent"))).toBe("English, fluent");
    expect(parseLines(" a \n\nb")).toEqual(["a", "b"]);
  });

  it("takes only the resume part of the profile of an account, cut to the limits", () => {
    const resume = resumeFromProfile({ ...profile, headline: "x".repeat(500), skills: Array.from({ length: 80 }, (_, i) => ({ name: `s${i}`, level: "godlike" })) });
    expect(resume.headline).toHaveLength(120);
    expect(resume.skills).toHaveLength(50);
    expect(resume.skills[0].level).toBeNull();
    expect(Object.keys(resume).sort()).toEqual(["education", "experience", "headline", "languages", "skills", "summary"]); // nothing private (email...) comes along
    expect(hasResume(resumeFromProfile({}))).toBe(false);
    expect(hasResume(resumeFromProfile(profile))).toBe(true);
  });

  it("knows the steps an employer can take", () => {
    expect(NEXT_STATUSES.submitted).not.toContain("offer");
    expect(NEXT_STATUSES.interview).toContain("offer");
    expect(NEXT_STATUSES.hired).toEqual([]);
  });
});

describe("the page of a job", () => {
  it("shows what the job asks of a person", async () => {
    render(<JobPage />);
    expect(await screen.findByRole("heading", { name: "Backend Engineer" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Kỹ năng bắt buộc" })).toHaveTextContent("Python · Advanced · 4 năm");
    expect(screen.getByRole("list", { name: "Kỹ năng ưu tiên" })).toHaveTextContent("Kubernetes");
    expect(screen.getByText(/Từ 5 năm kinh nghiệm/)).toBeInTheDocument();
    expect(screen.getByText("Design services")).toBeInTheDocument();
    expect(screen.getByText("Health insurance")).toBeInTheDocument();
    expect(screen.getByText(/Platform · 2 vị trí/)).toBeInTheDocument();
  });

  it("tells how well the skills of the viewer fit", async () => {
    render(<JobPage />);
    await screen.findByRole("heading", { name: "Backend Engineer" });
    expect(screen.getByText("Phù hợp với kỹ năng yêu cầu: 72%")).toBeInTheDocument();
    expect(screen.getByText("SQL", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Kubernetes", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Python", { selector: "span" })).toBeInTheDocument();
  });

  it("sends the profile of the account with the application", async () => {
    const user = userEvent.setup();
    render(<JobPage />);
    await screen.findByRole("heading", { name: "Backend Engineer" });
    expect(await screen.findByRole("checkbox", { name: "Gửi kèm hồ sơ của tôi" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Gửi đơn ứng tuyển" }));
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).endsWith("/apply"))).toBe(true));
    const call = api.mock.calls.find(([url]) => String(url).endsWith("/apply"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.resume.headline).toBe("Dev");
    expect(body.resume.skills[0]).toEqual({ name: "Python", level: "expert", years: 6 });
    expect(body.resume.email).toBeUndefined();
  });
});

describe("an applicant to a job", () => {
  const applicant = {
    id: 3, job_id: 7, applicant_username: "carol", status: "reviewing", cover_letter: "", contact_email: null, note: "",
    resume: resumeFromProfile(profile),
    match: { score: 40, matched: ["Python"], partial: [], missing: ["SQL", "Docker"], missing_preferred: [] },
    history: [{ status: "submitted", at: "2025-01-02T00:00:00Z", by: "applicant" }, { status: "reviewing", at: "2025-01-03T00:00:00Z", by: "employer" }],
    created_at: "2025-01-02T00:00:00Z", updated_at: "2025-01-03T00:00:00Z",
  } as const;

  it("shows the resume, each step of the application, and only the steps that can come next", () => {
    render(<ApplicantCard applicant={applicant as never} onChange={vi.fn()} />);
    expect(screen.getByText("Phù hợp với kỹ năng yêu cầu: 40%")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "SQL" })).not.toBeInTheDocument(); // the employer is not sent to learn it
    expect(screen.getByText("Dev")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Kỹ năng" })).toHaveTextContent("Python · Expert · 6 năm");
    expect(screen.getByText(/Engineer/)).toBeInTheDocument();
    const steps = screen.getByRole("list", { name: "Tiến trình" });
    expect(steps).toHaveTextContent("Submitted");
    expect(steps).toHaveTextContent("ứng viên");
    expect(steps).toHaveTextContent("nhà tuyển dụng");
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Reviewing", "Shortlisted", "Interview", "Rejected", "Hired"]);
  });
});

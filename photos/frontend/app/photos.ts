import { ApiError, apiFetch } from "@sn/api";

export const API = "/api/photos";
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const MAX_TEXT_CHARS = 500;
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
export const PAGE_SIZE = 12;

export interface Photo {
  id: number;
  username: string;
  caption: string | null;
  width: number;
  height: number;
  created_at: string;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
  is_mine: boolean;
  image_url: string;
  thumb_url: string;
}

export interface PhotoPage {
  items: Photo[];
  next_cursor: number | null;
}

export interface PhotoComment {
  id: number;
  photo_id: number;
  username: string;
  content: string;
  created_at: string;
}

export interface LikeState {
  liked: boolean;
  like_count: number;
}

export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Client-side pre-check; the server re-validates by content. Returns an error message or null. */
export function validateFile(file: { size: number; type: string } | null): string | null {
  if (!file) return "Choose an image first";
  if (file.size === 0) return "The file is empty";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than 5 MB";
  if (!ACCEPTED_TYPES.includes(file.type)) return "Only JPEG, PNG, WebP and GIF images are accepted";
  return null;
}

/** Newest-first list with the next page appended; ids already present are skipped. */
export function appendUnique(current: Photo[], next: Photo[]): Photo[] {
  const seen = new Set(current.map((photo) => photo.id));
  return [...current, ...next.filter((photo) => !seen.has(photo.id))];
}

export function replacePhoto(photos: Photo[], updated: Photo): Photo[] {
  return photos.map((photo) => (photo.id === updated.id ? updated : photo));
}

export function pageUrl(path: string, cursor: number | null): string {
  const cursorPart = cursor === null ? "" : `&cursor=${cursor}`;
  return `${API}${path}?limit=${PAGE_SIZE}${cursorPart}`;
}

export function fetchPage(path: string, cursor: number | null): Promise<PhotoPage> {
  return apiFetch<PhotoPage>(pageUrl(path, cursor));
}

export async function uploadPhoto(file: File, caption: string): Promise<Photo> {
  const form = new FormData();
  form.append("file", file);
  if (caption.trim()) form.append("caption", caption.trim());
  const response = await fetch(`${API}/photos`, { method: "POST", credentials: "include", body: form });
  if (!response.ok) {
    let message = `Upload failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as Photo;
}

export function setLike(id: number, liked: boolean): Promise<LikeState> {
  return apiFetch<LikeState>(`${API}/photos/${id}/like`, { method: liked ? "PUT" : "DELETE" });
}

export function deletePhoto(id: number): Promise<void> {
  return apiFetch<void>(`${API}/photos/${id}`, { method: "DELETE" });
}

export function fetchComments(id: number): Promise<PhotoComment[]> {
  return apiFetch<PhotoComment[]>(`${API}/photos/${id}/comments`);
}

export function postComment(id: number, content: string): Promise<PhotoComment> {
  return apiFetch<PhotoComment>(`${API}/photos/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function deleteComment(id: number): Promise<void> {
  return apiFetch<void>(`${API}/comments/${id}`, { method: "DELETE" });
}

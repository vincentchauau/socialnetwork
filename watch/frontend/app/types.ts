export const API = "/api/watch";

export interface Video {
  id: number;
  title: string;
  description: string;
  tags: string[];
  owner: string;
  owner_id: number;
  content_type: string;
  size_bytes: number;
  views: number;
  created_at: string;
}

export interface VideoDetail extends Video {
  in_watchlist: boolean;
  progress_seconds: number;
}

export interface VideoPage {
  items: Video[];
  next_cursor: number | null;
}

export interface HistoryItem {
  video: Video;
  seconds: number;
  updated_at: string;
}

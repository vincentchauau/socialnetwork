import { formatSize } from "./format";
import type { Video } from "./types";

export default function VideoList({ videos, empty }: { videos: Video[]; empty: string }) {
  if (videos.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="grid">
      {videos.map((video) => (
        <li key={video.id}>
          <article className="card stack">
            <h2 style={{ fontSize: "1.1rem", margin: 0 }}>
              <a href={`/watch/v/${video.id}`}>{video.title}</a>
            </h2>
            <span className="muted">
              {video.owner} · {video.views} {video.views === 1 ? "view" : "views"} ·{" "}
              {formatSize(video.size_bytes)}
            </span>
            {video.tags.length > 0 && (
              <ul className="tags" aria-label="Tags">
                {video.tags.map((tag) => (
                  <li key={tag} className="tag">
                    {tag}
                  </li>
                ))}
              </ul>
            )}
          </article>
        </li>
      ))}
    </ul>
  );
}

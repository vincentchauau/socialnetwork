"use client";

import { Gate } from "./Gate";
import { PhotoList } from "./PhotoList";
import { UploadForm } from "./UploadForm";

export default function FeedPage() {
  return (
    <Gate title="Photos">
      {(user) => (
        <div className="stack">
          <a href="/">← Home</a>
          <h1>Photos</h1>
          <p className="muted">
            Signed in as <a href={`/photos/u/${encodeURIComponent(user.username)}`}>{user.username}</a>
          </p>
          <PhotoList
            path="/photos"
            me={user.username}
            emptyText="No photos yet. Upload the first one!"
            header={(onUploaded) => <UploadForm onUploaded={onUploaded} />}
          />
        </div>
      )}
    </Gate>
  );
}

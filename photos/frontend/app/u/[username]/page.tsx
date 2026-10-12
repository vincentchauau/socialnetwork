"use client";

import { useParams } from "next/navigation";

import { Gate } from "../../Gate";
import { PhotoList } from "../../PhotoList";

export default function ProfilePage() {
  const params = useParams<{ username: string }>();
  const username = decodeURIComponent(params.username);
  return (
    <Gate title="Photos">
      {(user) => (
        <div className="stack">
          <a href="/">← Home</a>
          <p>
            <a href="/photos">All photos</a>
          </p>
          <h1>Photos by {username}</h1>
          <PhotoList
            key={username}
            path={`/users/${encodeURIComponent(username)}/photos`}
            me={user.username}
            emptyText={`${username} has not shared any photos yet.`}
          />
        </div>
      )}
    </Gate>
  );
}

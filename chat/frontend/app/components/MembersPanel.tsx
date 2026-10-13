import type { Presence } from "../protocol";

export default function MembersPanel({ presence }: { presence: Presence | null }) {
  if (!presence) {
    return (
      <section className="members" aria-label="Thành viên">
        <h3>Đang trong phòng</h3>
        <p className="muted small">Đang tải…</p>
      </section>
    );
  }
  const hidden = Math.max(0, presence.total - presence.members.length);
  return (
    <section className="members" aria-label="Thành viên">
      <h3>{`Đang trong phòng (${presence.total})`}</h3>
      <ul>
        {presence.members.map((member) => (
          <li key={member.userId}>{member.username}</li>
        ))}
      </ul>
      {hidden > 0 && <p className="muted small">{`+${hidden} người khác`}</p>}
    </section>
  );
}

export default function GuideSection() {
  return (
    <details className="card">
      <summary>Khi nào dùng cái nào?</summary>
      <ul className="lab-list">
        <li>
          <strong>RabbitMQ</strong>: giao việc làm một lần. Có người nhận, xử lý xong thì tin bị xoá.
        </li>
        <li>
          <strong>Kafka</strong>: lưu sự kiện, nhiều bên cùng đọc và có thể đọc lại từ đầu.
        </li>
        <li>
          <strong>gRPC</strong>: hỏi đáp tức thì giữa hai dịch vụ, cần kết quả ngay.
        </li>
      </ul>
    </details>
  );
}

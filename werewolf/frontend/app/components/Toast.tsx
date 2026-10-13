/** Error/notice toast: announced to screen readers, closable with the keyboard. */
export default function Toast({ message, onClose }: { message: string | null; onClose: () => void }) {
  return (
    <div className="ww-toast-slot">
      {message && (
        <div className="ww-toast" role="alert">
          <span>{message}</span>
          <button type="button" className="secondary" onClick={onClose} aria-label="Đóng thông báo">
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

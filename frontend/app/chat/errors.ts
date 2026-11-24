import { ApiError } from "@sn/api";
import { tr } from "./i18n";

/** The words the chat server uses (English), by the text of the interface that says the same. */
const KNOWN: Record<string, () => string> = {
  "You cannot message this person": () => tr("sc_e_khong_nhan_tin_duoc"),
  "You are friends already": () => tr("sc_e_da_la_ban"),
  "You have asked already": () => tr("sc_e_da_gui_loi_moi"),
  "Too many friend requests": () => tr("sc_e_qua_nhieu_loi_moi"),
  "Too many reports": () => tr("sc_e_qua_nhieu_bao_cao"),
  "Person not found": () => tr("sc_e_khong_thay_nguoi_nay"),
  "No request from this person": () => tr("sc_e_khong_co_loi_moi"),
  "Origin not allowed": () => tr("rm_e_origin"),
  "Too many rooms": () => tr("rm_e_too_many_rooms"),
  "That address is already used": () => tr("rm_e_address_used"),
  "Moderators only": () => tr("rm_e_moderators_only"),
  "Only the owner can do this": () => tr("rm_e_owner_only"),
  "Member not found": () => tr("rm_e_member_not_found"),
  "The owner cannot be changed": () => tr("rm_e_owner_untouchable"),
  "Only the owner can change a moderator": () => tr("rm_e_owner_changes_moderator"),
  "Only the owner can change roles": () => tr("rm_e_owner_changes_roles"),
  "Only the owner can remove a moderator": () => tr("rm_e_owner_changes_moderator"),
  "Message not found": () => tr("rm_e_message_not_found"),
  "You cannot delete this message": () => tr("rm_e_cannot_delete"),
  "Choose another active member": () => tr("rm_e_choose_active"),
  "The person has to join again": () => tr("rm_e_join_again"),
  "Hand the room over to someone before you leave": () => tr("rm_e_hand_over"),
  "Only the owner can bring back someone who was sent away": () => tr("rm_e_sent_away"),
  "The report was looked at already": () => tr("sc_e_bao_cao_da_xu_ly"),
  "Report not found": () => tr("sc_e_khong_thay_bao_cao"),
  "Too many requests": () => tr("rm_e_too_many_requests"),
  "Too many requests, slow down": () => tr("rm_e_too_many_requests"),
  // The Werewolf game of a room (the chat seats the member in it, or says why not):
  "The game has started": () => tr("rm_ww_started"),
  "The game is full": () => tr("rm_ww_full"),
  "You are in too many games": () => tr("rm_ww_too_many_rooms"),
  "No room left for a game": () => tr("rm_ww_busy"),
  "Choose someone else": () => tr("rm_e_choose_someone_else"),
  "The room already has more members than that": () => tr("rm_e_capacity_below_members"),
  "closes_at must be after opens_at": () => tr("rm_e_window"),
  "A private room is joined with an invitation or approval, not openly": () => tr("rm_e_private_open"),
  "A direct chat cannot be changed": () => tr("rm_e_dm_fixed"),
  "Room is full": () => tr("rm_e_room_full"),
  "This room is by invitation": () => tr("rm_e_invite_only"),
  "Room not found": () => tr("rm_khong_tim_thay_phong"),
  "You are not a member of this room": () => tr("rm_ban_chua_la_thanh_vien"),
  "Waiting for approval": () => tr("rm_dang_cho_duyet"),
  "You are banned from this room": () => tr("rm_ban_bi_chan"),
  "Room is not open": () => tr("rm_phong_dang_khong_mo"),
  "You are muted": () => tr("rm_ban_dang_bi_tat_tieng"),
  "Only moderators can post here": () => tr("rm_chi_quan_tri_moi_duoc_dang"),
};

/** The text for a failed call: the server's reason in the language of the page when it is a known one, else a general text. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const known = KNOWN[error.message];
    if (known) return known();
    // A rule the room's fields refuse (422) comes as a list the shared client shortens: say it plainly.
    return error.message || tr("da_xay_ra_loi_hay_thu");
  }
  if (error instanceof TypeError) return tr("khong_ket_noi_duoc_may_chu");
  return error instanceof Error && error.message ? error.message : tr("da_xay_ra_loi_hay_thu");
}

/** The text for a failed call of the people side (the same words as `errorMessage`). */
export const socialError = errorMessage;

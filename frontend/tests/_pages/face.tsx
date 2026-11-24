import { AuthGate } from "@sn/compounds/AuthGate";
import FaceApp from "../../app/face/components/FaceApp";
import { tr } from "../../app/face/i18n";

export default function FacePage() {
  return <AuthGate title={tr("phan_tich_doi_xung_khuon_mat")}>{() => <FaceApp />}</AuthGate>;
}

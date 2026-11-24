"use client";

import { AuthGate } from "@sn/compounds/AuthGate";
import FaceApp from "../components/FaceApp";
import { tr } from "../i18n";

export default function FacePage() {
  return <AuthGate title={tr("phan_tich_doi_xung_khuon_mat")}>{() => <FaceApp />}</AuthGate>;
}

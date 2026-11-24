import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import type { PublicKeyCredentialCreationOptionsJSON, PublicKeyCredentialRequestOptionsJSON } from "@simplewebauthn/browser";
import { tr } from "../i18n";

export const PASSKEY_CANCELLED = tr("ban_da_huy_hoac_thiet_bi");
export const PASSKEY_UNSUPPORTED = tr("trinh_duyet_nay_khong_ho_tro");
export const PASSKEY_DUPLICATE_DEVICE = tr("thiet_bi_nay_da_co_passkey");

/** A browser/device ceremony that failed locally (cancelled, timed out, nothing suitable); never a server error. */
class PasskeyCeremonyError extends Error {}

function ceremonyError(error: unknown): unknown {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "AbortError") return new PasskeyCeremonyError(PASSKEY_CANCELLED);
  if (name === "InvalidStateError") return new PasskeyCeremonyError(PASSKEY_DUPLICATE_DEVICE);
  return error;
}

/** Ask the device to sign in with a passkey (options come from the server as opaque JSON). */
export async function getPasskeyCredential(options: unknown) {
  try {
    return await startAuthentication({ optionsJSON: options as PublicKeyCredentialRequestOptionsJSON });
  } catch (error) {
    throw ceremonyError(error);
  }
}

/** Ask the device to create a new passkey. */
export async function createPasskeyCredential(options: unknown) {
  try {
    return await startRegistration({ optionsJSON: options as PublicKeyCredentialCreationOptionsJSON });
  } catch (error) {
    throw ceremonyError(error);
  }
}

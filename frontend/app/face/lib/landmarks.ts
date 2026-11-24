/** MediaPipe FaceMesh landmark index groups (ported from the original demo). */

export const FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109];

export const EAR_LEFT = [234, 127, 162, 21, 54, 103, 67, 109];
export const EAR_RIGHT = [454, 356, 389, 251, 284, 332, 297, 338];

export const EYE_LEFT = [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7];
export const EYE_RIGHT = [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249];
export const EYE_LEFT_CORNER = 33;
export const EYE_RIGHT_CORNER = 263;

export const NOSE_LEFT = [193, 245, 128, 114, 217, 198, 209, 49, 64, 240, 98, 97, 2];
export const NOSE_RIGHT = [417, 465, 357, 343, 437, 420, 429, 279, 294, 460, 327, 326, 2];
export const NOSE_CENTER = [168, 6, 197, 195, 5, 4, 1];

export const MOUTH_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146];
export const MOUTH_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95];

/** Ear anchors used for the ear outline: top, middle, bottom. */
export const EAR_ANCHORS = {
  left: { top: 127, mid: 234, bottom: 132 },
  right: { top: 356, mid: 454, bottom: 361 },
} as const;

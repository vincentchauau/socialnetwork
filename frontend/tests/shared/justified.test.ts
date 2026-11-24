import { justifiedRows } from "@sn/compounds/galleryModel";
import { describe, expect, it } from "vitest";

describe("justifiedRows", () => {
  it("fills every full row to the width, keeps the shapes, and keeps the last row between the target height and a quarter more", () => {
    const rows = justifiedRows([1.5, 1, 1, 1.5, 1, 1, 2], 600, 200, 4);
    for (const row of rows.slice(0, -1)) {
      const used = row.reduce((sum, place) => sum + place.width, 0) + 4 * (row.length - 1);
      expect(Math.abs(used - 600)).toBeLessThanOrEqual(row.length); // the rounding of each width
    }
    expect(rows.at(-1)!.every((place) => place.height >= 200 && place.height <= 250)).toBe(true);
    expect(rows.flat().map((place) => place.index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("keeps the shape of an item and survives a missing or silly proportion", () => {
    const [row] = justifiedRows([2, Number.NaN, 0, 100], 10_000, 100, 0);
    expect(row.map((place) => place.width)).toEqual([200, 100, 100, 300]);
  });

  it("grows a last row that is nearly full a little, and leaves a short one at the target height", () => {
    const nearly = justifiedRows([1, 1, 1, 1, 1], 600, 100, 0).at(-1)!; // 500 of 600 wide: grown to fill, at most 1.25 times the target
    expect(nearly.every((place) => place.height === 120)).toBe(true);
    const short = justifiedRows([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 600, 100, 0).at(-1)!; // one item: stays
    expect(short.map((place) => place.height)).toEqual([100]);
  });

  it("is empty for no items", () => {
    expect(justifiedRows([], 600, 200, 4)).toEqual([]);
  });
});

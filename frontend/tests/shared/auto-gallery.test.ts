import { autoGalleryConfig } from "@sn/compounds/galleryModel";
import type { TableInfo } from "@sn/compounds/crudModel";
import { describe, expect, it } from "vitest";

const col = (name: string, type: string, extra: object = {}) => ({ name, type, nullable: false, readonly: false, secret: false, ...extra });
const table = (columns: object[], pk = ["id"]): TableInfo => ({ name: "t", label: "T", pk, writable: true, columns: columns as TableInfo["columns"] });

describe("autoGalleryConfig", () => {
  it("makes cards from the description: a title by name, the picture, a badge, a body and a few facts", () => {
    const config = autoGalleryConfig(table([col("id", "int"), col("user_id", "int"), col("caption", "string"), col("image_name", "string", { media: { kind: "image", preview: "@self" } }), col("category", "string"), col("note", "text"), col("created_at", "datetime"), col("token", "string", { secret: true })]));
    expect(config).toMatchObject({ title: "caption", image: "image_name", badge: "category", body: "note", density: "media" });
    expect(config.meta).toEqual([]); // a card that leans on its picture shows no facts until the Columns menu asks for them
    expect(autoGalleryConfig(table([col("id", "int"), col("name", "string"), col("created_at", "datetime")])).meta).toEqual(["id", "created_at"]);
  });

  it("falls back to the first text column, then to the key, and never uses a secret", () => {
    expect(autoGalleryConfig(table([col("id", "int"), col("label_x", "string"), col("password_hash", "string", { secret: true })])).title).toBe("label_x");
    expect(autoGalleryConfig(table([col("id", "int"), col("n", "int")])).title).toBe("id");
  });
});

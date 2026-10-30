// Seed data mirrored from backend/seed (docs/data.md). Mock mode only; no Date/random at module load
// (Next Cache Components prerenders client modules).
import type { Goal, MerchantProfile, Product } from "@/lib/types";

export const MERCHANT: MerchantProfile = {
  merchant_id: "M001",
  shop_name: "Lakshmi Fashions",
  shop_description: "Men's and women's everyday clothing and accessories in Ameerpet, Hyderabad",
  languages: ["hi-IN", "te-IN", "kn-IN", "en-IN"],
  negotiation_instructions: "Hold the price at first. Suggest quantity deals. Always be polite and warm.",
  bundle_allowed: true,
  qr_token: "hermion-m001-demo",
};

type Row = [string, string, string, Record<string, string>, string[], number, number | null, number, number, number, boolean];
const rows: Row[] = [
  ["SHIRT-BLU-M", "Men's cotton shirt, blue", "shirts", { size: "M", colour: "blue", fabric: "cotton" }, ["shirt", "kameez", "chokka"], 1000, 800, 750, 630, 15, true],
  ["SHIRT-BLU-L", "Men's cotton shirt, blue", "shirts", { size: "L", colour: "blue", fabric: "cotton" }, ["shirt", "kameez", "chokka"], 1000, 800, 750, 630, 2, true],
  ["SHIRT-WHT-M", "Men's cotton shirt, white", "shirts", { size: "M", colour: "white", fabric: "cotton" }, ["shirt", "kameez", "chokka"], 950, 780, 720, 600, 10, true],
  ["SHIRT-WHT-XL", "Men's cotton shirt, white", "shirts", { size: "XL", colour: "white", fabric: "cotton" }, ["shirt", "kameez", "chokka"], 950, 780, 720, 600, 0, true],
  ["BELT-BRN-32", "Leather belt, brown", "belts", { size: "32", colour: "brown", material: "leather" }, ["belt", "patta"], 500, 400, 300, 220, 12, true],
  ["BELT-BLK-34", "Leather belt, black", "belts", { size: "34", colour: "black", material: "leather" }, ["belt", "patta"], 500, 400, 300, 220, 8, true],
  ["KURTA-MRN-M", "Men's cotton kurta, maroon", "kurtas", { size: "M", colour: "maroon", fabric: "cotton" }, ["kurta"], 1400, 1150, 1050, 850, 9, true],
  ["KURTA-MRN-L", "Men's cotton kurta, maroon", "kurtas", { size: "L", colour: "maroon", fabric: "cotton" }, ["kurta"], 1400, 1150, 1050, 850, 6, true],
  ["SAREE-COT-GRN", "Cotton saree, green with zari border", "sarees", { colour: "green", fabric: "cotton" }, ["saree", "cheera", "chira"], 2200, 1850, 1700, 1400, 5, true],
  ["SAREE-SLK-RED", "Silk saree, red", "sarees", { colour: "red", fabric: "silk" }, ["saree", "pattu cheera", "silk saree"], 6500, 5600, 5200, 4300, 3, true],
  ["JEANS-IND-32", "Men's jeans, indigo", "jeans", { size: "32", colour: "indigo" }, ["jeans", "pant"], 1600, 1350, 1250, 1000, 11, true],
  ["SOCKS-3PK", "Cotton socks, pack of 3", "socks", { size: "free", colour: "assorted" }, ["socks", "meezalu"], 250, null, 250, 150, 30, false],
];

const m = (n: number) => n.toFixed(2);

export function seedProducts(): Product[] {
  return rows.map(([id, name, category, attributes, aliases, listed, target, minimum, cost, stock, negotiable]) => ({
    product_id: id,
    merchant_id: "M001",
    product_name: name,
    category,
    attributes,
    aliases,
    listed_price: m(listed),
    target_price: target === null ? null : m(target),
    minimum_price: m(minimum),
    unit_cost: m(cost),
    available_stock: stock,
    negotiable,
  }));
}

export function seedGoals(): Goal[] {
  return [
    {
      goal_id: "G001",
      goal_type: "clear_stock",
      product_ids: ["KURTA-MRN-M", "KURTA-MRN-L"],
      instructions: "These kurtas have been in the shop for a while. Mention them when a customer is looking at shirts.",
    },
  ];
}

// Preserve dependency/font notices omitted by Next.js output tracing.
import { readdir, mkdir, copyFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
const root = process.cwd();
const output = path.resolve(process.argv[2] || "/notices");
const copied = [];
async function walk(directory) {
  let entries;
  try { entries = await readdir(directory, { withFileTypes: true }); }
  catch (error) { if (error.code === "ENOENT") return; throw error; }
  for (const entry of entries) {
    const source = path.join(directory, entry.name);
    if (entry.isDirectory()) await walk(source);
    else if (entry.isFile() && /^(licen[cs]e|copying|notice|ofl)([.-]|$)/i.test(entry.name)) {
      if ((await stat(source)).size > 1_048_576) throw new Error("Unexpectedly large notice; review before shipping");
      const relative = path.relative(root, source);
      const target = path.join(output, relative);
      await mkdir(path.dirname(target), { recursive: true });
      await copyFile(source, target);
      copied.push(relative);
    }
  }
}
await mkdir(output, { recursive: true });
await walk(path.join(root, "node_modules"));
await walk(path.join(root, "apps/web/node_modules"));
if (!copied.some(name => name.includes("noto-sans-sc"))) throw new Error("Noto font notice missing");
await writeFile(path.join(output, "index.json"), JSON.stringify(copied.sort(), null, 2) + "\n");
console.log(`Preserved ${copied.length} dependency/font notice files`);
